"""
content_generator.py – uses the Claude API to write post copy.

Generates:
  • instagram_caption  – engaging caption with 3-5 paragraphs + hashtags
  • tiktok_script      – voiceover script timed to the ~5-10 s video
  • tiktok_caption     – short TikTok caption + hashtags
  • video_prompt       – the Kling AI image-to-video prompt
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

import config
from research import ResearchResult

log = logging.getLogger(__name__)

client = OpenAI(api_key=config.OLLAMA_API_KEY, base_url=config.OLLAMA_BASE_URL)


# ── Hashtag helpers ────────────────────────────────────────────────────────────

def _load_hashtags() -> dict:
    with open(config.DATA_DIR / "hashtags.json") as f:
        return json.load(f)


def get_required_tags(category: str) -> list[str]:
    """Return the full ordered list of required tags: base + category-specific."""
    tags = _load_hashtags()
    return tags.get("base", []) + tags.get(category, [])


def ensure_hashtags(text: str, required_tags: list[str]) -> str:
    """
    Append any required hashtags that are missing from text.
    Comparison is case-insensitive and ignores the leading #.
    """
    existing = {w.lstrip("#").lower() for w in text.split() if w.startswith("#")}
    missing = [t for t in required_tags if t.lstrip("#").lower() not in existing]
    if missing:
        text = text.rstrip() + "\n" + " ".join(missing)
    return text


@dataclass
class GeneratedContent:
    instagram_caption: str
    tiktok_script: str           # ~30-45 second narration
    tiktok_caption: str
    video_prompt: str            # sent to Kling AI
    alt_text: str                # accessibility description for the image


# ── Prompt builders ────────────────────────────────────────────────────────────

def _build_instagram_prompt(r: ResearchResult, required_tags: list[str]) -> str:
    facts_lines = "\n".join(f"- {f}" for f in r.fun_facts[:4]) if r.fun_facts else ""
    facts_block = ("Fun facts:\n" + facts_lines) if facts_lines else ""
    uses_block = ("\nUSES / MEDICINAL:\n" + r.uses_section[:600]) if r.uses_section else ""
    conservation = ("\nConservation status: " + r.conservation_status) if r.conservation_status else ""
    range_info = ("\nRange: " + r.range_description) if r.range_description else ""
    tag_hint = " ".join(required_tags)

    return f"""You are the social media writer for "Birds, Bugs & Botanicals" – a nature account
that posts daily facts about wildlife and plants. The content is factual, engaging, playful,
and inspires people to spend time in nature. Captions feel warm and wonder-filled, not academic.

Write an Instagram caption for today's feature organism. Requirements:
• Open with an attention-grabbing first line (no emojis to start, just a punchy sentence)
• 3-5 short paragraphs totalling 180-280 words
• Weave in 2-3 of the fun facts naturally – don't just list them
• End with a call to action (e.g., "Have you spotted one? Tell us below 👇")
• Close with 20-25 relevant hashtags on a separate line
• You MUST include ALL of these required tags in your hashtag block: {tag_hint}
• You may add further relevant species-specific tags alongside them
• Tone: curious, enthusiastic, educational but accessible

TODAY'S ORGANISM:
  Common name: {r.common_name}
  Scientific name: {r.scientific_name or "unknown"}
  Category: {r.category}
  Wikipedia summary: {r.wikipedia_summary[:800]}
{facts_block}{uses_block}{conservation}{range_info}

Output ONLY the caption text (no explanations, no "Here's your caption:" preamble).
"""


def _build_tiktok_prompt(r: ResearchResult, required_tags: list[str]) -> str:
    facts_lines = "\n".join(f"- {f}" for f in r.fun_facts[:3]) if r.fun_facts else ""
    facts_block = ("Fun facts:\n" + facts_lines) if facts_lines else ""
    uses_block = ("\nUSES:\n" + r.uses_section[:400]) if r.uses_section else ""
    tag_hint = " ".join(required_tags)

    return f"""You are writing for "Birds, Bugs & Botanicals" on TikTok. The account posts
short, soothing nature videos with a voiceover narration. Videos are 5-10 seconds of
animated footage, so the script must be SHORT and punchy.

Write TWO things:

