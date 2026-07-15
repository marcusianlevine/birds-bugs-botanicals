"""
config.py - centralised settings for the BBB content pipeline.
All credentials are read from environment variables (load your .env first).

This module is imported by both the CLI pipeline (main.py) and the web app's
API functions (site/api/*.py, which add pipeline/ to sys.path rather than
keeping a separate copy). Every setting below is evaluated at import time, so
credentials that only some callers need (WaveSpeed, Instagram, a long-lived
TikTok token, eBird) are optional here and instead checked with a clear error
at the point of use (video_generator, social_media) - importing config
shouldn't hard-fail for a caller that only needs OLLAMA_API_KEY and the
TikTok app credentials, like the web app does.
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

# -- Ollama (OpenAI-compatible cloud endpoint) ----------------------------------
OLLAMA_API_KEY   = _require("OLLAMA_API_KEY")
OLLAMA_BASE_URL  = _optional("OLLAMA_BASE_URL", "https://ollama.com/v1")
OLLAMA_MODEL     = _optional("OLLAMA_MODEL", "gemma4")

# -- WaveSpeed AI ----------------------------------------------------------------
# Get your API key at https://wavespeed.ai/settings/api-keys
# The SDK reads WAVESPEED_API_KEY automatically from the environment.
# Optional here (only video_generator.py needs it - checked there with a
# clear error) so importing config doesn't require it for callers that never
# generate video, like the web app.
WAVESPEED_API_KEY = _optional("WAVESPEED_API_KEY")

# -- Instagram Graph API ----------------------------------------------------------
# Optional here for the same reason - only social_media.py's Instagram
# functions need these, checked there.
INSTAGRAM_ACCESS_TOKEN = _optional("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID   = _optional("INSTAGRAM_ACCOUNT_ID")
INSTAGRAM_GRAPH_URL    = "https://graph.facebook.com/v21.0"

# -- TikTok -----------------------------------------------------------------------
# TIKTOK_CLIENT_KEY/SECRET are the app's own credentials - required by both
# the CLI (tiktok_auth.py) and the web app's OAuth login. TIKTOK_ACCESS_TOKEN
# is a long-lived token used only by the CLI's social_media.post_tiktok_video;
# the web app gets a fresh token per session via OAuth instead, so this is
# optional here and checked at the point of use.
TIKTOK_ACCESS_TOKEN  = _optional("TIKTOK_ACCESS_TOKEN")
TIKTOK_CLIENT_KEY    = _require("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = _require("TIKTOK_CLIENT_SECRET")
TIKTOK_BASE_URL      = "https://open.tiktokapis.com/v2"

# -- eBird --------------------------------------------------------------------------
# Optional: research.py's eBird lookup is already best-effort (wrapped in
# try/except), so a missing key just means birds skip that photo source
# rather than the whole pipeline failing to import.
EBIRD_API_KEY = _optional("EBIRD_API_KEY")

# -- Pipeline settings ----------------------------------------------------------------
OUTPUT_DIR = Path(_optional("OUTPUT_DIR", str(Path(__file__).parent / "output")))
DATA_DIR   = Path(__file__).parent / "data"

# History file - tracks every species ever posted to avoid repeats
HISTORY_FILE = DATA_DIR / "posted_history.json"

# Rejected file - tracks species that were randomly selected but had no photo
# good enough to feature, so they're excluded from future random selection.
REJECTED_FILE = DATA_DIR / "rejected_species.json"

# When the automated picker exhausts a category (every species posted or
# rejected), it runs species discovery to add this many new species before
# falling back to recycling posted history.
DISCOVERY_REFILL_COUNT = int(_optional("DISCOVERY_REFILL_COUNT", "10"))

# WaveSpeed video settings
# Model - wan-2.1 is the documented image-to-video model; swap to a newer
# wavespeed-ai/* model string here without touching any other code.
WAVESPEED_MODEL          = _optional("WAVESPEED_MODEL", "alibaba/wan-2.7/image-to-video")
WAVESPEED_VIDEO_RESOLUTION = _optional("WAVESPEED_VIDEO_RESOLUTION", "720p")  # 720p or 1080p
WAVESPEED_VIDEO_DURATION = int(_optional("WAVESPEED_VIDEO_DURATION", "5"))
WAVESPEED_POLL_INTERVAL  = float(_optional("WAVESPEED_POLL_INTERVAL", "3.0"))
WAVESPEED_TIMEOUT        = int(_optional("WAVESPEED_TIMEOUT", "600"))

# -- Soundscapes -----------------------------------------------------------------
# WaveSpeed clips are silent; after each video is generated we mux one of the
# pre-generated nature soundscapes in audio/ onto it (chosen at random), trimmed
# to the video length with a short fade-out. Best-effort: if ffmpeg is missing or
# no audio files are present, the pipeline logs a warning and keeps the silent video.
AUDIO_DIR                = Path(_optional("AUDIO_DIR", str(Path(__file__).parent / "audio")))
SOUNDSCAPE_ENABLED       = _optional("SOUNDSCAPE_ENABLED", "true").lower() == "true"
SOUNDSCAPE_AUDIO_BITRATE = _optional("SOUNDSCAPE_AUDIO_BITRATE", "192k")
SOUNDSCAPE_FADE_OUT      = float(_optional("SOUNDSCAPE_FADE_OUT", "1.0"))  # seconds

# iNaturalist quality grade for photo sourcing
INATURALIST_QUALITY  = "research"
INATURALIST_PER_PAGE = 10

# -- Image review (vision LLM) ---------------------------------------------------
# An LLM inspects each candidate photo and rejects any that isn't a clear,
# high-quality image with the organism clearly visible. Candidates are tried in
# source order (Wikipedia -> iNaturalist -> eBird) until one is approved.
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
