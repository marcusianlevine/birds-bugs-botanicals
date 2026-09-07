"""Tests that the caption prompts surface invasiveness / ecological impact."""

from content_generator import _build_instagram_prompt, _build_tiktok_prompt
from research import ResearchResult

_IMPACT = (
    "Lycorma delicatula is a serious invasive pest in the eastern United States, "
    "damaging grapevines, hops and hardwoods. First detected in Pennsylvania in 2014."
)


def _lanternfly(impact: str = _IMPACT) -> ResearchResult:
    return ResearchResult(
        category="bug",
        common_name="Spotted Lanternfly",
        scientific_name="Lycorma delicatula",
        wikipedia_summary="A planthopper native to China.",
        impact_section=impact,
    )


class TestInstagramPrompt:
    def test_impact_section_text_is_included(self):
        prompt = _build_instagram_prompt(_lanternfly(), ["#nature"])
        assert "STATUS / ECOLOGICAL IMPACT" in prompt
        assert "serious invasive pest" in prompt

    def test_standing_impact_instructions_are_always_present(self):
        # Even with no impact section, the standing instructions stay in the prompt.
        prompt = _build_instagram_prompt(_lanternfly(impact=""), ["#nature"])
        assert "STATUS / ECOLOGICAL IMPACT" not in prompt
        assert "that paragraph is REQUIRED and you MUST" in prompt
        assert "specific regions where it is invasive or a problem" in prompt

    def test_status_paragraph_is_conditional_not_forced(self):
        prompt = _build_instagram_prompt(_lanternfly(impact=""), ["#nature"])
        assert "don't manufacture" in prompt

    def test_cta_makes_the_regional_distinction(self):
        prompt = _build_instagram_prompt(_lanternfly(), ["#nature"])
        assert "address the reader conditionally by location" in prompt
        assert "everyone toward reporting or control instead of admiration" in prompt

    def test_no_assumed_audience_region(self):
        prompt = _build_instagram_prompt(_lanternfly(), ["#nature"])
        assert "The audience is global." in prompt
        assert "North America" not in prompt

    def test_impact_section_is_truncated(self):
        prompt = _build_instagram_prompt(_lanternfly(impact="x" * 5000), ["#nature"])
        assert "x" * 700 in prompt
        assert "x" * 701 not in prompt


class TestTiktokPrompt:
    def test_impact_section_text_is_included(self):
        prompt = _build_tiktok_prompt(_lanternfly(), ["#nature"])
        assert "STATUS / ECOLOGICAL IMPACT" in prompt
        assert "serious invasive pest" in prompt

    def test_standing_impact_instructions_present_without_section(self):
        prompt = _build_tiktok_prompt(_lanternfly(impact=""), ["#nature"])
        assert "STATUS / ECOLOGICAL IMPACT" not in prompt
        assert "name the regions it affects" in prompt
        assert "never plant or release it" in prompt
        assert "The audience is global." in prompt
        assert "North America" not in prompt
