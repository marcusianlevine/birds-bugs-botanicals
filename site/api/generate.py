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
repo root) is outside it by default. Two things are required for this import
to work when deployed:
  1. Project Settings -> General -> Root Directory -> "Include source files
     outside of the Root Directory in the Build Step" must be enabled, so
     pipeline/ is even visible to the build.
  2. vercel.json's "includeFiles": "../pipeline/**" on this function, since
     Python Vercel Functions do no automatic import-tracing (unlike Node) -
     files aren't bundled into the deployed function just because they're
     importable locally.

Locally, this file lives at site/api/generate.py, so pipeline/ is two
directories up. Deployed, Vercel flattens Root Directory (site/) to the
function's own root, so pipeline/ ends up only one directory up instead -
parents[2] would miss it entirely. _find_pipeline_dir() walks up from this
file looking for a "pipeline" directory that actually contains research.py,
so it resolves correctly in both layouts instead of assuming one fixed depth.
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, request


def _find_pipeline_dir() -> Path:
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "pipeline"
        if (candidate / "research.py").is_file():
            return candidate
    raise RuntimeError(
        "Could not locate the pipeline/ directory from "
        f"{here} - check vercel.json's includeFiles and the Root "
        "Directory build setting."
    )


sys.path.insert(0, str(Path(__file__).parent / "_lib"))
sys.path.insert(0, str(_find_pipeline_dir()))

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
