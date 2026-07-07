"""
net.py – shared HTTP helpers.

`get_with_retry` performs a GET with exponential backoff, used for pulling
images (which can fail transiently on flaky CDNs). It retries connection
errors, timeouts, and 429/5xx responses; other 4xx responses (e.g. 404) are
not retried since they won't succeed on a repeat.

It also stamps every request with a default identifying User-Agent unless
the caller supplies their own. This matters most for Wikimedia: raw image
downloads from upload.wikimedia.org (via research.py's photo URLs) get a
straight 403 Forbidden with the default python-requests UA string, per
Wikimedia's User-Agent policy (https://meta.wikimedia.org/wiki/User-Agent_policy).
The metadata calls in research.py already sent a proper UA (wikipediaapi's
user_agent=, and an explicit header on the Action API call) - only the
actual image bytes were fetched UA-less, since download_image() and
_download_data_url() call get_with_retry() with no headers at all. Setting
the default here fixes both of those call sites (and every future one)
without touching them individually.
"""

import logging
import random
import time

import requests

log = logging.getLogger(__name__)

# Status codes worth retrying (rate limiting + transient server errors).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Identifies us to Wikimedia and other APIs that reject/rate-limit anonymous
# or default-library User-Agents. Contact email per Wikimedia's UA policy.
DEFAULT_USER_AGENT = "BirdsBugsBotanicals/1.0 (marcusianl@gmail.com)"


def get_with_retry(
    url: str,
    *,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_cap: float = 30.0,
    jitter: bool = True,
    **kwargs,
) -> requests.Response:
    """
    GET `url`, retrying transient failures with exponential backoff.

    Backoff before attempt N is backoff_base * 2**(N-1) seconds (capped at
    backoff_cap), plus a little random jitter. Any keyword args (timeout,
    stream, headers, params, …) are passed straight to requests.get. A
    default User-Agent (DEFAULT_USER_AGENT) is applied unless the caller's
    headers dict already sets one.

    Raises the last exception (or HTTPError) after `max_attempts` attempts.
    Non-retryable 4xx responses raise immediately.
    """
    last_exc: Exception | None = None

    headers = {**(kwargs.pop("headers", None) or {})}
    headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    kwargs["headers"] = headers

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, **kwargs)
        except requests.RequestException as e:
            last_exc = e
        else:
            if resp.status_code not in RETRYABLE_STATUS:
                # Success, or a non-retryable 4xx (raise_for_status handles it).
                resp.raise_for_status()
                return resp
            last_exc = requests.HTTPError(
                f"{resp.status_code} Server Error for url: {url}", response=resp
            )

        if attempt == max_attempts:
            break

        delay = min(backoff_base * (2 ** (attempt - 1)), backoff_cap)
        if jitter:
            delay += random.uniform(0, backoff_base)
        log.warning(
            "Image pull attempt %d/%d failed (%s). Retrying in %.1fs…",
            attempt, max_attempts, last_exc, delay,
        )
        time.sleep(delay)

    assert last_exc is not None
    raise last_exc
