"""
image_reviewer.py – use a vision LLM to pick the best organism photo.

The research step gathers candidate photos in source-preference order
(Wikipedia → iNaturalist → eBird). This module shows each candidate to a
vision-capable LLM and asks whether it is a clear, high-quality image with the
organism clearly visible. It returns the first candidate that passes, falling
back to the highest-scoring one if none clears the bar.
"""

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from openai import OpenAI

import config
from net import get_with_retry
from research import Photo, ResearchResult

log = logging.getLogger(__name__)

client = OpenAI(api_key=config.OLLAMA_API_KEY, base_url=config.OLLAMA_BASE_URL)


# ── Verdict ────────────────────────────────────────────────────────────────────

@dataclass
class ImageVerdict:
    source: str
    url: str
    approved: bool
    score: int                 # 1-10 overall quality/suitability
    organism_visible: bool
    reason: str

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "url": self.url,
            "approved": self.approved,
            "score": self.score,
            "organism_visible": self.organism_visible,
            "reason": self.reason,
        }


@dataclass
class SelectionResult:
    photo: Optional[Photo]                 # chosen photo (None if no candidates)
    verdict: Optional[ImageVerdict]        # verdict for the chosen photo
    approved: bool                         # did the chosen photo clear the bar?
    reviews: list[dict] = field(default_factory=list)  # log of every review


# ── Image download ──────────────────────────────────────────────────────────────

def _download_data_url(url: str) -> Optional[str]:
    """Download an image and return it as a base64 data URL, or None on failure."""
    try:
        resp = get_with_retry(
            url,
            timeout=30,
            max_attempts=config.IMAGE_PULL_MAX_ATTEMPTS,
            backoff_base=config.IMAGE_PULL_BACKOFF_BASE,
        )
    except requests.RequestException as e:
        log.warning("Could not download candidate image %s after %d attempts: %s",
                    url, config.IMAGE_PULL_MAX_ATTEMPTS, e)
        return None

    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"
    b64 = base64.b64encode(resp.content).decode("ascii")
    return f"data:{content_type};base64,{b64}"


# ── Prompt + parsing ─────────────────────────────────────────────────────────────

def _build_review_prompt(r: ResearchResult) -> str:
    return (
        "You are a strict photo editor for a nature social-media account. "
        "You are shown ONE candidate photo that is meant to feature a "
        f"{r.common_name} ({r.scientific_name or 'unknown'}), a {r.category}.\n\n"
        "Judge whether this single image is suitable as the hero photo for a post. "
        "It qualifies only if ALL of these are true:\n"
        "  1. The intended organism is clearly the subject, and the organism is unambiguously visible in its natural habitat"
        "(not tiny, not obscured or cut-off, not just a habitat/landscape shot, not containing other species).\n"
        "  2. It is in sharp focus and high quality (not blurry, pixelated, dark, "
        "or low resolution).\n"
        "  3. It looks like a real, clean photograph — no watermarks, heavy text, "
        "collages, diagrams, illustrations, museum specimens, or maps.\n\n"
        "Respond with ONLY a JSON object, no other text:\n"
        '{"organism_visible": true/false, "score": <integer 1-10>, '
        '"approved": true/false, "reason": "<short explanation>"}\n'
        "score is overall suitability from 1 (unusable) to 10 (perfect hero shot)."
    )


def _parse_verdict(raw: str, photo: Photo) -> ImageVerdict:
    """Parse the model's JSON reply, tolerating extra prose around it."""
    data = {}
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = {}

    score = data.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0

    organism_visible = bool(data.get("organism_visible", False))
    reason = str(data.get("reason", "")).strip() or "no reason given"

    # Trust an explicit approval flag if present, otherwise derive it from the
    # score threshold and organism visibility.
    if "approved" in data:
        approved = bool(data["approved"])
    else:
        approved = organism_visible and score >= config.IMAGE_REVIEW_MIN_SCORE

    # Guard: never approve something the model says has no visible organism.
    if not organism_visible:
        approved = False

    return ImageVerdict(
        source=photo.source,
        url=photo.url,
        approved=approved,
        score=score,
        organism_visible=organism_visible,
        reason=reason,
    )


def review_photo(photo: Photo, r: ResearchResult) -> Optional[ImageVerdict]:
    """Run one candidate through the vision model. Returns None if it can't be reviewed."""
    data_url = _download_data_url(photo.url)
    if data_url is None:
        return None

    try:
        response = client.chat.completions.create(
            model=config.VISION_MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_review_prompt(r)},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        )
        raw = response.choices[0].message.content.strip()
    except Exception as e:
        log.warning("Vision review call failed for %s image: %s", photo.source, e)
        return None

    verdict = _parse_verdict(raw, photo)
    log.info(
        "Reviewed %s image – score=%d visible=%s approved=%s (%s)",
        photo.source, verdict.score, verdict.organism_visible,
        verdict.approved, verdict.reason,
    )
    return verdict


# ── Main entry point ─────────────────────────────────────────────────────────────

def select_best_photo(r: ResearchResult) -> SelectionResult:
    """
    Review candidate photos in source-preference order and return the first one
    that the vision LLM approves. If none is approved, fall back to the
    highest-scoring reviewed photo, then to the first candidate.
    """
    candidates = r.photos[: config.IMAGE_REVIEW_MAX_CANDIDATES]

    if not candidates:
        return SelectionResult(photo=None, verdict=None, approved=False, reviews=[])

    if not config.IMAGE_REVIEW_ENABLED:
        log.info("Image review disabled – using first candidate (%s).",
                 candidates[0].source)
        return SelectionResult(
            photo=candidates[0], verdict=None, approved=False, reviews=[]
        )

    reviews: list[dict] = []
    best_photo: Optional[Photo] = None
    best_verdict: Optional[ImageVerdict] = None

    for photo in candidates:
        verdict = review_photo(photo, r)
        if verdict is None:
            continue
        reviews.append(verdict.as_dict())

        if verdict.approved:
            log.info("Approved %s image (score %d).", photo.source, verdict.score)
            return SelectionResult(
                photo=photo, verdict=verdict, approved=True, reviews=reviews
            )

        if best_verdict is None or verdict.score > best_verdict.score:
            best_photo, best_verdict = photo, verdict

    # Nothing cleared the bar – use the best-scoring reviewed photo, or the first.
    if best_photo is not None:
        log.warning(
            "No candidate approved. Falling back to best-scoring %s image (score %d).",
            best_photo.source, best_verdict.score,
        )
        return SelectionResult(
            photo=best_photo, verdict=best_verdict, approved=False, reviews=reviews
        )

    log.warning("No candidate could be reviewed. Falling back to first candidate (%s).",
                candidates[0].source)
    return SelectionResult(
        photo=candidates[0], verdict=None, approved=False, reviews=reviews
    )
