"""
tiktok_auth.py – CLI OAuth 2.0 login flow for TikTok Content Posting API.

Usage:
    python tiktok_auth.py                   # prints token
    python tiktok_auth.py --save-env        # also writes TIKTOK_ACCESS_TOKEN to .env

Prerequisites:
    • Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET in .env (or export them)
    • Add http://localhost:8080/callback as a redirect URI in your TikTok app
      at https://developers.tiktok.com → your app → Login Kit → Redirect URI

Scopes requested: video.publish, video.upload
"""

import argparse
import base64
import hashlib
import http.server
import os
import re
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── TikTok OAuth endpoints ────────────────────────────────────────────────────
AUTH_URL  = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

REDIRECT_URI = "http://localhost:8080/callback"
SCOPES       = "video.publish,video.upload"


# ── Local callback server ─────────────────────────────────────────────────────

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Catches a single OAuth redirect and stores the query params."""

    result: dict = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        _CallbackHandler.result = params

        if "error" in params:
            body = f"<h2>Auth error: {params['error']}</h2><p>{params.get('error_description', '')}</p>"
        elif "code" in params:
            body = "<h2>Authorised ✓</h2><p>You can close this tab and return to the terminal.</p>"
        else:
            body = "<h2>Unexpected response</h2>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *_):
        pass   # silence access log


def _wait_for_callback(timeout: int = 120) -> dict:
    """Start a one-shot local server and block until the callback arrives."""
    server = http.server.HTTPServer(("localhost", 8080), _CallbackHandler)
    server.timeout = timeout

    timer = threading.Timer(timeout, server.shutdown)
    timer.start()
    try:
        server.handle_request()   # blocks until one request arrives
    finally:
        timer.cancel()
        server.server_close()

    return _CallbackHandler.result


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier  = secrets.token_urlsafe(64)          # 86 URL-safe chars
    digest    = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def _build_auth_url(client_key: str, state: str, code_challenge: str) -> str:
    params = {
        "client_key":            client_key,
        "response_type":         "code",
        "scope":                 SCOPES,
        "redirect_uri":          REDIRECT_URI,
        "state":                 state,
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def _exchange_code(client_key: str, client_secret: str, code: str, code_verifier: str) -> dict:
    """Exchange authorisation code for an access token (PKCE)."""
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key":     client_key,
            "client_secret":  client_secret,
            "code":           code,
            "grant_type":     "authorization_code",
            "redirect_uri":   REDIRECT_URI,
            "code_verifier":  code_verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"Token exchange failed: {body}")
    return body.get("data", body)


# ── .env writer ───────────────────────────────────────────────────────────────

def _save_to_env(token: str, refresh_token: str | None) -> None:
    env_path = Path(__file__).parent / ".env"

    if not env_path.exists():
        print(f"\n⚠  No .env found at {env_path} — create one first.")
        return

    text = env_path.read_text(encoding="utf-8")

    def _replace_or_append(key: str, value: str, content: str) -> str:
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        new, n = re.subn(pattern, replacement, content, flags=re.MULTILINE)
        if n == 0:
            new = content.rstrip("\n") + f"\n{replacement}\n"
        return new

    text = _replace_or_append("TIKTOK_ACCESS_TOKEN", token, text)
    if refresh_token:
        text = _replace_or_append("TIKTOK_REFRESH_TOKEN", refresh_token, text)

    env_path.write_text(text, encoding="utf-8")
    print(f"\n✓  Saved TIKTOK_ACCESS_TOKEN to {env_path}")
    if refresh_token:
        print(f"✓  Saved TIKTOK_REFRESH_TOKEN to {env_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok OAuth login (CLI)")
    parser.add_argument(
        "--save-env",
        action="store_true",
        help="Write the access token directly to .env after a successful login",
    )
    args = parser.parse_args()

    client_key    = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")

    if not client_key or not client_secret:
        print("Error: TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    state                    = secrets.token_urlsafe(16)
    code_verifier, challenge = _pkce_pair()
    auth_url                 = _build_auth_url(client_key, state, challenge)

    print("\n── TikTok OAuth Login ──────────────────────────────────────────")
    print(f"  client_key:   {client_key!r}")
    print(f"  Scopes:       {SCOPES}")
    print(f"  Redirect URI: {REDIRECT_URI}")
    print()
    print("Opening your browser… If it doesn't open, paste this URL manually:")
    print(f"\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for callback on http://localhost:8080/callback …")
    params = _wait_for_callback(timeout=120)

    if not params:
        print("\nError: timed out waiting for the OAuth callback (120 s).")
        sys.exit(1)

    if "error" in params:
        print(f"\nError from TikTok: {params['error']} — {params.get('error_description', '')}")
        sys.exit(1)

    if params.get("state") != state:
        print("\nError: state mismatch — possible CSRF. Aborting.")
        sys.exit(1)

    code = params.get("code")
    if not code:
        print(f"\nError: no code in callback params: {params}")
        sys.exit(1)

    print("Exchanging authorisation code for access token…")
    token_data = _exchange_code(client_key, client_secret, code, code_verifier)

    access_token  = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    open_id       = token_data.get("open_id")
    expires_in    = token_data.get("expires_in")

    print("\n── Success ─────────────────────────────────────────────────────")
    print(f"  access_token:  {access_token}")
    if refresh_token:
        print(f"  refresh_token: {refresh_token}")
    if open_id:
        print(f"  open_id:       {open_id}")
    if expires_in:
        days = int(expires_in) // 86400
        print(f"  expires_in:    {expires_in} s (~{days} days)")
    print()
    print("Add this to your .env:")
    print(f"  TIKTOK_ACCESS_TOKEN={access_token}")

    if args.save_env:
        _save_to_env(access_token, refresh_token)


if __name__ == "__main__":
    main()
