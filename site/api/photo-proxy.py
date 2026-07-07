"""
/api/photo-proxy – re-serve a source photo from our own verified domain.

TikTok's Content Posting API (PULL_FROM_URL) will only fetch photos from a
domain/URL prefix you've verified in the TikTok developer portal. Our source
photos come from Wikipedia/iNaturalist/eBird, which we obviously can't
verify ownership of — so this endpoint re-serves the chosen photo's bytes
from our own domain instead, and TikTok pulls from here.

Deliberately unauthenticated (TikTok's servers need to fetch it directly),
so it's locked to an allow-list of the exact hosts our research pipeline
ever sources photos from (see _lib/webauth.py) to prevent it being used as
an open image proxy.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, Response, request

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from webauth import is_allowed_photo_host  # noqa: E402

app = Flask(__name__)


@app.route("/api/photo-proxy", methods=["GET"])
def photo_proxy():
    src = request.args.get("src", "")
    if not src:
        return "Missing src query param.", 400

    hostname = urlparse(src).hostname or ""
    if not is_allowed_photo_host(hostname):
        return "Host not allowed.", 400

    try:
        upstream = requests.get(src, timeout=20, stream=True)
        upstream.raise_for_status()
    except requests.RequestException as e:
        return f"Upstream fetch failed: {e}", 502

    content_type = upstream.headers.get("content-type", "image/jpeg")
    return Response(
        upstream.content,
        mimetype=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
