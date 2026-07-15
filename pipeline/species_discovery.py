"""
species_discovery.py – find new candidate species and grow the species pools.

We query iNaturalist's ``/observations/species_counts`` endpoint, which ranks
taxa by how many research-grade observations they have. That count is a strong
proxy for "commonly encountered and well photographed", which is exactly what we
want to feature — species with plenty of good public imagery for the pipeline to
pull from.

For each of our three categories (mapped to iNaturalist "iconic taxa") we pull
the most-observed species and keep the ones that are:

  • genuine species (rank == "species"),
  • have an English common name,
  • have at least one photo, and
  • aren't already in the pool or on the rejected list.

Botanicals get one extra check: the pipeline only features plants whose
Wikipedia page has a "Uses" section (see research.is_valid_botanical), so we
confirm that here too and skip plants that would always be rejected downstream.

New names are appended to the matching category in data/species_pools.json.

Run it via the Make target::

    make discover-species            # add up to 10 across all categories
    make discover-species MAX=5      # add up to 5
    make discover-species CATEGORY=bird   # only birds

or directly::

    python species_discovery.py --max 10 [--category bird] [--no-validate] [--dry-run]
"""

import argparse
import json
import logging
import random
import sys
from pathlib import Path

import requests

import config
from net import get_with_retry

log = logging.getLogger("discover")

INATURALIST_BASE = "https://api.inaturalist.org/v1"

# Our categories → iNaturalist iconic taxa (same mapping research.py uses).
ICONIC_TAXA = {
    "bird": "Aves",
    "bug": "Insecta",
    "botanical": "Plantae",
}

# How many top species to pull per category before filtering. A wide net means
# that after removing everything already in the pool there are still plenty of
# fresh candidates to sample from for variety. iNaturalist caps per_page at 500.
FETCH_PER_CATEGORY = 200


# ── Pools + exclusion sets ──────────────────────────────────────────────────────

def _pools_path() -> Path:
    return config.DATA_DIR / "species_pools.json"


def _load_pools() -> dict:
    with open(_pools_path()) as f:
        return json.load(f)


def _save_pools(pools: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_pools_path(), "w") as f:
        json.dump(pools, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _rejected_names() -> set[str]:
    """Lower-cased names previously rejected (no good photo), across categories."""
    path = config.REJECTED_FILE
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return set()
    names: set[str] = set()
    for entries in data.values():
        for entry in entries:
            name = entry.get("name", "")
            if name:
                names.add(name.lower())
    return names


def _existing_names(pools: dict) -> set[str]:
    """Lower-cased set of every common name already in any pool."""
    return {name.lower() for names in pools.values() for name in names}


# ── iNaturalist ─────────────────────────────────────────────────────────────────

def _fetch_species_counts(iconic: str, per_page: int = FETCH_PER_CATEGORY) -> list[dict]:
    """
    Return the raw ``results`` list from iNaturalist species_counts for an
    iconic taxon, most-observed first. Best-effort: returns [] on failure.
    """
    params = {
        "iconic_taxa": iconic,
        "quality_grade": "research",
        "photos": "true",
        "rank": "species",
        "per_page": per_page,
        "locale": "en",
    }
    try:
        resp = get_with_retry(f"{INATURALIST_BASE}/observations/species_counts",
                              params=params, timeout=30)
        return resp.json().get("results", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("iNaturalist species_counts failed for %s: %s", iconic, e)
        return []


def _candidate_names(results: list[dict], exclude: set[str]) -> list[str]:
    """
    Pure filter: turn raw species_counts results into a list of usable common
    names, in the order returned. Keeps genuine species that have an English
    common name and a photo, and drops anything whose name is in ``exclude``
    (a lower-cased set). De-dupes within the batch.
    """
    names: list[str] = []
    seen = set(exclude)
    for row in results:
        taxon = row.get("taxon") or {}
        if taxon.get("rank") != "species":
            continue
        if not taxon.get("default_photo"):
            continue
        common = (taxon.get("preferred_common_name") or "").strip()
        if not common:
            continue
        key = common.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(common)
    return names


# ── Botanical validation (mirrors the pipeline's own rule) ──────────────────────

def _botanical_ok(common_name: str) -> bool:
    """
    True if this plant's Wikipedia page has a "Uses" section, matching the
    pipeline's botanical rule (research.is_valid_botanical). Best-effort: on any
    lookup error we skip the candidate (return False) rather than add a plant
    that would always be rejected downstream.
    """
    try:
        import research
        wiki = research._get_wikipedia(common_name, "botanical")
        return research.is_valid_botanical(wiki)
    except Exception as e:  # noqa: BLE001
        log.debug("Botanical validation failed for '%s': %s", common_name, e)
        return False


# ── Orchestration ───────────────────────────────────────────────────────────────

def discover(
    max_total: int = 10,
    only_category: str | None = None,
    validate_botanicals: bool = True,
) -> tuple[dict[str, list[str]], dict]:
    """
    Find up to ``max_total`` new species and build the updated pools.

    Spreads additions across the categories (round-robin) unless ``only_category``
    restricts it to one. Returns ``(added, pools)`` where ``added`` maps each
    category to the list of newly added names and ``pools`` is the updated pools
    dict ready to be written out.
    """
    pools = _load_pools()
    exclude = _existing_names(pools) | _rejected_names()

    categories = [only_category] if only_category else list(ICONIC_TAXA)

    # Pull and filter candidates for each category up front, shuffled so re-runs
    # surface different species rather than always the same most-observed few.
    candidates: dict[str, list[str]] = {}
    for cat in categories:
        results = _fetch_species_counts(ICONIC_TAXA[cat])
        names = _candidate_names(results, exclude)
        random.shuffle(names)
        candidates[cat] = names
        log.info("%s: %d fresh candidate(s) after filtering.", cat, len(names))

    added: dict[str, list[str]] = {cat: [] for cat in categories}
    total = 0

    # Round-robin so a 10-item budget is shared roughly evenly across categories.
    while total < max_total and any(candidates[c] for c in categories):
        for cat in categories:
            if total >= max_total:
                break
            picked = None
            while candidates[cat]:
                name = candidates[cat].pop(0)
                if cat == "botanical" and validate_botanicals and not _botanical_ok(name):
                    log.info("Skipping botanical '%s' (no Wikipedia Uses section).", name)
                    continue
                picked = name
                break
            if picked is None:
                continue
            pools[cat].append(picked)
            added[cat].append(picked)
            exclude.add(picked.lower())
            total += 1
            log.info("Added %s: %s", cat, picked)

    return added, pools


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover new species via iNaturalist and add them to the pools."
    )
    parser.add_argument("--max", type=int, default=10,
                        help="Maximum number of new species to add (default: 10).")
    parser.add_argument("--category", choices=list(ICONIC_TAXA),
                        help="Restrict discovery to a single category.")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip the Wikipedia 'Uses' check for botanicals.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without writing the pools file.")
    args = parser.parse_args()

    if args.max <= 0:
        sys.exit("--max must be a positive integer.")

    added, pools = discover(
        max_total=args.max,
        only_category=args.category,
        validate_botanicals=not args.no_validate,
    )

    total = sum(len(v) for v in added.values())
    if total == 0:
        print("No new species found to add (pools may already cover the most-observed "
              "species, or iNaturalist was unreachable).")
        return

    if args.dry_run:
        print(f"[dry run] Would add {total} new species:")
    else:
        _save_pools(pools)
        print(f"Added {total} new species to {_pools_path().name}:")

    for cat, names in added.items():
        if names:
            print(f"  {cat} (+{len(names)}): {', '.join(names)}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
