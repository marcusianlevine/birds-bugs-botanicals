"""
test_structural.py - fast rule-based tests, no API calls needed.

Run: pytest evals/test_structural.py -v
     (requires data/eval_fixture.json — generate with run_evals.py --save-fixture)
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))
from evals.checks import (
    check_instagram_caption,
    check_tiktok_script,
    check_tiktok_caption,
    check_video_prompt,
)


# ---------------------------------------------------------------------------
# Instagram caption
# ---------------------------------------------------------------------------

class TestInstagramCaption:

    def test_body_word_count(self, generated_content):
        results = check_instagram_caption(
            generated_content["instagram_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "instagram/body_word_count")
        assert result.passed, result.message

    def test_hashtag_count(self, generated_content):
        results = check_instagram_caption(
            generated_content["instagram_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "instagram/hashtag_count")
        assert result.passed, result.message

    def test_required_tags_present(self, generated_content):
        results = check_instagram_caption(
            generated_content["instagram_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "instagram/required_tags")
        assert result.passed, result.message

    def test_has_cta(self, generated_content):
        results = check_instagram_caption(
            generated_content["instagram_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "instagram/has_cta")
        assert result.passed, result.message

    def test_no_emoji_opener(self, generated_content):
        results = check_instagram_caption(
            generated_content["instagram_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "instagram/no_emoji_opener")
        assert result.passed, result.message

    def test_hashtags_at_end(self, generated_content):
        results = check_instagram_caption(
            generated_content["instagram_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "instagram/hashtags_at_end")
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# TikTok script
# ---------------------------------------------------------------------------

class TestTikTokScript:

    def test_sentence_count(self, generated_content):
        results = check_tiktok_script(generated_content["tiktok_script"])
        result = next(r for r in results if r.name == "tiktok_script/sentence_count")
        assert result.passed, result.message

    def test_word_count(self, generated_content):
        results = check_tiktok_script(generated_content["tiktok_script"])
        result = next(r for r in results if r.name == "tiktok_script/word_count")
        assert result.passed, result.message

    def test_uses_you_language(self, generated_content):
        results = check_tiktok_script(generated_content["tiktok_script"])
        result = next(r for r in results if r.name == "tiktok_script/uses_you_language")
        assert result.passed, result.message

    def test_not_empty(self, generated_content):
        results = check_tiktok_script(generated_content["tiktok_script"])
        result = next(r for r in results if r.name == "tiktok_script/not_empty")
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# TikTok caption
# ---------------------------------------------------------------------------

class TestTikTokCaption:

    def test_body_word_count(self, generated_content):
        results = check_tiktok_caption(
            generated_content["tiktok_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "tiktok_caption/body_word_count")
        assert result.passed, result.message

    def test_hashtag_count(self, generated_content):
        results = check_tiktok_caption(
            generated_content["tiktok_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "tiktok_caption/hashtag_count")
        assert result.passed, result.message

    def test_required_tags_present(self, generated_content):
        results = check_tiktok_caption(
            generated_content["tiktok_caption"],
            generated_content["required_tags"],
        )
        result = next(r for r in results if r.name == "tiktok_caption/required_tags")
        assert result.passed, result.message


# ---------------------------------------------------------------------------
# Video prompt
# ---------------------------------------------------------------------------

class TestVideoPrompt:

    def test_has_motion_keywords(self, generated_content):
        results = check_video_prompt(generated_content["video_prompt"])
        result = next(r for r in results if r.name == "video_prompt/has_motion_keywords")
        assert result.passed, result.message

    def test_length(self, generated_content):
        results = check_video_prompt(generated_content["video_prompt"])
        result = next(r for r in results if r.name == "video_prompt/length")
        assert result.passed, result.message

    def test_no_text_overlay(self, generated_content):
        results = check_video_prompt(generated_content["video_prompt"])
        result = next(r for r in results if r.name == "video_prompt/no_text_overlay")
        assert result.passed, result.message
