"""
/api/auth/tiktok/callback – exchange the OAuth code for an access token.

On success, stores the access token in an httpOnly cookie and redirects back
to /app. There's exactly one operator for this app, so the token is kept
server-side-only via the cookie rather than in a database — plenty for a
single-account tool, though it does mean re-authenticating from a new
browser/device requires clicking "Connect TikTok" again.
"""

import os

import requests
from flask import Flask, make_response, redirect, request

app = Flask(__name__)

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_COOKIE_PATH = "/api/auth/tiktok"


def _redirect_uri() -> str:
    return os.environ.get("TIKTOK_REDIRECT_URI") or (
        request.url_root.rstrip("/") + "/api/auth/tiktok/callback"
    )


def _clear_pkce_cookies(resp):
    resp.set_cookie("tt_state", "", max_age=0, path=_COOKIE_PATH)
    resp.set_cookie("tt_verifier", "", max_age=0, path=_COOKIE_PATH)


@app.route("/api/auth/tiktok/callback", methods=["GET"])
def tiktok_callback():
    if request.args.get("error"):
        return redirect(f"/app?tiktok_error={request.args.get('error')}")

    state = request.args.get("state", "")
    code = request.args.get("code", "")
    cookie_state = request.cookies.get("tt_state", "")
    verifier = request.cookies.get("tt_verifier", "")

    if not code or not state or state != cookie_state:
        resp = make_response(redirect("/app?tiktok_error=state_mismatch"))
        _clear_pkce_cookies(resp)
        return resp

    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")

    try:
        token_resp = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _redirect_uri(),
                "code_verifier": verifier,
            },
            timeout=30,
        )
        token_data = token_resp.json()
    except (requests.RequestException, ValueError):
        resp = make_response(redirect("/app?tiktok_error=token_exchange_failed"))
        _clear_pkce_cookies(resp)
        return resp

    access_token = token_data.get("access_token")
    if not access_token:
        resp = make_response(redirect("/app?tiktok_error=no_access_token"))
        _clear_pkce_cookies(resp)
        return resp

    expires_in = int(token_data.get("expires_in") or 86400)

    resp = make_response(redirect("/app?tiktok_connected=1"))
    resp.set_cookie(
        "tt_access_token", access_token,
        httponly=True, secure=True, samesite="Lax",
        max_age=expires_in, path="/",
    )
    _clear_pkce_cookies(resp)
    return resp
