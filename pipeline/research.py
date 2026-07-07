"""
research.py – gather facts, images and taxonomy for a chosen organism.

Sources:
  • Wikipedia  – summary text, sections (incl. "Uses" for botanicals)
  • iNaturalist – research-grade photos, range info, common observations
  • eBird       – range maps and observation data (birds only)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import requests
import wikipediaapi

import config
from net import get_with_retry

log = logging.getLogger(__name__)

WIKI_USER_AGENT = "BirdsBugsBotanicals/1.0 (marcusianl@gmail.com)"
INATURALIST_BASE = "https://api.inaturalist.org/v1"
EBIRD_BASE = "https://api.ebird.org/v2"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Photo:
    url: str            # full-size URL
    thumb_url: str      # small thumbnail
    attribution: str    # photographer credit
    source: str         # "Wikipedia" | "iNaturalist" | "eBird"


@dataclass
class ResearchResult:
    category: str
    common_name: str
    scientific_name: str = ""
    wikipedia_summary: str = ""
    wikipedia_url: str = ""
    uses_section: str = ""          # botanical only
    fun_facts: list[str] = field(default_factory=list)
    photos: list[Photo] = field(default_factory=list)
    range_description: str = ""     # where it's found
    conservation_status: str = ""
    taxon_id: int | None = None     # iNaturalist taxon ID


# ── Wikipedia ─────────────────────────────────────────────────────────────────

def _get_wikipedia(common_name: str, category: str) -> dict:
    """
    Fetch Wikipedia page data. Returns dict with:
      summary, url, uses_section, scientific_name, conservation_status
    """
    wiki = wikipediaapi.Wikipedia(
        language="en",
        user_agent=WIKI_USER_AGENT
    )

    page = wiki.page(common_name)
    if not page.exists():
        # Try appending the category as disambiguation
        for suffix in [f" ({category})", " (plant)", " (insect)", " (bird)"]:
            page = wiki.page(common_name + suffix)
            if page.exists():
                break

    if not page.exists():
        log.warning("Wikipedia page not found for: %s", common_name)
        return {}

    # Extract "Uses" / "Uses and applications" section for botanicals
    uses_text = ""
    for section_name in ("Uses", "Uses and applications", "Medical uses",
                         "Traditional uses", "Culinary uses", "Medicinal uses"):
        section = page.section_by_title(section_name)
        if section and section.text.strip():
            uses_text = section.text.strip()
            break

    # Try to extract scientific name from intro text
    sci_name = _extract_scientific_name(page.text)

    # Conservation status
    conservation = _extract_conservation_status(page.text)

    # Pull a few interesting sentences from non-lead sections for fun facts
    fun_facts = _extract_fun_facts(page)

    # Lead image (the reviewer tries this before other databases)
    image_url, thumb_url = _get_wikipedia_image(page.title)

    return {
        "summary": page.summary[:1500],   # first ~1500 chars
        "url": page.fullurl,
        "uses_section": uses_text,
        "scientific_name": sci_name,
        "conservation_status": conservation,
        "fun_facts": fun_facts,
        "image_url": image_url,
        "thumb_url": thumb_url,
    }


def _get_wikipedia_image(title: str) -> tuple[str, str]:
    """
    Fetch the lead image for a Wikipedia page via the MediaWiki Action API
    (prop=pageimages). Returns (original_url, thumbnail_url); either may be ""
    if none exists.

    Note: we deliberately use the Action API (w/api.php) rather than the REST
    summary endpoint (/api/rest_v1/page/summary/), which now returns 403
    Forbidden for automated clients. The Action API accepts the same
    User-Agent the rest of our Wikipedia access already uses.
    """
    if not title:
        return "", ""

    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "prop": "pageimages",
        "piprop": "original|thumbnail",
        "pithumbsize": 800,
        "titles": title,
        "redirects": 1,
    }
    try:
        resp = get_with_retry(
            "https://en.wikipedia.org/w/api.php",
            params=params,
            headers={"User-Agent": WIKI_USER_AGENT},
            timeout=10,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("Wikipedia image lookup failed for '%s': %s", title, e)
        return "", ""

    pages = data.get("query", {}).get("pages", [])
    # formatversion=2 returns a list; older format returns a dict keyed by pageid.
    if isinstance(pages, dict):
        pages = list(pages.values())
    if not pages:
        return "", ""

    page = pages[0]
    original = (page.get("original") or {}).get("source", "")
    thumb = (page.get("thumbnail") or {}).get("source", "")
    return original, (thumb or original)


def _extract_scientific_name(text: str) -> str:
    """Heuristic: look for italicised binomial in the first 500 chars."""
    # Wikipedia plain text doesn't preserve italics, but the binomial often
    # appears in parentheses early on
    match = re.search(r'\(([A-Z][a-z]+ [a-z]+(?:\s[a-z]+)?)\)', text[:800])
    return match.group(1) if match else ""


def _extract_conservation_status(text: str) -> str:
    statuses = [
        "Least Concern", "Near Threatened", "Vulnerable",
        "Endangered", "Critically Endangered", "Extinct in the Wild", "Extinct"
    ]
    for status in statuses:
        if status.lower() in text.lower():
            return status
    return ""


def _extract_fun_facts(page) -> list[str]:
    """Pull 3 interesting sentences from body sections."""
    facts = []
    skip_sections = {"References", "External links", "See also", "Further reading", "Notes"}
    for section in page.sections:
        if section.title in skip_sections:
            continue
        sentences = re.split(r'(?<=[.!?])\s+', section.text.strip())
        for sentence in sentences:
            sentence = sentence.strip()
            if (len(sentence) > 60 and len(sentence) < 300
                    and not sentence.startswith("==")
                    and sentence not in facts):
                facts.append(sentence)
                if len(facts) >= 5:
                    return facts
    return facts


# ── iNaturalist ───────────────────────────────────────────────────────────────

def _get_inaturalist(common_name: str, category: str) -> dict:
    """
    Search iNaturalist for the taxon, then fetch research-grade photos.
    Returns dict with: taxon_id, scientific_name, photos, range_description
    """
    # Map our categories to iNaturalist iconic_taxa
    iconic_map = {
        "bird": "Aves",
        "bug": "Insecta",
        "botanical": "Plantae",
    }

    params = {
        "q": common_name,
        "rank": "species",
        "is_active": "true",
        "locale": "en",
        "preferred_place_id": 1,
    }
    iconic = iconic_map.get(category)
    if iconic:
        params["iconic_taxa"] = iconic

    try:
        resp = get_with_retry(f"{INATURALIST_BASE}/taxa", params=params, timeout=15)
        results = resp.json().get("results", [])
    except requests.RequestException as e:
        log.warning("iNaturalist taxa search failed: %s", e)
        return {}

    if not results:
        log.warning("No iNaturalist taxon found for: %s", common_name)
        return {}

    taxon = results[0]
    taxon_id = taxon["id"]
    sci_name = taxon.get("name", "")

    # Fetch research-grade observations with photos
    obs_params = {
        "taxon_id": taxon_id,
        "quality_grade": config.INATURALIST_QUALITY,
        "photos": "true",
        "per_page": config.INATURALIST_PER_PAGE,
        "order": "votes",
        "order_by": "votes",
    }
    try:
        obs_resp = get_with_retry(
            f"{INATURALIST_BASE}/observations", params=obs_params, timeout=15
        )
        observations = obs_resp.json().get("results", [])
    except requests.RequestException as e:
        log.warning("iNaturalist observations failed: %s", e)
        observations = []

    photos = []
    seen_urls: set[str] = set()
    for obs in observations:
        for photo_data in obs.get("photos", []):
            url = photo_data.get("url", "").replace("/square.", "/original.")
            if url and url not in seen_urls:
                seen_urls.add(url)
                attribution = photo_data.get("attribution", "© iNaturalist")
                photos.append(Photo(
                    url=url,
                    thumb_url=photo_data.get("url", ""),
                    attribution=attribution,
                    source="iNaturalist",
                ))
                if len(photos) >= 5:
                    break
        if len(photos) >= 5:
            break

    # Simple range description from taxon's establishment_means or Wikipedia range
    range_desc = ""
    if taxon.get("establishment_means"):
        range_desc = taxon["establishment_means"].get("establishment_means", "")

    return {
        "taxon_id": taxon_id,
        "scientific_name": sci_name,
        "photos": photos,
        "range_description": range_desc,
    }


# ── eBird (birds only) ────────────────────────────────────────────────────────

def _get_ebird_info(scientific_name: str) -> dict:
    """Fetch species code from eBird. Returns dict with species_code."""
    if not scientific_name:
        return {}
    headers = {"X-eBirdApiToken": config.EBIRD_API_KEY}
    try:
        resp = get_with_retry(
            f"{EBIRD_BASE}/ref/taxonomy/ebird",
            params={"fmt": "json", "species": scientific_name},
            headers=headers,
            timeout=10,
        )
        data = resp.json()
        if data:
            return {"species_code": data[0].get("speciesCode", "")}
    except requests.RequestException as e:
        log.warning("eBird lookup failed: %s", e)
    return {}


def _get_ebird_photos(species_code: str, limit: int = 5) -> list[Photo]:
    """
    Fetch top-rated photos for a bird from the Macaulay Library (the media
    archive behind eBird). Best-effort: returns [] on any failure.
    """
    if not species_code:
        return []

    params = {
        "taxonCode": species_code,
        "mediaType": "photo",
        "sort": "rating_rank_desc",
        "count": limit,
    }
    try:
        resp = get_with_retry(
            "https://search.macaulaylibrary.org/api/v2/search",
            params=params,
            timeout=15,
        )
        results = resp.json().get("results", {}).get("content", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("eBird/Macaulay photo search failed: %s", e)
        return []

    photos: list[Photo] = []
    for item in results:
        asset_id = item.get("assetId")
        if not asset_id:
            continue
        # Macaulay CDN sizes: 320/480/900/1200/2400 (px on longest side)
        url = f"https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset_id}/1200"
        thumb = f"https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset_id}/480"
        photographer = item.get("userDisplayName", "")
        attribution = (
            f"© {photographer} / Macaulay Library" if photographer
            else "© Macaulay Library"
        )
        photos.append(Photo(
            url=url,
            thumb_url=thumb,
            attribution=attribution,
            source="eBird",
        ))
    return photos


# ── Botanical validation ───────────────────────────────────────────────────────

def is_valid_botanical(wiki_data: dict) -> bool:
    """
    A plant qualifies as a 'botanical' if its Wikipedia page has a Uses section.
    Returns True if it passes, False if we should try another plant.
    """
    uses = wiki_data.get("uses_section", "")
    return bool(uses and len(uses.strip()) > 50)


# ── Main entry point ──────────────────────────────────────────────────────────

def research(category: str, common_name: str) -> Optional[ResearchResult]:
    """
    Run the full research pipeline for an organism.
    Returns None if the species fails validation (botanical without Uses section).
    """
    log.info("Researching: %s (%s)", common_name, category)

    # 1. Wikipedia
    wiki_data = _get_wikipedia(common_name, category)

    # 2. Botanical validation
    if category == "botanical":
        if not is_valid_botanical(wiki_data):
            log.info(
                "'%s' has no Uses section – not a valid botanical. "
                "Caller should pick another species.",
                common_name
            )
            return None

    # 3. iNaturalist
    inat_data = _get_inaturalist(common_name, category)

    # 4. eBird (birds only)
    sci_name = inat_data.get("scientific_name") or wiki_data.get("scientific_name", "")
    ebird_data = {}
    ebird_photos: list[Photo] = []
    if category == "bird" and sci_name:
        ebird_data = _get_ebird_info(sci_name)
        ebird_photos = _get_ebird_photos(ebird_data.get("species_code", ""))

    # 5. Assemble candidate photos in reviewer-preference order:
    #    Wikipedia first, then iNaturalist, then eBird/Macaulay.
    photos: list[Photo] = []
    if wiki_data.get("image_url"):
        photos.append(Photo(
            url=wiki_data["image_url"],
            thumb_url=wiki_data.get("thumb_url", wiki_data["image_url"]),
            attribution="Wikimedia Commons (via Wikipedia)",
            source="Wikipedia",
        ))
    photos.extend(inat_data.get("photos", []))
    photos.extend(ebird_photos)
    log.info(
        "Candidate photos for '%s': %d (%s)",
        common_name,
        len(photos),
        ", ".join(sorted({p.source for p in photos})) or "none",
    )

    # 6. Assemble result
    return ResearchResult(
        category=category,
        common_name=common_name,
        scientific_name=sci_name,
        wikipedia_summary=wiki_data.get("summary", ""),
        wikipedia_url=wiki_data.get("url", ""),
        uses_section=wiki_data.get("uses_section", ""),
        fun_facts=wiki_data.get("fun_facts", []),
        photos=photos,
        range_description=inat_data.get("range_description", ""),
        conservation_status=wiki_data.get("conservation_status", ""),
        taxon_id=inat_data.get("taxon_id"),
    )
