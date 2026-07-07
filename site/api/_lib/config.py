"""
config.py – trimmed settings for the web app's content-generation path.

This is a deliberately smaller copy of pipeline/config.py: the web app only
ever calls research() + select_best_photo() + generate_content() (no video,
no Instagram, no long-lived TikTok token), so only the settings those
functions actually touch are required here. Everything else degrades
gracefully instead of raising at import time, since Vercel's environment
won't have (and doesn't need) secrets for integrations the web UI never
calls.
"""

import os
from pathlib import Path


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key} "
            f"(set it in the Vercel project's Environment Variables)."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


# ── Ollama (OpenAI-compatible cloud endpoint) – required for content/vision ────
OLLAMA_API_KEY  = _require("OLLAMA_API_KEY")
OLLAMA_BASE_URL = _optional("OLLAMA_BASE_URL", "https://api.ollama.com/v1")
OLLAMA_MODEL    = _optional("OLLAMA_MODEL", "llama3.3")

# ── eBird – optional (birds-only photo/range lookup, best-effort already) ──────
EBIRD_API_KEY = _optional("EBIRD_API_KEY")

# ── Data directory (bundled alongside this file, not the CLI pipeline's) ──────
DATA_DIR = Path(__file__).parent / "data"

# iNaturalist quality grade for photo sourcing
INATURALIST_QUALITY  = "research"
INATURALIST_PER_PAGE = 10

# ── Image review (vision LLM) ──────────────────────────────────────────────────
IMAGE_REVIEW_ENABLED = _optional("IMAGE_REVIEW_ENABLED", "true").lower() == "true"
VISION_MODEL = _optional("VISION_MODEL", OLLAMA_MODEL)
IMAGE_REVIEW_MAX_CANDIDATES = int(_optional("IMAGE_REVIEW_MAX_CANDIDATES", "6"))
IMAGE_REVIEW_MIN_SCORE = int(_optional("IMAGE_REVIEW_MIN_SCORE", "7"))

# Retry settings for image downloads (exponential backoff on transient errors).
IMAGE_PULL_MAX_ATTEMPTS = int(_optional("IMAGE_PULL_MAX_ATTEMPTS", "3"))
IMAGE_PULL_BACKOFF_BASE = float(_optional("IMAGE_PULL_BACKOFF_BASE", "1.0"))
