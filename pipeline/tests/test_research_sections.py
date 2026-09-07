"""Unit tests for _first_section_text section extraction in research.py."""

from research import _first_section_text


class _FakeSection:
    def __init__(self, text: str):
        self.text = text


class _FakePage:
    """Minimal stand-in for a wikipediaapi page."""

    def __init__(self, sections: dict):
        self._sections = sections

    def section_by_title(self, title: str):
        return self._sections.get(title)


class TestFirstSectionText:
    def test_returns_first_match_in_title_order(self):
        page = _FakePage({
            "Ecology": _FakeSection("ecology text"),
            "Invasive species": _FakeSection("invasive text"),
        })
        got = _first_section_text(page, ("Invasive species", "Ecology"))
        assert got == "invasive text"

    def test_returns_empty_when_no_section_matches(self):
        page = _FakePage({"History": _FakeSection("nope")})
        assert _first_section_text(page, ("Invasive species", "Ecology")) == ""

    def test_skips_blank_sections_and_continues(self):
        page = _FakePage({
            "Invasive species": _FakeSection("   \n  "),
            "Ecology": _FakeSection("real ecology content"),
        })
        assert _first_section_text(page, ("Invasive species", "Ecology")) == "real ecology content"

    def test_strips_surrounding_whitespace(self):
        page = _FakePage({"Threats": _FakeSection("\n  habitat loss  \n")})
        assert _first_section_text(page, ("Threats",)) == "habitat loss"
