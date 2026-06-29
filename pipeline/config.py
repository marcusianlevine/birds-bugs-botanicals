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

# ── Kling AI ───────────────────────────────────────────────────────────────────
KLING_API_KEY       = _require("KLING_API_KEY")
# KLING_API_SECRET is no longer used — Kling migrated to simple Bearer token auth
# in June 2026. Kept here as optional in case you need the legacy JWT flow.
KLING_API_SECRET    = _optional("KLING_API_SECRET")
# International endpoint (non-China). Override via KLING_BASE_URL if needed.
KLING_BASE_URL      = _optional("KLING_BASE_URL", "https://api-singapore.klingai.com")

# ── Instagram Graph API ────────────────────────────────────────────────────────
INSTAGRAM_ACCESS_TOKEN = _require("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID   = _require("INSTAGRAM_ACCOUNT_ID")
INSTAGRAM_GRAPH_URL    = "https://graph.instagram.com/v21.0"

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

# Kling video settings
KLING_VIDEO_DURATION = 5          # seconds (5 or 10)
KLING_VIDEO_RATIO    = "9:16"     # portrait for TikTok/Reels
KLING_POLL_INTERVAL  = 15         # seconds between status polls
KLING_POLL_TIMEOUT   = 600        # give up after 10 minutes

# iNaturalist quality grade for photo sourcing
INATURALIST_QUALITY  = "research"
INATURALIST_PER_PAGE = 10

# Categories and their daily probability weights
CATEGORIES = ["bird", "bug", "botanical"]
CATEGORY_WEIGHTS = [0.35, 0.35, 0.30]    # slight bias away from botanicals
                                           # (stricter filtering)
