"""
webauth.py – shared auth helpers for the web app's API functions.

Two independent concerns live here:
  * check_admin_password – gates the expensive/impactful endpoints
    (content generation, posting) behind a single shared secret, since this
    app has exactly one intended operator, not a public user base.
  * is_allowed_photo_host – restricts the photo-proxy endpoint to the actual
    handful of domains our research pipeline ever sources photos from, so it
    can't be abused as an open image proxy.
"""

import hmac
import os


def check_admin_password(provided) -> bool:
    """Constant-time check against the ADMIN_PASSWORD env var.

    Returns False (deny) if ADMIN_PASSWORD isn't configured at all — fail
    closed rather than accidentally leaving these endpoints open.
    """
    expected = os.environ.get("ADMIN_PASSWORD", "")
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(provided), expected)


# Root domains the research pipeline ever sources photos from (Wikipedia,
# iNaturalist, eBird/Macaulay Library). The photo proxy only ever fetches
# from these.
_ALLOWED_PHOTO_SUFFIXES = (
    "wikipedia.org",
    "wikimedia.org",
    "inaturalist.org",
    "inaturalist-open-data.s3.amazonaws.com",
    "birds.cornell.edu",
    "macaulaylibrary.org",
)


def is_allowed_photo_host(hostname: str) -> bool:
    hostname = (hostname or "").lower()
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in _ALLOWED_PHOTO_SUFFIXES
    )