1. VOICEOVER SCRIPT (max 4 sentences, ~45 words total):
   - Opens mid-action, as if the viewer just stumbled upon this creature or plant
   - Uses "you" language to pull the viewer in
   - Ends with one astonishing fact
   - Warm, gentle tone – like a knowledgeable friend, not a textbook

2. TIKTOK CAPTION (max 60 words + hashtags):
   - Punchy first line
   - 1-2 follow-up sentences
   - 10-15 hashtags
   - You MUST include ALL of these required tags: {tag_hint}

TODAY'S ORGANISM:
  Common name: {r.common_name}
  Scientific name: {r.scientific_name or "unknown"}
  Category: {r.category}
  Summary: {r.wikipedia_summary[:500]}
{facts_block}{uses_block}

Format your response exactly like this (use these exact headers):
VOICEOVER:
<script here>

CAPTION:
<caption here>
"""


def _static_video_prompt(r: ResearchResult) -> str:
    """Deterministic fallback prompt used if the dynamic (LLM) one fails."""
    category_style = {
        "bird": (
            "feathers shimmer, wings subtly flex, eyes blink slowly, "
            "the bird turns its head with awareness"
        ),
        "bug": (
            "wings fan open gently, antennae quiver, body sways slightly, "
            "legs shift with delicate micro-movements"
        ),
        "botanical": (
            "a gentle time-lapse: a bud swells and unfurls into bloom, "
            "leaves sway in a soft breeze, morning dew catches the light"
        ),
    }
    motion = category_style.get(r.category, "subtle natural movement")

    return (
        f"Cinematic nature documentary animation. "
        f"A stunning {r.common_name} ({r.category}) comes to life from a still photograph. "
        f"{motion}. "
        f"The background softly blurs with a shallow depth of field. "
        f"Golden hour lighting. Ultra high definition, photorealistic. "
        f"No text, no overlays, no sudden movements. "
        f"Camera: very slow gentle push-in, as if leaning in to look closer."
    )


# Category-specific guidance for the dynamic, research-driven video prompt.
_VIDEO_MOTION_GUIDANCE = {
    "bird": (
        "Animate 2-3 SPECIFIC behaviours this bird is genuinely known for (drawn "
        "from the research) — e.g. how it forages or feeds, a characteristic wing "
        "or tail flick, cocking its head to listen, preening, singing, or a "
        "courtship display. Keep every movement subtle and believable."
    ),
    "bug": (
        "Animate 2-3 SPECIFIC behaviours this insect is genuinely known for (drawn "
        "from the research) — e.g. fanning or flexing its wings, antennae probing "
        "the air, sipping nectar or pollinating a flower, a defensive or camouflage "
        "sway, or creeping along a stem. Delicate, micro-scale motion only."
    ),
    "botanical": (
        "Animate a gentle LIFECYCLE time-lapse so we glimpse the plant at different "
        "stages of life: e.g. a seed or bud swelling and unfurling, new leaves "
        "emerging, petals opening into full bloom and then a seed head forming, or a "
        "soft seasonal shift — smooth, dreamlike growth that begins from the plant "
        "exactly as shown in the photo."
    ),
}


def _build_video_prompt_request(r: ResearchResult) -> str:
    """LLM prompt that produces a species-tailored image-to-video prompt."""
    facts = "\n".join(f"- {f}" for f in r.fun_facts[:5]) if r.fun_facts else ""
    facts_block = (
        "Research notes (use these for accurate, species-specific behaviour):\n" + facts
    ) if facts else ""
    guidance = _VIDEO_MOTION_GUIDANCE.get(
        r.category, "Animate subtle, natural movement true to this organism."
    )

    return f"""You are writing an image-to-video prompt for "Birds, Bugs & Botanicals". A still
photograph of a {r.common_name} ({r.scientific_name or 'unknown'}), a {r.category}, will be
animated into a short (~5 second) soothing, cinematic nature clip.

Write ONE vivid, richly descriptive prompt (45-85 words) that brings the still to life:
• {guidance}
• Make it SPECIFIC to this species using the research below — not generic motion.
• The animation must begin from the exact pose/scene in the photo and stay physically plausible.
• Cinematic and photorealistic, shallow depth of field, soft golden-hour light, very slow gentle camera push-in.
• No text, no overlays, no captions, no people, no sudden movements or hard cuts.

