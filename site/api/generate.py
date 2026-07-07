"""
/api/generate - research a species and generate post copy (no video).

POST { "species": "Barn Owl", "category": "bird" }
->  { common_name, scientific_name, category, wikipedia_url,
      conservation_status, photo: {...}, instagram_caption,
      tiktok_caption, alt_text }

Imports research()/select_best_photo()/generate_content() straight from the
repo's pipeline/ directory (no duplicate copy) - deliberately stops short of
video_generator.py, which only ever runs from the CLI pipeline directly.

Vercel's Root Directory is set to site/, so pipeline/ (one level up, at the
repo root) is outside it by default - the project must have "Include files
outside the Root Directory in the Build Step" enabled (Project Settings ->
General -> Root Directory) for this import to find it at build/runtime.
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent / "_lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))

from webauth import check_admin_password  # noqa: E402
import research as research_mod  # noqa: E402
import image_reviewer  # noqa: E402
import content_generator  # noqa: E402

app = Flask(__name__)

VALID_CATEGORIES = {"bird", "bug", "botanical"}


@app.route("/api/generate", methods=["POST"])
def generate():
    if not check_admin_password(request.headers.get("X-Admin-Password")):
        return jsonify({"error": "Unauthorized."}), 401

    data = request.get_json(silent=True) or {}
    species = (data.get("species") or "").strip()
    category = (data.get("category") or "").strip().lower()

    if not species:
        return jsonify({"error": "Species name is required."}), 400
    if category not in VALID_CATEGORIES:
        return jsonify({"error": "Category must be bird, bug, or botanical."}), 400

    try:
        result = research_mod.research(category, species)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Research failed: {e}"}), 502

    if result is None:
        return jsonify({
            "error": (
                f"Couldn't validate '{species}' as a {category}. "
                "(Botanicals need a Wikipedia 'Uses' section to qualify.)"
            )
        }), 422

    try:
        selection = image_reviewer.select_best_photo(result)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Photo review failed: {e}"}), 502

    if selection.photo is None:
        return jsonify({
            "error": f"No usable photo found for '{species}'. Try a different species."
        }), 422

    try:
        content = content_generator.generate_content(result)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Content generation failed: {e}"}), 502

    return jsonify({
        "common_name": result.common_name,
        "scientific_name": result.scientific_name,
        "category": result.category,
        "wikipedia_url": result.wikipedia_url,
        "conservation_status": result.conservation_status,
        "photo": {
            "url": selection.photo.url,
            "source": selection.photo.source,
            "attribution": selection.photo.attribution,
            "reviewer_approved": selection.approved,
        },
        "instagram_caption": content.instagram_caption,
        "tiktok_caption": content.tiktok_caption,
        "alt_text": content.alt_text,
    })
