"""
tests/conftest.py — setup for the fast, deterministic unit tests.

Unlike the eval suite (which exercises the LLM and needs real API keys and/or a
saved fixture), these tests cover pure logic — species selection, discovery
filtering, attribution formatting, and the soundscape muxing guards — with no
network or API calls.

config.py calls _require() on a few credentials at import time, so we set dummy
values here (before any pipeline module is imported) so the modules import
cleanly in CI without real secrets.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("OLLAMA_API_KEY", "test-key")
os.environ.setdefault("TIKTOK_CLIENT_KEY", "test-client-key")
os.environ.setdefault("TIKTOK_CLIENT_SECRET", "test-client-secret")

# Make the pipeline modules (species_selector, research, …) importable.
sys.path.insert(0, str(Path(__file__).parent.parent))
