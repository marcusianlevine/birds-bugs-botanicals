"""
test_quality.py - LLM-as-judge quality tests (slow, requires ANTHROPIC_API_KEY).

Run: pytest evals/test_quality.py -v --llm-judge
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from evals.judge import judge_instagram, judge_tiktok

PASS_THRESHOLD = 3.5   # out of 5.0


@pytest.mark.llm_judge
class TestInstagramQuality:

    @pytest.fixture(scope="class")
    def ig_report(self, generated_content):
        return judge_instagram(
            caption=generated_content["instagram_caption"],
            category=generated_content["category"],
            species=generated_content["species"],
            research_summary=generated_content.get("research_summary", ""),
        )

    def test_overall_score(self, ig_report):
        assert ig_report.overall >= PASS_THRESHOLD, (
            f"Instagram overall score {ig_report.overall:.1f} below threshold {PASS_THRESHOLD}\n{ig_report}"
        )

    def test_tone(self, ig_report):
        score = next(s for s in ig_report.scores if s.dimension == "tone")
        assert score.score >= 3, f"Tone score {score.score}/5: {score.rationale}"

    def test_engagement(self, ig_report):
        score = next(s for s in ig_report.scores if s.dimension == "engagement")
        assert score.score >= 3, f"Engagement score {score.score}/5: {score.rationale}"

    def test_accuracy(self, ig_report):
        score = next(s for s in ig_report.scores if s.dimension == "accuracy")
        assert score.score >= 3, f"Accuracy score {score.score}/5: {score.rationale}"

    def test_style_match(self, ig_report):
        score = next(s for s in ig_report.scores if s.dimension == "style_match")
        assert score.score >= 3, f"Style match score {score.score}/5: {score.rationale}"


@pytest.mark.llm_judge
class TestTikTokQuality:

    @pytest.fixture(scope="class")
    def tt_report(self, generated_content):
        return judge_tiktok(
            script=generated_content["tiktok_script"],
            caption=generated_content["tiktok_caption"],
            category=generated_content["category"],
            species=generated_content["species"],
            research_summary=generated_content.get("research_summary", ""),
        )

    def test_overall_score(self, tt_report):
        assert tt_report.overall >= PASS_THRESHOLD, (
            f"TikTok overall score {tt_report.overall:.1f} below threshold {PASS_THRESHOLD}\n{tt_report}"
        )

    def test_tone(self, tt_report):
        score = next(s for s in tt_report.scores if s.dimension == "tone")
        assert score.score >= 3, f"Tone score {score.score}/5: {score.rationale}"

    def test_engagement(self, tt_report):
        score = next(s for s in tt_report.scores if s.dimension == "engagement")
        assert score.score >= 3, f"Engagement score {score.score}/5: {score.rationale}"