TODAY'S ORGANISM:
  Common name: {r.common_name}
  Scientific name: {r.scientific_name or 'unknown'}
  Category: {r.category}
  Summary: {r.wikipedia_summary[:600]}
{facts_block}

Output ONLY the video prompt text — no preamble, no quotes, no explanation."""


def _sanitize_video_prompt(text: str, r: ResearchResult) -> str:
    """Clean up the model's video prompt; fall back to the static one if unusable."""
    cleaned = (text or "").strip()
    # Drop a leading label like "Prompt:" or "Video prompt:" first...
    for label in ("video prompt:", "prompt:"):
        if cleaned.lower().startswith(label):
            cleaned = cleaned[len(label):].strip()
    # ...then strip wrapping quotes the model may have added.
    cleaned = cleaned.strip('"').strip("'").strip()
    if len(cleaned) < 40:
        log.warning("Dynamic video prompt too short; using static fallback.")
        return _static_video_prompt(r)
    return cleaned


def _build_alt_text_prompt(r: ResearchResult) -> str:
    return (
        f"Write a concise, vivid alt-text description (1-2 sentences, max 125 chars) "
        f"for a high-quality nature photograph of a {r.common_name}. "
        f"Include key visual details (colour, pose, setting) for accessibility. "
        f"Output only the alt text, no quotes."
    )


# ── Main generator ─────────────────────────────────────────────────────────────

def generate_content(r: ResearchResult) -> GeneratedContent:
    """Call Claude to generate all post copy for the organism."""

    log.info("Generating content for: %s", r.common_name)

    required_tags = get_required_tags(r.category)
    log.debug("Required hashtags (%d): %s", len(required_tags), " ".join(required_tags))

    def _call(prompt: str) -> str:
        response = client.chat.completions.create(
            model=config.OLLAMA_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    # Instagram caption — ask Claude to include required tags, then guarantee them
    instagram_caption = _call(_build_instagram_prompt(r, required_tags))
    instagram_caption = ensure_hashtags(instagram_caption, required_tags)

    # TikTok voiceover + caption (single call, parsed from response)
    tiktok_raw = _call(_build_tiktok_prompt(r, required_tags))
    tiktok_script, tiktok_caption = _parse_tiktok_response(tiktok_raw)
    tiktok_caption = ensure_hashtags(tiktok_caption, required_tags)

    # Video prompt for the image-to-video model — dynamically tailored to the
    # species (specific behaviours for birds/bugs, a lifecycle time-lapse for
    # plants), with a deterministic fallback if the call fails.
    try:
        video_prompt = _sanitize_video_prompt(_call(_build_video_prompt_request(r)), r)
    except Exception as e:
        log.warning("Dynamic video prompt generation failed (%s); using static fallback.", e)
        video_prompt = _static_video_prompt(r)

    # Alt text
    alt_text = _call(_build_alt_text_prompt(r))

    return GeneratedContent(
        instagram_caption=instagram_caption,
        tiktok_script=tiktok_script,
        tiktok_caption=tiktok_caption,
        video_prompt=video_prompt,
        alt_text=alt_text,
    )


def _parse_tiktok_response(raw: str) -> tuple[str, str]:
    """Split the TikTok response into (voiceover_script, caption)."""
    script, caption = "", ""
    current = None
    lines = raw.split("\n")
    buf: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("VOICEOVER:"):
            if current == "caption":
                caption = "\n".join(buf).strip()
            current = "voiceover"
            buf = []
            remainder = line[line.upper().index("VOICEOVER:") + 10:].strip()
            if remainder:
                buf.append(remainder)
        elif stripped.upper().startswith("CAPTION:"):
            if current == "voiceover":
                script = "\n".join(buf).strip()
            current = "caption"
            buf = []
            remainder = line[line.upper().index("CAPTION:") + 8:].strip()
            if remainder:
                buf.append(remainder)
        else:
            buf.append(line)

    if current == "voiceover":
        script = "\n".join(buf).strip()
    elif current == "caption":
        caption = "\n".join(buf).strip()

    # Fallback: treat everything as script if parsing found no headers
    if not script and not caption:
        script = raw.strip()

    return script, caption