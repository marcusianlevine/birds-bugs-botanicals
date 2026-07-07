"""
net.py – shared HTTP helpers.

`get_with_retry` performs a GET with exponential backoff, used for pulling
images (which can fail transiently on flaky CDNs). It retries connection
errors, timeouts, and 429/5xx responses; other 4xx responses (e.g. 404) are
not retried since they won't succeed on a repeat.
"""

import logging
import random
import time

import requests

log = logging.getLogger(__name__)

# Status codes worth retrying (rate limiting + transient server errors).
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


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
    stream, headers, params, …) are passed straight to requests.get.

    Raises the last exception (or HTTPError) after `max_attempts` attempts.
    Non-retryable 4xx responses raise immediately.
    """
    last_exc: Exception | None = None

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
