"""
conftest.py - pytest configuration for the BBB eval suite.

Flags:
  --llm-judge   Also run the slow LLM-as-judge tests (requires ANTHROPIC_API_KEY)
  --generate    Generate fresh content via the full pipeline before testing
                (requires all API keys). Without this flag, tests use fixtures
                from data/eval_fixture.json if it exists.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_addoption(parser):
    parser.addoption(
        "--llm-judge",
        action="store_true",
        default=False,
        help="Run LLM-as-judge quality tests (slow, requires ANTHROPIC_API_KEY)",
    )
    parser.addoption(
        "--generate",
        action="store_true",
        default=False,
        help="Generate fresh content via the full pipeline before running tests",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "llm_judge: mark test as requiring the LLM judge (slow)")
    config.addinivalue_line("markers", "requires_generation: mark test as requiring live generation")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--llm-judge"):
        skip = pytest.mark.skip(reason="pass --llm-judge to run")
        for item in items:
            if "llm_judge" in item.keywords:
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FIXTURE_FILE = Path(__file__).parent.parent / "data" / "eval_fixture.json"


def _load_fixture() -> dict | None:
    if FIXTURE_FILE.exists():
        with open(FIXTURE_FILE) as f:
            return json.load(f)
    return None


@pytest.fixture(scope="session")
def generated_content(request):
    """
    Returns a dict with keys: category, species, instagram_caption,
    tiktok_script, tiktok_caption, video_prompt, alt_text, research_summary.

    With --generate: runs the full pipeline (slow, needs all API keys).
    Without --generate: loads from data/eval_fixture.json (fast).
    """
    if request.config.getoption("--generate"):
        return _generate_live()
    fixture = _load_fixture()
    if fixture is None:
        pytest.skip(
            "No eval fixture found. Run `python evals/run_evals.py --save-fixture` "
            "to generate one, or pass --generate to produce content live."
        )
    return fixture


def _generate_live() -> dict:
    """Run the pipeline and return content as a plain dict."""
    from species_selector import pick_today
    from research import research
    from content_generator import generate_content, get_required_tags

    for _ in range(10):
        sel = pick_today()
        result = research(sel.category, sel.common_name)
        if result is not None:
            break
    else:
        raise RuntimeError("Could not find a valid species after 10 attempts")

    content = generate_content(result)
    required_tags = get_required_tags(sel.category)

    return {
        "category": sel.category,
        "species": sel.common_name,
        "scientific_name": result.scientific_name,
        "instagram_caption": content.instagram_caption,
        "tiktok_script": content.tiktok_script,
        "tiktok_caption": content.tiktok_caption,
        "video_prompt": content.video_prompt,
        "alt_text": content.alt_text,
        "required_tags": required_tags,
        "research_summary": result.wikipedia_summary[:600],
    }
