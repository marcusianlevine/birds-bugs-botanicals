"""Unit tests for the caption source footer (Wikipedia link + photo credit)."""

from content_generator import (
    format_photo_credit,
    build_caption_footer,
    _append_footer,
)
from research import Photo, ResearchResult


def _photo(attribution: str, source: str) -> Photo:
    return Photo(url="u", thumb_url="t", attribution=attribution, source=source)


class TestFormatPhotoCredit:
    def test_inaturalist_appends_source(self):
        credit = format_photo_credit(_photo("(c) jsmith (CC BY-NC)", "iNaturalist"))
        assert credit == "(c) jsmith (CC BY-NC) · via iNaturalist"

    def test_wikipedia_not_duplicated(self):
        # attribution already names Wikimedia, so "via Wikipedia" is suppressed
        credit = format_photo_credit(_photo("Jane Doe / Wikimedia Commons", "Wikipedia"))
        assert credit == "Jane Doe / Wikimedia Commons"

    def test_ebird_macaulay_not_duplicated(self):
        credit = format_photo_credit(_photo("© A. Birder / Macaulay Library", "eBird"))
        assert credit == "© A. Birder / Macaulay Library"

    def test_empty_attribution_uses_via(self):
        assert format_photo_credit(_photo("", "iNaturalist")) == "via iNaturalist"

    def test_none_photo(self):
        assert format_photo_credit(None) == ""


class TestBuildCaptionFooter:
    def test_full_footer(self):
        r = ResearchResult(
            category="bird",
            common_name="Barn Owl",
            wikipedia_url="https://en.wikipedia.org/wiki/Barn_owl",
        )
        footer = build_caption_footer(r, _photo("(c) jsmith", "iNaturalist"))
        assert "📖 Learn more: https://en.wikipedia.org/wiki/Barn_owl" in footer
        assert "📷 Photo: (c) jsmith · via iNaturalist" in footer

    def test_link_only_when_no_photo(self):
        r = ResearchResult(category="bird", common_name="X",
                           wikipedia_url="https://en.wikipedia.org/wiki/X")
        footer = build_caption_footer(r, None)
        assert footer == "📖 Learn more: https://en.wikipedia.org/wiki/X"

    def test_empty_when_no_url_and_no_photo(self):
        assert build_caption_footer(ResearchResult(category="bug", common_name="X"), None) == ""


class TestAppendFooter:
    def test_appended_below_hashtags(self):
        out = _append_footer("Caption body\n#a #b", "📖 Learn more: url")
        assert out == "Caption body\n#a #b\n\n📖 Learn more: url"

    def test_noop_when_footer_empty(self):
        assert _append_footer("Caption", "") == "Caption"
