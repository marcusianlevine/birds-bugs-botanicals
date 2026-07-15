"""Unit tests for species_discovery.py (iNaturalist-backed pool growth)."""

import json
import random

import pytest

import config
import species_discovery as sd


def _taxon(name, rank="species", photo=True, common=None):
    return {
        "count": 1,
        "taxon": {
            "rank": rank,
            "preferred_common_name": name if common is None else common,
            "default_photo": {"url": "u"} if photo else None,
            "name": "Scientificus " + str(name),
        },
    }


class TestCandidateNames:
    def test_filters_and_dedups(self):
        results = [
            _taxon("American Robin"),
            _taxon("Genus Only", rank="genus"),      # not a species
            _taxon("No Photo", photo=False),          # no photo
            _taxon("No Common", common=""),           # no common name
            _taxon("American Robin"),                 # duplicate in batch
            _taxon("Cedar Waxwing"),
        ]
        assert sd._candidate_names(results, set()) == ["American Robin", "Cedar Waxwing"]

    def test_excludes_case_insensitively(self):
        results = [_taxon("Blue Jay"), _taxon("Northern Cardinal")]
        assert sd._candidate_names(results, {"blue jay"}) == ["Northern Cardinal"]


@pytest.fixture
def pools_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "REJECTED_FILE", tmp_path / "rejected_species.json")
    (tmp_path / "species_pools.json").write_text(json.dumps(
        {"bird": ["Northern Cardinal"], "bug": ["Monarch"], "botanical": ["Lavender"]}))
    (tmp_path / "rejected_species.json").write_text(json.dumps(
        {"bird": [{"name": "Blue Jay", "date": "x", "reason": "no acceptable photo"}],
         "bug": [], "botanical": []}))
    return tmp_path


class TestDiscover:
    def test_distributes_excludes_and_validates(self, pools_dir, monkeypatch):
        random.seed(0)
        fake = {
            "Aves": [_taxon(n) for n in ["Robin", "Wren", "Northern Cardinal", "Blue Jay"]],
            "Insecta": [_taxon(n) for n in ["Beetle", "Wasp"]],
            "Plantae": [_taxon(n) for n in ["Sage", "Weedy Plant", "Thyme"]],
        }
        monkeypatch.setattr(sd, "_fetch_species_counts", lambda iconic, per_page=200: fake[iconic])
        monkeypatch.setattr(sd, "_botanical_ok", lambda name: name in {"Sage", "Thyme"})

        added, pools = sd.discover(max_total=10)
        flat = [n for names in added.values() for n in names]
        # existing pool members and rejected species are never re-added
        assert "Northern Cardinal" not in flat
        assert "Blue Jay" not in flat
        assert "Monarch" not in flat
        # botanicals validated: only Sage/Thyme, never "Weedy Plant"
        assert set(added["botanical"]) <= {"Sage", "Thyme"}
        assert "Weedy Plant" not in flat
        # everything added is actually appended to the returned pools
        for cat, names in added.items():
            for n in names:
                assert n in pools[cat]

    def test_respects_max_total(self, pools_dir, monkeypatch):
        monkeypatch.setattr(sd, "_fetch_species_counts",
                            lambda iconic, per_page=200: [_taxon(f"{iconic}{i}") for i in range(20)])
        monkeypatch.setattr(sd, "_botanical_ok", lambda name: True)
        added, _ = sd.discover(max_total=4)
        assert sum(len(v) for v in added.values()) == 4

    def test_only_category(self, pools_dir, monkeypatch):
        monkeypatch.setattr(sd, "_fetch_species_counts",
                            lambda iconic, per_page=200: [_taxon("New Bird")])
        added, _ = sd.discover(max_total=5, only_category="bird")
        assert list(added) == ["bird"]
        assert added["bird"] == ["New Bird"]

    def test_no_validate_keeps_botanicals(self, pools_dir, monkeypatch):
        monkeypatch.setattr(sd, "_fetch_species_counts",
                            lambda iconic, per_page=200: [_taxon("Some Plant")] if iconic == "Plantae" else [])
        # _botanical_ok would reject, but validation is off, so it should be added
        monkeypatch.setattr(sd, "_botanical_ok", lambda name: False)
        added, _ = sd.discover(max_total=5, only_category="botanical", validate_botanicals=False)
        assert added["botanical"] == ["Some Plant"]


class TestPoolsIO:
    def test_save_load_roundtrip(self, pools_dir):
        pools = sd._load_pools()
        pools["bird"].append("New Bird")
        sd._save_pools(pools)
        assert sd._load_pools()["bird"][-1] == "New Bird"


class TestRejectedNames:
    def test_loads_lowercased_across_categories(self, pools_dir):
        assert "blue jay" in sd._rejected_names()

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "REJECTED_FILE", tmp_path / "does_not_exist.json")
        assert sd._rejected_names() == set()
