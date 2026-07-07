"""
species_selector.py – randomly picks today's organism.

Strategy:
  1. Pick a category (bird / bug / botanical) using weighted random choice.
  2. Shuffle the species pool for that category and return the first one
     not found in the posted-history file.
  3. If every species in the pool has been used, clear the history for
     that category and start fresh (we have 50 species per category,
     so this won't happen for a long time).
"""

import json
import random
import logging
from dataclasses import dataclass, field
from datetime import date

import config

log = logging.getLogger(__name__)


@dataclass
class SpeciesSelection:
    category: str          # "bird" | "bug" | "botanical"
    common_name: str
    selected_date: str = field(default_factory=lambda: date.today().isoformat())


# ── History helpers ────────────────────────────────────────────────────────────

def _load_history() -> dict:
    if config.HISTORY_FILE.exists():
        with open(config.HISTORY_FILE) as f:
            return json.load(f)
    return {"bird": [], "bug": [], "botanical": []}


def _save_history(history: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def mark_posted(selection: SpeciesSelection) -> None:
    """Record a species as posted so it won't be repeated."""
    history = _load_history()
    entry = {"name": selection.common_name, "date": selection.selected_date}
    history.setdefault(selection.category, []).append(entry)
    _save_history(history)
    log.info("Marked as posted: %s (%s)", selection.common_name, selection.category)


# ── Species pool ───────────────────────────────────────────────────────────────

def _load_pools() -> dict:
    pools_file = config.DATA_DIR / "species_pools.json"
    with open(pools_file) as f:
        return json.load(f)


# ── Main selector ──────────────────────────────────────────────────────────────

def pick_today(category: str | None = None) -> SpeciesSelection:
    """
    Pick a species for today.

    Args:
        category: Force a specific category ("bird", "bug", "botanical").
                  If None, picks randomly using CATEGORY_WEIGHTS.

    Returns:
        SpeciesSelection with the chosen category and common name.
    """
    if category is None:
        category = random.choices(
            config.CATEGORIES,
            weights=config.CATEGORY_WEIGHTS,
            k=1
        )[0]

    pools = _load_pools()
    history = _load_history()

    pool: list[str] = pools[category]
    posted_names: set[str] = {entry["name"] for entry in history.get(category, [])}

    # Filter out already-posted species
    remaining = [s for s in pool if s not in posted_names]

    if not remaining:
        log.warning(
            "All %s species have been posted. Resetting %s history.",
            category, category
        )
        history[category] = []
        _save_history(history)
        remaining = pool.copy()

    chosen = random.choice(remaining)
    log.info("Selected species: %s (%s)", chosen, category)
    return SpeciesSelection(category=category, common_name=chosen)


# ── Named selection (explicit species override) ─────────────────────────────────

def _find_in_pools(common_name: str) -> tuple[str | None, str]:
    """
    Look up a species by name in the pools (case-insensitive).
    Returns (category, canonical_name). If not found, returns (None, common_name).
    """
    pools = _load_pools()
    for category, names in pools.items():
        for name in names:
            if name.lower() == common_name.strip().lower():
                return category, name
    return None, common_name.strip()


def pick_named(common_name: str, category: str | None = None) -> SpeciesSelection:
    """
    Build a selection for a specific, user-requested species (bypasses the
    random picker). The category is inferred from the species pools when
    possible; otherwise the caller must supply `category`.

    Raises ValueError if the category can't be determined.
    """
    if not common_name or not common_name.strip():
        raise ValueError("No species name provided.")

    found_category, canonical = _find_in_pools(common_name)
    resolved = found_category or category

    if resolved is None:
        raise ValueError(
            f"'{common_name}' isn't in the species pools, so its category is "
            f"unknown. Re-run and also pass a category "
            f"(e.g. CATEGORY=bird / --category bird)."
        )
    if found_category and category and found_category != category:
        log.warning(
            "Requested category '%s' for '%s' but the pools list it as '%s'. "
            "Using '%s'.", category, canonical, found_category, found_category,
        )

    log.info("Using requested species: %s (%s)", canonical, resolved)
    return SpeciesSelection(category=resolved, common_name=canonical)
