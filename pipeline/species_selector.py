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


# ── Rejected-species helpers ───────────────────────────────────────────────────
#
# A species that gets randomly selected but has no photo good enough to feature
# is recorded here and permanently excluded from future random selection, so we
# don't keep wasting research/vision-review calls rediscovering it has no usable
# image. (An explicit --species override bypasses this list.)

def _load_rejected() -> dict:
    if config.REJECTED_FILE.exists():
        with open(config.REJECTED_FILE) as f:
            return json.load(f)
    return {"bird": [], "bug": [], "botanical": []}


def _save_rejected(rejected: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.REJECTED_FILE, "w") as f:
        json.dump(rejected, f, indent=2)


def mark_rejected(selection: SpeciesSelection, reason: str = "no acceptable photo") -> None:
    """Exclude a species from future random selection (e.g. no usable photo)."""
    rejected = _load_rejected()
    names = {entry["name"] for entry in rejected.get(selection.category, [])}
    if selection.common_name in names:
        return  # already recorded
    entry = {
        "name": selection.common_name,
        "date": selection.selected_date,
        "reason": reason,
    }
    rejected.setdefault(selection.category, []).append(entry)
    _save_rejected(rejected)
    log.info(
        "Marked as rejected (%s): %s (%s) — won't be selected again.",
        reason, selection.common_name, selection.category,
    )


# ── Species pool ───────────────────────────────────────────────────────────────

def _load_pools() -> dict:
    pools_file = config.DATA_DIR / "species_pools.json"
    with open(pools_file) as f:
        return json.load(f)


# ── Automatic pool refill via discovery ─────────────────────────────────────────

def _discover_more(category: str) -> list[str]:
    """
    Grow the pool for `category` by running species discovery, persisting any
    additions to species_pools.json. Returns the newly added common names.

    Best-effort: returns [] (and logs) if discovery is unavailable or finds
    nothing — e.g. the network is down or the pool already covers the
    most-observed species — so the caller can fall back to recycling history.
    """
    try:
        import species_discovery
        added, pools = species_discovery.discover(
            max_total=config.DISCOVERY_REFILL_COUNT,
            only_category=category,
        )
    except Exception as e:  # noqa: BLE001 - discovery must never break selection
        log.error("Species discovery failed for %s: %s", category, e)
        return []

    new_names = added.get(category, [])
    if new_names:
        species_discovery._save_pools(pools)
        log.info(
            "Discovery added %d new %s species: %s",
            len(new_names), category, ", ".join(new_names),
        )
    return new_names


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
    rejected = _load_rejected()

    pool: list[str] = pools[category]
    posted_names: set[str] = {entry["name"] for entry in history.get(category, [])}
    rejected_names: set[str] = {entry["name"] for entry in rejected.get(category, [])}

    # Filter out already-posted species and any excluded for having no good photo
    remaining = [s for s in pool if s not in posted_names and s not in rejected_names]

    if not remaining:
        # Pool is exhausted for this category (everything posted or rejected).
        # Try to grow it with freshly discovered species before recycling.
        log.warning(
            "All usable %s species are exhausted (posted or rejected). "
            "Running species discovery to find new ones…", category
        )
        if _discover_more(category):
            pool = _load_pools()[category]   # reload the freshly grown pool
            remaining = [s for s in pool if s not in posted_names and s not in rejected_names]

        if not remaining:
            # Discovery found nothing new (or is offline) — recycle posted
            # history as a last resort so a post still goes out today.
            log.warning(
                "No new %s species available from discovery. Resetting %s history "
                "(rejected species stay excluded).", category, category
            )
            history[category] = []
            _save_history(history)
            # Rejected species have no usable photo, so keep excluding them.
            remaining = [s for s in pool if s not in rejected_names]
            if not remaining:
                log.error(
                    "Every %s species is on the rejected list and discovery found "
                    "nothing. Falling back to the full pool for this run.", category
                )
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
