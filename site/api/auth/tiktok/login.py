"""
/api/auth/tiktok/login – start the TikTok OAuth (PKCE) flow.

Redirects the browser to TikTok's consent screen. TikTok redirects back to
/api/auth/tiktok/callback with an authorization code, which is exchanged for
an access token there.

Mirrors pipeline/tiktok_auth.py's CLI flow, adapted for a real redirect URI
instead of a localhost callback server.
"""

import base64
import hashlib
import os
import secrets
import urllib.parse

from flask import Flask, make_response, redirect, request

app = Flask(__name__)

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
SCOPES = "user.info.basic,video.publish"

# Cookies scoped to this path so they're only ever sent between the two
# OAuth endpoints, not on every request to the app.
_COOKIE_PATH = "/api/auth/tiktok"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _redirect_uri() -> str:
    # Prefer an explicit override (useful if the app sits behind a proxy/
    # custom domain Vercel doesn't see directly); otherwise derive it from
    # the incoming request.
    return os.environ.get("TIKTOK_REDIRECT_URI") or (
        request.url_root.rstrip("/") + "/api/auth/tiktok/callback"
    )


@app.route("/api/auth/tiktok/login", methods=["GET"])
def tiktok_login():
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    if not client_key:
        return "TIKTOK_CLIENT_KEY is not configured.", 500

    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()

    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": _redirect_uri(),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    resp = make_response(redirect(auth_url))
    resp.set_cookie("tt_state", state, httponly=True, secure=True,
                     samesite="Lax", max_age=600, path=_COOKIE_PATH)
    resp.set_cookie("tt_verifier", verifier, httponly=True, secure=True,
                     samesite="Lax", max_age=600, path=_COOKIE_PATH)
    return resp
