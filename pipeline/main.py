#!/usr/bin/env python3
"""
main.py – Birds, Bugs & Botanicals daily content pipeline.

Run manually:
  python main.py

Run for a specific category:
  python main.py --category bird
  python main.py --category bug
  python main.py --category botanical

Generate everything (including Kling video) but skip posting:
  python main.py --no-post

Dry run (skip video generation AND posting — fast, cheap):
  python main.py --dry-run

Post to Instagram only (e.g. while the TikTok app is pending approval):
  python main.py --no-tiktok

Everything is saved to output/<YYYY-MM-DD>/ regardless of mode.
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote


import config
from net import get_with_retry
from species_selector import (
    pick_today,
    pick_named,
    mark_posted,
    mark_rejected,
    SpeciesSelection,
)
from research import research, ResearchResult
from image_reviewer import select_best_photo
from content_generator import generate_content, GeneratedContent
from video_generator import generate_video, GeneratedVideo
from social_media import (
    post_instagram_photo,
    post_instagram_reel,
    post_tiktok_photo,
    post_tiktok_video,
)

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


# ── Output directory ───────────────────────────────────────────────────────────

def make_output_dir() -> Path:
    today = date.today().isoformat()
    out = config.OUTPUT_DIR / today
    out.mkdir(parents=True, exist_ok=True)
    return out


# ── Image download helper ──────────────────────────────────────────────────────

def download_image(url: str, dest: Path) -> Path:
    """Download an image from a URL to a local path. Returns the dest path."""
    log.info("Downloading image: %s", url)
    resp = get_with_retry(
        url,
        timeout=30,
        stream=True,
        max_attempts=config.IMAGE_PULL_MAX_ATTEMPTS,
        backoff_base=config.IMAGE_PULL_BACKOFF_BASE,
    )

    # Determine extension from content-type
    ct = resp.headers.get("content-type", "image/jpeg")
    ext = ".jpg" if "jpeg" in ct else ".png" if "png" in ct else ".jpg"
    dest = dest.with_suffix(ext)

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    log.info("Image saved: %s", dest)
    return dest


# ── Save text outputs ──────────────────────────────────────────────────────────

def save_outputs(
    out_dir: Path,
    selection: SpeciesSelection,
    result: ResearchResult,
    content: GeneratedContent,
    posting_result: dict,
    image_selection=None,
) -> None:
    """Write all generated text + metadata to the output directory."""

    image_review = None
    if image_selection is not None:
        image_review = {
            "chosen_source": image_selection.photo.source if image_selection.photo else None,
            "chosen_url": image_selection.photo.url if image_selection.photo else None,
            "approved": image_selection.approved,
            "reviews": image_selection.reviews,
        }

    summary = {
        "date": date.today().isoformat(),
        "category": selection.category,
        "common_name": selection.common_name,
        "scientific_name": result.scientific_name,
        "wikipedia_url": result.wikipedia_url,
        "conservation_status": result.conservation_status,
        "photos_sourced": len(result.photos),
        "image_review": image_review,
        "posting": posting_result,
    }

    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out_dir / "instagram_caption.txt").write_text(
        content.instagram_caption, encoding="utf-8"
    )
    (out_dir / "tiktok_script.txt").write_text(
        f"VOICEOVER SCRIPT:\n{content.tiktok_script}\n\n"
        f"TIKTOK CAPTION:\n{content.tiktok_caption}",
        encoding="utf-8"
    )
    (out_dir / "video_prompt.txt").write_text(
        content.video_prompt, encoding="utf-8"
    )
    (out_dir / "alt_text.txt").write_text(
        content.alt_text, encoding="utf-8"
    )
    (out_dir / "research_notes.txt").write_text(
        _format_research(result), encoding="utf-8"
    )

    log.info("All outputs saved to: %s", out_dir)


def _format_research(r: ResearchResult) -> str:
    lines = [
        f"SPECIES: {r.common_name} ({r.scientific_name})",
        f"CATEGORY: {r.category}",
        f"CONSERVATION: {r.conservation_status or 'not listed'}",
        f"WIKIPEDIA: {r.wikipedia_url}",
        "",
        "SUMMARY:",
        r.wikipedia_summary,
    ]
    if r.fun_facts:
        lines += ["", "FUN FACTS:"]
        lines += [f"  • {f}" for f in r.fun_facts]
    if r.uses_section:
        lines += ["", "USES:", r.uses_section[:1000]]
    return "\n".join(lines)


# ── Main pipeline ──────────────────────────────────────────────────────────────

def _find_good_photo(result: ResearchResult, common_name: str):
    """
    Run the image reviewer and decide whether this species has a usable photo.

    Returns the SelectionResult when a good photo is found — meaning the vision
    reviewer approved a candidate, or image review is disabled (in which case we
    can't judge quality and just accept the first candidate). Returns None when
    the species has no candidate photos or the reviewer rejected all of them, so
    the caller can move on to another species.
    """
    if not result.photos:
        log.warning("No candidate photos found for '%s'.", common_name)
        return None

    sel = select_best_photo(result)
    if sel.photo is not None and (sel.approved or not config.IMAGE_REVIEW_ENABLED):
        return sel

    log.warning(
        "Image reviewer found no clear, high-quality photo of '%s' "
        "(all %d candidate(s) rejected).",
        common_name, len(sel.reviews) or len(result.photos),
    )
    return None


def _tiktok_pull_url(image_url: str) -> str:
    """
    Build the URL TikTok will PULL_FROM_URL for a photo post.

    TikTok requires the URL's domain to be verified in your app. If a verified
    site base URL is configured (config.MEDIA_PROXY_BASE_URL) we route the image
    through its /api/photo-proxy; otherwise we fall back to the raw URL and warn
    (which only succeeds if that source domain is itself verified).
    """
    base = config.MEDIA_PROXY_BASE_URL.rstrip("/")
    if base:
        return f"{base}/api/photo-proxy?src={quote(image_url, safe='')}"
    log.warning(
        "MEDIA_PROXY_BASE_URL is not set — passing the raw image URL to TikTok. "
        "TikTok photo posts require the URL's domain to be verified in your app; "
        "set MEDIA_PROXY_BASE_URL to your deployed site to route through "
        "/api/photo-proxy."
    )
    return image_url


def run(
    category: str | None = None,
    dry_run: bool = False,
    no_post: bool = False,
    species: str | None = None,
    mode: str = "photo",
    no_tiktok: bool = False,
) -> None:
    out_dir = make_output_dir()
    log.info("Output directory: %s", out_dir)

    # ── 1. Select species (research + a reviewer-approved photo both required) ──
    #   Candidate photos are ordered Wikipedia → iNaturalist → eBird; a vision
    #   LLM must approve one as a clear, high-quality shot with the organism
    #   clearly visible. If none is approved the species is rejected: in auto
    #   mode we pick another, and for a forced --species we abort with a clear
    #   "no good photo" message.
    selection: SpeciesSelection | None = None
    result: ResearchResult | None = None
    selection_result = None

    if species:
        # Explicit override – research exactly this species, no random picking.
        try:
            candidate = pick_named(species, category=category)
        except ValueError as e:
            log.error("%s", e)
            sys.exit(1)

        log.info("Forced species: %s (%s)", candidate.common_name, candidate.category)
        candidate_result = research(candidate.category, candidate.common_name)
        if candidate_result is None:
            log.error(
                "'%s' failed research/validation (e.g. no Wikipedia page, or a "
                "botanical with no Uses section). Aborting.",
                candidate.common_name,
            )
            sys.exit(1)

        candidate_selection = _find_good_photo(candidate_result, candidate.common_name)
        if candidate_selection is None:
            log.error(
                "'%s' does not have a good photo – the image reviewer rejected "
                "every candidate. Nothing to feature; try a different species.",
                candidate.common_name,
            )
            sys.exit(1)
        selection, result, selection_result = candidate, candidate_result, candidate_selection
    else:
        MAX_TRIES = 10
        for attempt in range(1, MAX_TRIES + 1):
            candidate = pick_today(category=category)
            log.info("[%d/%d] Trying: %s (%s)", attempt, MAX_TRIES,
                     candidate.common_name, candidate.category)

            # ── 2. Research ────────────────────────────────────────────────────
            candidate_result = research(candidate.category, candidate.common_name)
            if candidate_result is None:
                # Botanical without Uses section – pick another
                log.warning(
                    "Skipping '%s' (botanical validation failed). Trying again…",
                    candidate.common_name,
                )
                continue

            # ── 3. Require a reviewer-approved photo, else pick another ─────────
            candidate_selection = _find_good_photo(candidate_result, candidate.common_name)
            if candidate_selection is None:
                # No usable photo — exclude this species from future random
                # selection so we don't keep rediscovering it has no good image.
                mark_rejected(candidate)
                log.warning(
                    "Skipping '%s' – no good photo available. Trying another species…",
                    candidate.common_name,
                )
                continue

            selection = candidate
            result = candidate_result
            selection_result = candidate_selection
            break

        if selection is None or result is None or selection_result is None:
            log.error(
                "Could not find a species with a good photo after %d attempts. "
                "Aborting.", MAX_TRIES,
            )
            sys.exit(1)

    # ── 4. Use the chosen photo (reviewer-approved, or first if review off) ────
    best_photo = selection_result.photo
    image_url = best_photo.url
    if selection_result.approved:
        log.info("Using %s photo (reviewer approved): %s", best_photo.source, image_url)
    else:
        log.info("Using %s photo (image review disabled): %s", best_photo.source, image_url)

    # Also save a local copy for reference / dry-run inspection
    try:
        download_image(image_url, out_dir / "source_image")
    except Exception as e:
        log.warning("Could not save local image copy: %s", e)

    # ── 4. Generate post copy ──────────────────────────────────────────────────
    content = generate_content(result, photo=best_photo)

    # ── 5. Generate the animated video (video mode only) ──────────────────────
    posting_result: dict = {}
    video: GeneratedVideo | None = None

    if mode == "video" and not dry_run:
        try:
            video = generate_video(
                image_url=image_url,
                prompt=content.video_prompt,
                output_path=out_dir / "tiktok_video.mp4",
            )
        except Exception as e:
            log.error("Video generation failed: %s", e)
            log.warning("Continuing without video – video posts will be skipped.")
            video = None

    # ── 6. Post to Instagram (photo, or Reel in video mode) ───────────────────
    if not dry_run and not no_post:
        try:
            if mode == "video":
                if video is None or not video.path.exists():
                    raise RuntimeError("video generation failed – nothing to post")
                # Upload the local file (soundscape muxed in), not the raw
                # silent WaveSpeed URL.
                ig_media_id = post_instagram_reel(
                    video_path=video.path,
                    caption=content.instagram_caption,
                )
            else:
                ig_media_id = post_instagram_photo(
                    image_url=image_url,
                    caption=content.instagram_caption,
                    alt_text=content.alt_text,
                )
            posting_result["instagram"] = {"status": "posted", "media_id": ig_media_id}
            log.info("Instagram: posted ✓ (%s, media_id=%s)", mode, ig_media_id)
        except Exception as e:
            log.error("Instagram posting failed: %s", e)
            posting_result["instagram"] = {"status": "failed", "error": str(e)}

    # ── 7. Post to TikTok (photo via PULL_FROM_URL, or video via FILE_UPLOAD) ──
    if not dry_run and not no_post and not no_tiktok:
        try:
            if mode == "video":
                if not (video and video.path.exists()):
                    raise RuntimeError("video generation failed – nothing to post")
                tt_publish_id = post_tiktok_video(
                    video_path=video.path,
                    caption=content.tiktok_caption,
                )
            else:
                tt_publish_id = post_tiktok_photo(
                    image_url=_tiktok_pull_url(image_url),
                    caption=content.tiktok_caption,
                )
            posting_result["tiktok"] = {"status": "posted", "publish_id": tt_publish_id}
            log.info("TikTok: posted ✓ (%s, publish_id=%s)", mode, tt_publish_id)
        except Exception as e:
            log.error("TikTok posting failed: %s", e)
            posting_result["tiktok"] = {"status": "failed", "error": str(e)}

    # ── 8. Save all outputs ────────────────────────────────────────────────────
    save_outputs(out_dir, selection, result, content, posting_result,
                 image_selection=selection_result)

    # ── 9. Mark as posted (only if at least one platform succeeded) ────────────
    if not dry_run and not no_post:
        statuses = {k: v.get("status") for k, v in posting_result.items()}
        if any(s == "posted" for s in statuses.values()):
            mark_posted(selection)

    # ── Done ───────────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Pipeline complete!")
    log.info("  Organism : %s (%s)", selection.common_name, result.scientific_name or "unknown")
    log.info("  Category : %s", selection.category)
    log.info("  Post type: %s", mode)
    if dry_run:
        log.info("  Mode     : DRY RUN – nothing posted, no media generated")
    elif no_post:
        log.info("  Mode     : NO-POST – nothing posted")
    else:
        for platform, res in posting_result.items():
            log.info("  %-12s: %s", platform.capitalize(), res.get("status", "?"))
        if no_tiktok:
            log.info("  %-12s: %s", "Tiktok", "skipped (--no-tiktok)")
    log.info("  Output   : %s", out_dir)
    log.info("=" * 60)


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Birds, Bugs & Botanicals – daily content pipeline"
    )
    parser.add_argument(
        "--category",
        choices=["bird", "bug", "botanical"],
        default=None,
        help="Force a specific category (default: random)",
    )
    parser.add_argument(
        "--species",
        default=None,
        metavar="NAME",
        help="Force a specific species by common name (e.g. --species \"Barn Owl\"). "
             "Category is inferred from the species pools; pass --category too if "
             "the species isn't in a pool.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip video generation AND posting (fast, cheap — for testing copy)",
    )
    parser.add_argument(
        "--no-post",
        action="store_true",
        help="Generate everything (incl. video in video mode) but skip posting",
    )
    parser.add_argument(
        "--mode",
        choices=["photo", "video"],
        default="photo",
        help="What to post to Instagram and TikTok: 'photo' (default, no video "
             "generation) or 'video' (generate and post the animated clip)",
    )
    parser.add_argument(
        "--no-tiktok",
        action="store_true",
        help="Skip posting to TikTok (e.g. while the TikTok app is still pending "
             "approval). Instagram posting is unaffected.",
    )
    args = parser.parse_args()

    run(category=args.category, dry_run=args.dry_run, no_post=args.no_post,
        species=args.species, mode=args.mode, no_tiktok=args.no_tiktok)
