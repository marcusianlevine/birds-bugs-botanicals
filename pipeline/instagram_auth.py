"""
instagram_auth.py – Instagram Graph API token management.

The Instagram Graph API uses User Access Tokens that last 60 days.
This script handles two operations:

  --exchange   Exchange a short-lived token (valid ~1 hour, copied from the
               Facebook developer portal) for a long-lived token (valid 60 days).
               Saves the token to .env and prints the expiry date.

  --refresh    Refresh an existing long-lived token before it expires.
               Long-lived tokens can be refreshed any time after they are at
               least 24 hours old, as long as they have not yet expired.
               Updates INSTAGRAM_ACCESS_TOKEN in .env.

Prerequisites
-------------
  1. Facebook App with the Instagram product (Graph API) added.
  2. App must have these permissions approved:
       instagram_basic, instagram_content_publish,
       pages_read_engagement, pages_show_list
  3. For --exchange: generate a short-lived User Token in the
     Facebook Graph API Explorer (https://developers.facebook.com/tools/explorer/)
     with the permissions above, then paste it when prompted.

Environment variables read / written
-------------------------------------
  INSTAGRAM_APP_ID          Facebook App ID (from App Dashboard)
  INSTAGRAM_APP_SECRET      Facebook App Secret (from App Dashboard)
  INSTAGRAM_ACCESS_TOKEN    Long-lived User Access Token (written/updated here)
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(ENV_FILE)

GRAPH_BASE = "https://graph.facebook.com/v21.0"


# ── helpers ───────────────────────────────────────────────────────────────────

def _require_env(key: str) -> str:
    val = os.getenv(key)
    if not val:
        sys.exit(
            f"ERROR: {key} is not set in your .env file.\n"
            "Add it and try again. See .env.example for details."
        )
    return val


def _update_env(key: str, value: str) -> None:
    """Write or update a key=value line in .env (creates file if missing)."""
    content = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(content):
        content = pattern.sub(new_line, content)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    ENV_FILE.write_text(content)
    print(f"  ✓ Saved {key} to .env")


def _check_response(resp: requests.Response) -> dict:
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        sys.exit(f"ERROR: Facebook API returned {resp.status_code}:\n{resp.text}")
    body = resp.json()
    if "error" in body:
        err = body["error"]
        sys.exit(f"ERROR: Facebook API error [{err.get('code')}]: {err.get('message')}")
    return body


def _expiry_message(expires_in_seconds: int) -> str:
    expiry = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in_seconds)
    return expiry.strftime("%Y-%m-%d %H:%M UTC")


# ── exchange: short-lived → long-lived ───────────────────────────────────────

def exchange_token(short_lived_token: str) -> None:
    """Exchange a short-lived token for a long-lived one and save to .env."""
    app_id     = _require_env("INSTAGRAM_APP_ID")
    app_secret = _require_env("INSTAGRAM_APP_SECRET")

    print("Exchanging short-lived token for a long-lived token...")
    resp = requests.get(
        f"{GRAPH_BASE}/oauth/access_token",
        params={
            "grant_type":        "fb_exchange_token",
            "client_id":         app_id,
            "client_secret":     app_secret,
            "fb_exchange_token": short_lived_token,
        },
        timeout=15,
    )
    body = _check_response(resp)

    long_token   = body["access_token"]
    expires_in   = body.get("expires_in", 5183944)   # default ~60 days
    expiry_str   = _expiry_message(expires_in)

    print(f"\nLong-lived token obtained! Expires: {expiry_str}")
    print(f"\nToken preview: {long_token[:20]}...")

    _update_env("INSTAGRAM_ACCESS_TOKEN", long_token)
    print(f"\n⚠  Set a calendar reminder to run `make auth-instagram-refresh` before {expiry_str}")


# ── refresh: extend an existing long-lived token ──────────────────────────────

def refresh_token() -> None:
    """Refresh the existing long-lived token and save the new one to .env."""
    app_id     = _require_env("INSTAGRAM_APP_ID")
    app_secret = _require_env("INSTAGRAM_APP_SECRET")
    token      = _require_env("INSTAGRAM_ACCESS_TOKEN")

    print("Refreshing long-lived Instagram token...")
    resp = requests.get(
        f"{GRAPH_BASE}/oauth/access_token",
        params={
            "grant_type":    "fb_exchange_token",
            "client_id":     app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token,
        },
        timeout=15,
    )
    body = _check_response(resp)

    new_token  = body["access_token"]
    expires_in = body.get("expires_in", 5183944)
    expiry_str = _expiry_message(expires_in)

    print(f"Token refreshed! New expiry: {expiry_str}")
    _update_env("INSTAGRAM_ACCESS_TOKEN", new_token)
    print(f"\n⚠  Set a calendar reminder to run `make auth-instagram-refresh` before {expiry_str}")


# ── verify: sanity-check the current token ────────────────────────────────────

def verify_token() -> None:
    """Print basic info about the current token (account ID, permissions, expiry)."""
    token = _require_env("INSTAGRAM_ACCESS_TOKEN")

    resp = requests.get(
        f"{GRAPH_BASE}/me",
        params={"fields": "id,name", "access_token": token},
        timeout=15,
    )
    body = _check_response(resp)
    print(f"Token is valid. Facebook user: {body.get('name')} (id={body.get('id')})")

    # Check token debug info
    app_id     = os.getenv("INSTAGRAM_APP_ID", "")
    app_secret = os.getenv("INSTAGRAM_APP_SECRET", "")
    if app_id and app_secret:
        debug_resp = requests.get(
            f"{GRAPH_BASE}/debug_token",
            params={
                "input_token":  token,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout=15,
        )
        debug_body = _check_response(debug_resp).get("data", {})
        exp_at = debug_body.get("expires_at", 0)
        if exp_at:
            expiry = datetime.fromtimestamp(exp_at, tz=timezone.utc)
            days_left = (expiry - datetime.now(tz=timezone.utc)).days
            print(f"Token expires: {expiry.strftime('%Y-%m-%d')} ({days_left} days remaining)")
            if days_left < 10:
                print("⚠  Token expires soon — run `make auth-instagram-refresh` now!")
        scopes = debug_body.get("scopes", [])
        if scopes:
            print(f"Granted scopes: {', '.join(scopes)}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Instagram Graph API token management for Birds, Bugs & Botanicals"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--exchange",
        metavar="SHORT_LIVED_TOKEN",
        nargs="?",
        const="prompt",
        help="Exchange a short-lived token for a long-lived one (prompts if token not provided)",
    )
    group.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh the existing long-lived token in .env",
    )
    group.add_argument(
        "--verify",
        action="store_true",
        help="Verify the current token and print expiry info",
    )
    args = parser.parse_args()

    if args.exchange is not None:
        token = args.exchange
        if token == "prompt":
            print("Paste your short-lived User Access Token from the Facebook Graph API Explorer:")
            print("(https://developers.facebook.com/tools/explorer/)")
            token = input("> ").strip()
            if not token:
                sys.exit("No token provided.")
        exchange_token(token)

    elif args.refresh:
        refresh_token()

    elif args.verify:
        verify_token()


if __name__ == "__main__":
    main()
