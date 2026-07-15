"""Unit tests for species_selector.py: rejection tracking, exclusion, and the
pool-exhaustion → discovery flow."""

import json

import pytest

import config
import species_selector as ss
import species_discovery as sd


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "posted_history.json")
    monkeypatch.setattr(config, "REJECTED_FILE", tmp_path / "rejected_species.json")
    monkeypatch.setattr(config, "DISCOVERY_REFILL_COUNT", 10)

    def write(pools=None, posted=None, rejected=None):
        empty = {"bird": [], "bug": [], "botanical": []}
        (tmp_path / "species_pools.json").write_text(json.dumps(
            pools or {"bird": ["A", "B"], "bug": ["X"], "botanical": ["P"]}))
        (tmp_path / "posted_history.json").write_text(json.dumps(posted or empty))
        (tmp_path / "rejected_species.json").write_text(json.dumps(rejected or empty))

    write()
    return write


def _posted(*names):
    return {"bird": [{"name": n, "date": "d"} for n in names], "bug": [], "botanical": []}


class TestMarkRejected:
    def test_persists_with_reason_and_is_idempotent(self, data_dir):
        sel = ss.SpeciesSelection(category="bird", common_name="A")
        ss.mark_rejected(sel)
        ss.mark_rejected(sel)  # duplicate should not double-record
        data = json.loads(config.REJECTED_FILE.read_text())
        assert [e["name"] for e in data["bird"]] == ["A"]
        assert data["bird"][0]["reason"] == "no acceptable photo"


class TestPickTodayExclusion:
    def test_excludes_posted_and_rejected(self, data_dir):
        data_dir(
            pools={"bird": ["A", "B", "C"], "bug": ["X"], "botanical": ["P"]},
            posted=_posted("A"),
            rejected={"bird": [{"name": "B", "date": "d", "reason": "r"}], "bug": [], "botanical": []},
        )
        picks = {ss.pick_today(category="bird").common_name for _ in range(50)}
        assert picks == {"C"}


class TestExhaustionTriggersDiscovery:
    def test_discovery_adds_species_and_history_kept(self, data_dir, monkeypatch):
        data_dir(pools={"bird": ["A", "B"], "bug": ["X"], "botanical": ["P"]},
                 posted=_posted("A", "B"))

        def fake_discover(max_total, only_category=None, validate_botanicals=True):
            assert only_category == "bird" and max_total == 10
            pools = sd._load_pools()
            pools[only_category].append("Discovered Owl")
            return {only_category: ["Discovered Owl"]}, pools

        monkeypatch.setattr(sd, "discover", fake_discover)
        got = ss.pick_today(category="bird")
        assert got.common_name == "Discovered Owl"
        # discovery succeeded, so posted history must NOT be reset
        assert len(json.loads(config.HISTORY_FILE.read_text())["bird"]) == 2

    def test_discovery_empty_resets_history(self, data_dir, monkeypatch):
        data_dir(pools={"bird": ["A", "B"], "bug": ["X"], "botanical": ["P"]},
                 posted=_posted("A", "B"))
        monkeypatch.setattr(sd, "discover",
                            lambda max_total, only_category=None, validate_botanicals=True:
                            ({only_category: []}, sd._load_pools()))
        got = ss.pick_today(category="bird")
        assert got.common_name in {"A", "B"}
        assert json.loads(config.HISTORY_FILE.read_text())["bird"] == []  # recycled

    def test_discovery_error_is_swallowed(self, data_dir, monkeypatch):
        data_dir(pools={"bird": ["A", "B"], "bug": ["X"], "botanical": ["P"]},
                 posted=_posted("A", "B"))

        def boom(*a, **k):
            raise RuntimeError("iNaturalist down")

        monkeypatch.setattr(sd, "discover", boom)
        got = ss.pick_today(category="bird")  # must not raise
        assert got.common_name in {"A", "B"}

    def test_not_exhausted_does_not_call_discovery(self, data_dir, monkeypatch):
        calls = {"n": 0}

        def spy(*a, **k):
            calls["n"] += 1
            return ({}, sd._load_pools())

        monkeypatch.setattr(sd, "discover", spy)
        got = ss.pick_today(category="bird")  # default pools A,B with nothing posted
        assert got.common_name in {"A", "B"}
        assert calls["n"] == 0
