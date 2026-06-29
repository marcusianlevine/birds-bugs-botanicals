"""
evals/judge.py - LLM-as-judge quality scoring via Ollama's OpenAI-compatible API.

Scores generated content on four dimensions, using example_posts.json
as reference for tone and style calibration.

Each dimension is scored 1-5 with a short rationale.
"""

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

log = logging.getLogger(__name__)

client = OpenAI(api_key=config.OLLAMA_API_KEY, base_url=config.OLLAMA_BASE_URL)

EXAMPLES_FILE = config.DATA_DIR / "example_posts.json"

DIMENSIONS = {
    "tone": (
        "Warm, curious and wonder-filled — like a knowledgeable friend sharing "
        "something they're genuinely excited about. NOT academic, NOT dry, NOT "
        "promotional. The reader should feel invited into nature, not lectured at."
    ),
    "engagement": (
        "Compelling opening line, interesting facts woven naturally into the prose "
        "(not bullet-listed), clear call-to-action, likely to generate comments or saves."
    ),
    "accuracy": (
        "Facts stated are plausible and consistent with the research data provided. "
        "No obvious errors, exaggerations, or made-up statistics."
    ),
    "style_match": (
        "Matches the voice, rhythm, and structure of the golden example posts — "
        "same paragraph length, similar hook style, same hashtag placement convention."
    ),
}


@dataclass
class DimensionScore:
    dimension: str
    score: int          # 1-5
    rationale: str

    def __str__(self):
        bar = "█" * self.score + "░" * (5 - self.score)
        return f"  {self.dimension:<14} [{bar}] {self.score}/5  {self.rationale}"


@dataclass
class JudgeReport:
    post_type: str      # "instagram" or "tiktok"
    category: str
    species: str
    scores: list[DimensionScore]
    overall: float      # mean score
    summary: str

    def passed(self, threshold: float = 3.5) -> bool:
        return self.overall >= threshold

    def __str__(self):
        lines = [
            f"\nJudge report — {self.post_type} / {self.category} / {self.species}",
            f"Overall: {self.overall:.1f}/5.0  ({'PASS' if self.passed() else 'FAIL'})",
            "",
        ]
        for s in self.scores:
            lines.append(str(s))
        lines += ["", f"Summary: {self.summary}"]
        return "\n".join(lines)


def _load_examples(category: str, post_type: str = "instagram") -> list[dict]:
    """Return golden examples filtered by category and post type."""
    with open(EXAMPLES_FILE) as f:
        data = json.load(f)
    examples = data.get(post_type, [])
    # Prefer same-category examples; fall back to all examples
    same_cat = [e for e in examples if e.get("category") == category]
    return same_cat if same_cat else examples


def _build_judge_prompt(
    post_type: str,
    category: str,
    species: str,
    content: str,
    research_summary: str,
    examples: list[dict],
) -> str:
    example_block = ""
    for i, ex in enumerate(examples[:2], 1):
        field = "caption" if post_type == "instagram" else "caption"
        example_block += f"\n--- Example {i} ({ex.get('species', '?')}) ---\n{ex.get(field, '')}\n"
        if ex.get("notes"):
            example_block += f"[Why it works: {ex['notes']}]\n"

    dimension_block = "\n".join(
        f'  "{dim}": {desc}' for dim, desc in DIMENSIONS.items()
    )

    return f"""You are a social media content quality reviewer for "Birds, Bugs & Botanicals",
a nature account that posts daily facts about wildlife and plants.

Your job: score a piece of generated content on four dimensions, using the golden
example posts below as your style and tone reference.

=== GOLDEN EXAMPLES (reference standard) ===
{example_block}

=== CONTENT TO EVALUATE ===
Post type: {post_type}
Category:  {category}
Species:   {species}

{content}

=== RESEARCH DATA USED TO GENERATE THIS POST ===
{research_summary[:600]}

=== SCORING DIMENSIONS ===
Score each dimension 1-5 (1=poor, 3=acceptable, 5=excellent):
{dimension_block}

Respond in this EXACT JSON format (no markdown fences, no extra text):
{{
  "tone":        {{"score": <1-5>, "rationale": "<one sentence>"}},
  "engagement":  {{"score": <1-5>, "rationale": "<one sentence>"}},
  "accuracy":    {{"score": <1-5>, "rationale": "<one sentence>"}},
  "style_match": {{"score": <1-5>, "rationale": "<one sentence>"}},
  "summary":     "<two sentences: what works well and what could be improved>"
}}"""


def _parse_judge_response(raw: str, post_type: str, category: str, species: str) -> JudgeReport:
    data = json.loads(raw.strip())
    scores = []
    for dim in DIMENSIONS:
        entry = data.get(dim, {})
        scores.append(DimensionScore(
            dimension=dim,
            score=int(entry.get("score", 3)),
            rationale=entry.get("rationale", ""),
        ))
    overall = sum(s.score for s in scores) / len(scores)
    return JudgeReport(
        post_type=post_type,
        category=category,
        species=species,
        scores=scores,
        overall=round(overall, 2),
        summary=data.get("summary", ""),
    )


def judge_instagram(
    caption: str,
    category: str,
    species: str,
    research_summary: str = "",
) -> JudgeReport:
    examples = _load_examples(category, "instagram")
    prompt = _build_judge_prompt(
        post_type="instagram",
        category=category,
        species=species,
        content=caption,
        research_summary=research_summary,
        examples=examples,
    )
    log.info("Running LLM judge for Instagram caption (%s)...", species)
    msg = client.chat.completions.create(
        model=config.OLLAMA_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_judge_response(msg.choices[0].message.content,"instagram", category, species)


def judge_tiktok(
    script: str,
    caption: str,
    category: str,
    species: str,
    research_summary: str = "",
) -> JudgeReport:
    combined = f"VOICEOVER:\n{script}\n\nCAPTION:\n{caption}"
    examples = _load_examples(category, "tiktok")
    prompt = _build_judge_prompt(
        post_type="tiktok",
        category=category,
        species=species,
        content=combined,
        research_summary=research_summary,
        examples=examples,
    )
    log.info("Running LLM judge for TikTok content (%s)...", species)
    msg = client.chat.completions.create(
        model=config.OLLAMA_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_judge_response(msg.choices[0].message.content,"tiktok", category, species)
