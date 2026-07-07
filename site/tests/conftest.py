"""
conftest.py - shared setup for the site/api test suite.

Sets placeholder credentials so importing pipeline/config.py (transitively,
via generate.py -> research.py/content_generator.py) doesn't fail its
required-key checks at import time. No real network or LLM calls happen in
this suite - every external call (OpenAI, TikTok, requests.get/post) is
mocked at the point of use in the individual tests.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("OLLAMA_API_KEY", "test-placeholder")
os.environ.setdefault("TIKTOK_CLIENT_KEY", "test-placeholder")
os.environ.setdefault("TIKTOK_CLIENT_SECRET", "test-placeholder")

SITE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE_DIR / "api" / "_lib"))
