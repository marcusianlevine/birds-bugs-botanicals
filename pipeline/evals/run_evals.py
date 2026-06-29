#!/usr/bin/env python3
"""
evals/run_evals.py - end-to-end eval runner.

Usage:
  # Generate content + run all checks + LLM judge:
  python evals/run_evals.py

  # Force a specific category:
  python evals/run_evals.py --category bird

  # Save content as fixture so pytest can run without re-generating:
  python evals/run_evals.py --save-fixture

  # Skip the LLM judge (structural checks only, faster):
  python evals/run_evals.py --no-judge

  # Eval against already-saved fixture (no generation, no API except judge):
  python evals/run_evals.py --use-fixture
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from species_selector import pick_today
from research import research
from content_generator import generate_content, get_required_tags
from evals.checks import run_all_checks
from evals.judge import judge_instagram, judge_tiktok

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("run_evals")

FIXTURE_FILE = config.DATA_DIR / "eval_fixture.json"
PASS_THRESHOLD = 3.5


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate(category: str | None = None) -> dict:
    log.info("Selecting species...")
    for attempt in range(10):
        sel = pick_today(category=category)
        log.info("[%d] Trying: %s (%s)", attempt + 1, sel.common_name, sel.category)
        result = research(sel.category, sel.common_name)
        if result is not None:
            break
    else:
        log.error("Could not find a valid species after 10 attempts.")
        sys.exit(1)

    log.info("Generating content...")
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


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

PASS_ICON = "\033[92mPASS\033[0m"
FAIL_ICON = "\033[91mFAIL\033[0m"
WARN_ICON = "\033[93mWARN\033[0m"


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_structural_results(results):
    print_header("STRUCTURAL CHECKS")
    passed = sum(1 for r in results if r.passed)
    for r in results:
        icon = PASS_ICON if r.passed else FAIL_ICON
        print(f"  [{icon}] {r.name:<45} {r.message}")
    print(f"\n  {passed}/{len(results)} checks passed")
    return passed == len(results)


def print_judge_report(report):
    icon = PASS_ICON if report.passed(PASS_THRESHOLD) else FAIL_ICON
    print(f"\n  [{icon}] {report.post_type.upper()} overall: {report.overall:.1f}/5.0")
    for s in report.scores:
        bar = "█" * s.score + "░" * (5 - s.score)
        print(f"         {s.dimension:<14} [{bar}] {s.score}/5  {s.rationale}")
    print(f"\n  Summary: {report.summary}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args):
    # Load or generate fixture
    if args.use_fixture:
        if not FIXTURE_FILE.exists():
            log.error("No fixture found at %s. Run without --use-fixture first.", FIXTURE_FILE)
            sys.exit(1)
        log.info("Loading fixture from %s", FIXTURE_FILE)
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
    else:
        data = generate(category=args.category)

    if args.save_fixture:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(FIXTURE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        log.info("Fixture saved to %s", FIXTURE_FILE)

    # Print what we're evaluating
    print_header(f"EVALUATING: {data['species']} ({data['category']})")
    print(f"\n  Scientific name : {data.get('scientific_name', 'unknown')}")
    print(f"\n--- Instagram Caption ---\n{data['instagram_caption'][:300]}...")
    print(f"\n--- TikTok Script ---\n{data['tiktok_script']}")
    print(f"\n--- TikTok Caption ---\n{data['tiktok_caption'][:200]}...")
    print(f"\n--- Video Prompt ---\n{data['video_prompt']}")

    # Structural checks (fast, no API)
    from content_generator import GeneratedContent
    content = GeneratedContent(
        instagram_caption=data["instagram_caption"],
        tiktok_script=data["tiktok_script"],
        tiktok_caption=data["tiktok_caption"],
        video_prompt=data["video_prompt"],
        alt_text=data.get("alt_text", ""),
    )
    structural_results = run_all_checks(content, data["category"], data["required_tags"])
    structural_ok = print_structural_results(structural_results)

    # LLM judge (slow, requires API)
    judge_ok = True
    if not args.no_judge:
        print_header("LLM JUDGE SCORES")
        try:
            ig_report = judge_instagram(
                caption=data["instagram_caption"],
                category=data["category"],
                species=data["species"],
                research_summary=data.get("research_summary", ""),
            )
            print_judge_report(ig_report)
            if not ig_report.passed(PASS_THRESHOLD):
                judge_ok = False

            tt_report = judge_tiktok(
                script=data["tiktok_script"],
                caption=data["tiktok_caption"],
                category=data["category"],
                species=data["species"],
                research_summary=data.get("research_summary", ""),
            )
            print_judge_report(tt_report)
            if not tt_report.passed(PASS_THRESHOLD):
                judge_ok = False

        except Exception as e:
            log.error("LLM judge failed: %s", e)
            judge_ok = False

    # Final verdict
    print_header("VERDICT")
    overall_ok = structural_ok and judge_ok
    verdict = PASS_ICON if overall_ok else FAIL_ICON
    print(f"\n  [{verdict}] {'All checks passed.' if overall_ok else 'Some checks failed — review output above.'}\n")
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BBB content eval runner")
    parser.add_argument("--category", choices=["bird", "bug", "botanical"], default=None)
    parser.add_argument("--save-fixture", action="store_true", help="Save generated content as eval fixture")
    parser.add_argument("--use-fixture", action="store_true", help="Load existing fixture instead of generating")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge (structural checks only)")
    run(parser.parse_args())
