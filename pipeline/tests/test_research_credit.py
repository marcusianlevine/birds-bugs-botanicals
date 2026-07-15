"""Unit tests for Wikimedia photo-credit extraction in research.py."""

import requests

import research
from research import _strip_html, _wikimedia_image_credit


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TestStripHtml:
    def test_removes_tags_and_decodes_entities(self):
        assert _strip_html('<a href="/wiki/User:X">Jane &amp; Co</a>') == "Jane & Co"

    def test_empty_input(self):
        assert _strip_html("") == ""

    def test_truncates_long_values(self):
        assert len(_strip_html("x" * 300)) <= 120


class TestWikimediaImageCredit:
    def test_fallback_on_empty_url(self):
        assert _wikimedia_image_credit("") == "Wikimedia Commons"

    def test_parses_artist(self, monkeypatch):
        payload = {"query": {"pages": [
            {"imageinfo": [{"extmetadata": {"Artist": {"value": '<a href="x">Jane Doe</a>'}}}]}
        ]}}
        monkeypatch.setattr(research, "get_with_retry", lambda *a, **k: _FakeResp(payload))
        got = _wikimedia_image_credit("https://upload.wikimedia.org/wikipedia/commons/a/aa/Owl.jpg")
        assert got == "Jane Doe / Wikimedia Commons"

    def test_fallback_when_no_artist_field(self, monkeypatch):
        payload = {"query": {"pages": [{"imageinfo": [{"extmetadata": {}}]}]}}
        monkeypatch.setattr(research, "get_with_retry", lambda *a, **k: _FakeResp(payload))
        assert _wikimedia_image_credit("https://upload.wikimedia.org/x/Owl.jpg") == "Wikimedia Commons"

    def test_network_error_falls_back(self, monkeypatch):
        def boom(*a, **k):
            raise requests.RequestException("down")
        monkeypatch.setattr(research, "get_with_retry", boom)
        assert _wikimedia_image_credit("https://upload.wikimedia.org/x/Owl.jpg") == "Wikimedia Commons"
