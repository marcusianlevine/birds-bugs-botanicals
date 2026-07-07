"""
/api/login – validate the shared admin password.

This app has exactly one intended operator, so there's no user database —
just a single shared secret (ADMIN_PASSWORD) checked against every request
to the costly/impactful endpoints (/api/generate, /api/post). This endpoint
exists purely to give the frontend immediate "wrong password" feedback; the
frontend stores the password in sessionStorage for the tab's lifetime and
sends it as the X-Admin-Password header on subsequent calls.
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent / "_lib"))

from webauth import check_admin_password  # noqa: E402

app = Flask(__name__)


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    ok = check_admin_password(data.get("password"))
    return jsonify({"ok": ok}), (200 if ok else 401)
