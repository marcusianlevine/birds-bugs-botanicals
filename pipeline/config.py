"""
config.py – centralised settings for the BBB content pipeline.
All credentials are read from environment variables (load your .env first).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv(Path(__file__).parent / ".env")

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"See .env.example for setup instructions."
        )
    return val

def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)

# ── Ollama (OpenAI-compatible cloud endpoint) ──────────────────────────────────
OLLAMA_API_KEY   = _require("OLLAMA_API_KEY")
OLLAMA_BASE_URL  = _optional("OLLAMA_BASE_URL", "https://api.ollama.com/v1")
OLLAMA_MODEL     = _optional("OLLAMA_MODEL", "llama3.3")

# ── WaveSpeed AI ──────────────────────────────────────────────────────────────
# Get your API key at https://wavespeed.ai/settings/api-keys
# The SDK reads WAVESPEED_API_KEY automatically from the environment.
WAVESPEED_API_KEY = _require("WAVESPEED_API_KEY")

# ── Instagram Graph API ────────────────────────────────────────────────────────
INSTAGRAM_ACCESS_TOKEN = _require("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID   = _require("INSTAGRAM_ACCOUNT_ID")
INSTAGRAM_GRAPH_URL    = "https://graph.facebook.com/v21.0"

# ── TikTok ─────────────────────────────────────────────────────────────────────
TIKTOK_ACCESS_TOKEN  = _require("TIKTOK_ACCESS_TOKEN")
TIKTOK_CLIENT_KEY    = _require("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = _require("TIKTOK_CLIENT_SECRET")
TIKTOK_BASE_URL      = "https://open.tiktokapis.com/v2"

# ── eBird ──────────────────────────────────────────────────────────────────────
EBIRD_API_KEY = _require("EBIRD_API_KEY")

# ── Pipeline settings ──────────────────────────────────────────────────────────
OUTPUT_DIR = Path(_optional("OUTPUT_DIR", str(Path(__file__).parent / "output")))
DATA_DIR   = Path(__file__).parent / "data"

# History file – tracks every species ever posted to avoid repeats
HISTORY_FILE = DATA_DIR / "posted_history.json"

# WaveSpeed video settings
# Model — wan-2.1 is the documented image-to-video model; swap to a newer
# wavespeed-ai/* model string here without touching any other code.
WAVESPEED_MODEL          = _optional("WAVESPEED_MODEL", "alibaba/wan-2.7/image-to-video")
WAVESPEED_VIDEO_RESOLUTION = _optional("WAVESPEED_VIDEO_RESOLUTION", "720p")  # 720p or 1080p
WAVESPEED_VIDEO_DURATION = int(_optional("WAVESPEED_VIDEO_DURATION", "5"))
WAVESPEED_POLL_INTERVAL  = float(_optional("WAVESPEED_POLL_INTERVAL", "3.0"))
WAVESPEED_TIMEOUT        = int(_optional("WAVESPEED_TIMEOUT", "600"))

# iNaturalist quality grade for photo sourcing
INATURALIST_QUALITY  = "research"
INATURALIST_PER_PAGE = 10

# ── Image review (vision LLM) ──────────────────────────────────────────────────
# An LLM inspects each candidate photo and rejects any that isn't a clear,
# high-quality image with the organism clearly visible. Candidates are tried in
# source order (Wikipedia → iNaturalist → eBird) until one is approved.
IMAGE_REVIEW_ENABLED = _optional("IMAGE_REVIEW_ENABLED", "true").lower() == "true"
# Vision-capable model served by the OpenAI-compatible endpoint. Must accept
# image input (e.g. "llama3.2-vision"); defaults to the main model.
VISION_MODEL = _optional("VISION_MODEL", OLLAMA_MODEL)
# Cap how many candidates we spend a vision call on before giving up.
IMAGE_REVIEW_MAX_CANDIDATES = int(_optional("IMAGE_REVIEW_MAX_CANDIDATES", "6"))
# Minimum score (1-10) for a photo to be approved.
IMAGE_REVIEW_MIN_SCORE = int(_optional("IMAGE_REVIEW_MIN_SCORE", "7"))

# Retry settings for image downloads (exponential backoff on transient errors).
IMAGE_PULL_MAX_ATTEMPTS  = int(_optional("IMAGE_PULL_MAX_ATTEMPTS", "3"))
IMAGE_PULL_BACKOFF_BASE  = float(_optional("IMAGE_PULL_BACKOFF_BASE", "1.0"))

# Categories and their daily probability weights
CATEGORIES = ["bird", "bug", "botanical"]
CATEGORY_WEIGHTS = [0.35, 0.35, 0.30]    # slight bias away from botanicals
                                           # (stricter filtering)
