"""
evals/checks.py - fast, rule-based checks on generated content.

No API calls. Each check returns a dict:
  { "pass": bool, "value": <measured value>, "message": str }

collect_results() gathers all checks into a flat report dict.
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    name: str
    passed: bool
    value: Any
    message: str

    def __str__(self):
        icon = "PASS" if self.passed else "FAIL"
        return f"[{icon}] {self.name}: {self.message}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hashtags(text: str) -> list[str]:
    return re.findall(r'#\w+', text)


def _body_text(caption: str) -> str:
    """Caption text before the first hashtag line."""
    lines = caption.splitlines()
    body_lines = []
    for line in lines:
        if line.strip().startswith('#'):
            break
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def _word_count(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Instagram caption checks
# ---------------------------------------------------------------------------

CTA_KEYWORDS = [
    "comment", "tell us", "share", "spotted", "seen", "find", "tag",
    "drop", "let us know", "have you", "do you", "what do you", "below",
]

def check_instagram_caption(caption: str, required_tags: list[str]) -> list[CheckResult]:
    results = []
    tags = _hashtags(caption)
    body = _body_text(caption)
    body_words = _word_count(body)

    # Word count (body, not including hashtags)
    results.append(CheckResult(
        name="instagram/body_word_count",
        passed=150 <= body_words <= 350,
        value=body_words,
        message=f"{body_words} words (expected 150-350)",
    ))

    # Hashtag count
    results.append(CheckResult(
        name="instagram/hashtag_count",
        passed=15 <= len(tags) <= 35,
        value=len(tags),
        message=f"{len(tags)} hashtags (expected 15-35)",
    ))

    # Required tags present
    existing = {t.lstrip('#').lower() for t in tags}
    missing = [t for t in required_tags if t.lstrip('#').lower() not in existing]
    results.append(CheckResult(
        name="instagram/required_tags",
        passed=len(missing) == 0,
        value=missing,
        message="All required tags present" if not missing else f"Missing: {', '.join(missing)}",
    ))

    # CTA present
    has_cta = any(kw in caption.lower() for kw in CTA_KEYWORDS)
    results.append(CheckResult(
        name="instagram/has_cta",
        passed=has_cta,
        value=has_cta,
        message="Call-to-action found" if has_cta else "No call-to-action detected",
    ))

    # Does not open with an emoji
    first_char = caption.strip()[0] if caption.strip() else ""
    opens_with_emoji = ord(first_char) > 127
    results.append(CheckResult(
        name="instagram/no_emoji_opener",
        passed=not opens_with_emoji,
        value=first_char,
        message="Opens with text (good)" if not opens_with_emoji else f"Opens with emoji '{first_char}' (avoid this)",
    ))

    # Hashtags appear at the end (after body)
    first_hashtag_pos = caption.find('#')
    tags_at_end = first_hashtag_pos > len(body)
    results.append(CheckResult(
        name="instagram/hashtags_at_end",
        passed=tags_at_end,
        value=first_hashtag_pos,
        message="Hashtags appear after body text" if tags_at_end else "Hashtags mixed into body text",
    ))

    return results


# ---------------------------------------------------------------------------
# TikTok script checks
# ---------------------------------------------------------------------------

def check_tiktok_script(script: str) -> list[CheckResult]:
    results = []
    sentences = re.split(r'(?<=[.!?])\s+', script.strip())
    sentences = [s for s in sentences if s.strip()]
    word_count = _word_count(script)

    # Sentence count
    results.append(CheckResult(
        name="tiktok_script/sentence_count",
        passed=2 <= len(sentences) <= 5,
        value=len(sentences),
        message=f"{len(sentences)} sentences (expected 2-5)",
    ))

    # Word count
    results.append(CheckResult(
        name="tiktok_script/word_count",
        passed=20 <= word_count <= 70,
        value=word_count,
        message=f"{word_count} words (expected 20-70 for ~10 sec read)",
    ))

    # Uses second-person language
    uses_you = bool(re.search(r'\byou\b|\byour\b', script, re.IGNORECASE))
    results.append(CheckResult(
        name="tiktok_script/uses_you_language",
        passed=uses_you,
        value=uses_you,
        message="Uses 'you/your' language" if uses_you else "Missing second-person 'you/your' language",
    ))

    # Not empty
    results.append(CheckResult(
        name="tiktok_script/not_empty",
        passed=len(script.strip()) > 20,
        value=len(script.strip()),
        message="Script has content" if len(script.strip()) > 20 else "Script is too short or empty",
    ))

    return results


# ---------------------------------------------------------------------------
# TikTok caption checks
# ---------------------------------------------------------------------------

def check_tiktok_caption(caption: str, required_tags: list[str]) -> list[CheckResult]:
    results = []
    tags = _hashtags(caption)
    body = _body_text(caption)
    body_words = _word_count(body)

    results.append(CheckResult(
        name="tiktok_caption/body_word_count",
        passed=5 <= body_words <= 80,
        value=body_words,
        message=f"{body_words} words (expected 5-80)",
    ))

    results.append(CheckResult(
        name="tiktok_caption/hashtag_count",
        passed=8 <= len(tags) <= 30,
        value=len(tags),
        message=f"{len(tags)} hashtags (expected 8-30)",
    ))

    existing = {t.lstrip('#').lower() for t in tags}
    missing = [t for t in required_tags if t.lstrip('#').lower() not in existing]
    results.append(CheckResult(
        name="tiktok_caption/required_tags",
        passed=len(missing) == 0,
        value=missing,
        message="All required tags present" if not missing else f"Missing: {', '.join(missing)}",
    ))

    return results


# ---------------------------------------------------------------------------
# Video prompt checks
# ---------------------------------------------------------------------------

MOTION_KEYWORDS = [
    "shimmer", "flex", "blink", "sway", "quiver", "breathe", "ripple",
    "movement", "animate", "motion", "gentle", "subtle", "slow",
]

def check_video_prompt(prompt: str) -> list[CheckResult]:
    results = []

    has_motion = any(kw in prompt.lower() for kw in MOTION_KEYWORDS)
    results.append(CheckResult(
        name="video_prompt/has_motion_keywords",
        passed=has_motion,
        value=has_motion,
        message="Contains motion/animation keywords" if has_motion else "Missing motion keywords",
    ))

    results.append(CheckResult(
        name="video_prompt/length",
        passed=40 <= len(prompt.split()) <= 120,
        value=len(prompt.split()),
        message=f"{len(prompt.split())} words (expected 40-120)",
    ))

    no_text_overlay = "no text" in prompt.lower() or "no overlay" in prompt.lower()
    results.append(CheckResult(
        name="video_prompt/no_text_overlay",
        passed=no_text_overlay,
        value=no_text_overlay,
        message="Explicitly excludes text overlays" if no_text_overlay else "Should say 'no text overlays'",
    ))

    return results


# ---------------------------------------------------------------------------
# Convenience: run all checks for a full GeneratedContent object
# ---------------------------------------------------------------------------

def run_all_checks(content, category: str, required_tags: list[str]) -> list[CheckResult]:
    """
    Run every structural check against a GeneratedContent instance.

    Args:
        content:       GeneratedContent dataclass from content_generator.py
        category:      "bird" | "bug" | "botanical"
        required_tags: list of required hashtag strings (with #)

    Returns:
        Flat list of CheckResult objects.
    """
    results = []
    results += check_instagram_caption(content.instagram_caption, required_tags)
    results += check_tiktok_script(content.tiktok_script)
    results += check_tiktok_caption(content.tiktok_caption, required_tags)
    results += check_video_prompt(content.video_prompt)
    return results
