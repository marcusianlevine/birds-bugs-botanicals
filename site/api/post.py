"""
/api/post – publish generated content to TikTok as a photo post.

Uses TikTok's Content Posting API v2 (/v2/post/publish/content/init/) with
source PULL_FROM_URL, pointed at our own /api/photo-proxy so TikTok fetches
the image from our verified domain rather than the original Wikipedia/
iNaturalist/eBird source. post_mode is MEDIA_UPLOAD (sends to the TikTok
inbox for the account owner to review and finish publishing in-app) rather
than DIRECT_POST, since DIRECT_POST requires separate approval from TikTok
that this app doesn't have yet.

Requires an active TikTok session (see /api/auth/tiktok/login) and the
shared admin password (see _lib/webauth.py).
"""

import sys
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from webauth import check_admin_password  # noqa: E402

app = Flask(__name__)

CONTENT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/content/init/"


@app.route("/api/post", methods=["POST"])
def post_to_tiktok():
    if not check_admin_password(request.headers.get("X-Admin-Password")):
        return jsonify({"error": "Unauthorized."}), 401

    access_token = request.cookies.get("tt_access_token", "")
    if not access_token:
        return jsonify({
            "error": "Not connected to TikTok yet. Click “Connect TikTok” first."
        }), 401

    data = request.get_json(silent=True) or {}
    photo_url = (data.get("photo_url") or "").strip()
    caption = (data.get("caption") or "").strip()

    if not photo_url or not caption:
        return jsonify({"error": "photo_url and caption are required."}), 400

    base_url = request.url_root.rstrip("/")
    proxied_photo_url = f"{base_url}/api/photo-proxy?src={quote(photo_url, safe='')}"

    payload = {
        "post_info": {
            "title": caption[:90],
            "description": caption[:4000],
            "disable_comment": False,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": [proxied_photo_url],
        },
        "post_mode": "MEDIA_UPLOAD",
        "media_type": "PHOTO",
    }

    try:
        resp = requests.post(
            CONTENT_INIT_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            timeout=30,
        )
        body = resp.json()
    except (requests.RequestException, ValueError) as e:
        return jsonify({"error": f"TikTok request failed: {e}"}), 502

    error = body.get("error", {}) or {}
    if error.get("code") not in (None, "ok"):
        return jsonify({
            "error": f"TikTok API error [{error.get('code')}]: {error.get('message')}"
        }), 502

    return jsonify({
        "status": "sent_to_tiktok",
        "publish_id": (body.get("data") or {}).get("publish_id"),
        "note": (
            "Sent to TikTok. Until this app is approved for direct posting, "
            "it lands in the account's TikTok inbox/drafts to review and "
            "finish publishing from the TikTok app."
        ),
    })
