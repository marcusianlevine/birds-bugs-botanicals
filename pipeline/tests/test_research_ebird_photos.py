"""Unit tests for _get_ebird_photos response-shape handling in research.py."""

import requests
import research
from research import _get_ebird_photos


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _one_asset(asset_id="12345", photographer="Jane Doe"):
    return {"assetId": asset_id, "userDisplayName": photographer}


class TestGetEbirdPhotos:
    def test_empty_species_code_skips_call(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("should not hit the network")
        monkeypatch.setattr(research, "get_with_retry", boom)
        assert _get_ebird_photos("") == []

    def test_parses_normal_shape(self, monkeypatch):
        payload = {"results": {"content": [_one_asset()]}}
        monkeypatch.setattr(research, "get_with_retry", lambda *a, **k: _FakeResp(payload))
        photos = _get_ebird_photos("norrif1")
        assert len(photos) == 1
        assert photos[0].source == "eBird"
        assert "12345" in photos[0].url
        assert photos[0].attribution == "© Jane Doe / Macaulay Library"

    def test_bare_list_payload_is_tolerated(self, monkeypatch):
        # The Macaulay Library search API has been observed returning a
        # top-level list instead of {"results": {"content": [...]}}.
        monkeypatch.setattr(
            research, "get_with_retry", lambda *a, **k: _FakeResp([_one_asset()])
        )
        photos = _get_ebird_photos("norrif1")
        assert len(photos) == 1
        assert "12345" in photos[0].url

    def test_unexpected_shape_returns_empty(self, monkeypatch):
        for payload in ("nope", 42, None, {"results": []}, [123, "x"]):
            monkeypatch.setattr(
                research, "get_with_retry", lambda *a, _p=payload, **k: _FakeResp(_p)
            )
            assert _get_ebird_photos("norrif1") == []

    def test_network_error_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise requests.RequestException("down")
        monkeypatch.setattr(research, "get_with_retry", boom)
        assert _get_ebird_photos("norrif1") == []

    def test_items_without_asset_id_are_skipped(self, monkeypatch):
        payload = {"results": {"content": [{"userDisplayName": "x"}, _one_asset()]}}
        monkeypatch.setattr(research, "get_with_retry", lambda *a, **k: _FakeResp(payload))
        assert len(_get_ebird_photos("norrif1")) == 1
