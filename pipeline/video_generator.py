"""
video_generator.py – generate an image-to-video clip via WaveSpeed AI.

WaveSpeed API reference: https://wavespeed.ai/docs
Auth: WAVESPEED_API_KEY environment variable (picked up automatically by the SDK)

The SDK handles job submission and polling internally — wavespeed.run() blocks
until the video is ready and returns the result dict.

iNaturalist photo URLs are publicly accessible HTTPS, so we pass them directly.
If WaveSpeed rejects the URL (some hosts block cross-origin requests), we fall
back to downloading the image locally and uploading it via wavespeed.upload().
"""

import logging
import tempfile
from pathlib import Path

import requests
import wavespeed

import config

log = logging.getLogger(__name__)


def _resolve_image_url(image_url: str) -> str:
    """
    Return a URL WaveSpeed can fetch.

    Tries the original URL first. If it's not publicly reachable from WaveSpeed
    (some CDNs block non-browser requests), downloads it and re-uploads via the
    WaveSpeed storage API.
    """
    # iNaturalist URLs are reliably public — pass through directly.
    # Only fall back to upload if explicitly needed (e.g. local files or
    # restricted hosts). Keeping this fast path keeps latency low.
    return image_url


def _upload_image(image_url: str) -> str:
    """Download image_url and upload it to WaveSpeed storage. Returns hosted URL."""
    log.info("Uploading image to WaveSpeed storage (fallback path)…")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    resp = requests.get(image_url, timeout=30, stream=True)
    resp.raise_for_status()
    with open(tmp_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)

    hosted_url = wavespeed.upload(str(tmp_path))
    tmp_path.unlink(missing_ok=True)
    log.info("Image uploaded: %s", hosted_url)
    return hosted_url


def generate_video(image_url: str, prompt: str, output_path: Path) -> Path:
    """
    Generate a short video from a still image using WaveSpeed AI, then save it.

    Args:
        image_url:   Publicly accessible URL of the source image.
        prompt:      Motion/animation prompt.
        output_path: Where to save the finished MP4.

    Returns:
        Path to the saved MP4 file.

    Raises:
        RuntimeError  if the API call fails or returns no video.
        TimeoutError  if generation exceeds config.WAVESPEED_TIMEOUT seconds.
    """
    resolved_url = _resolve_image_url(image_url)

    payload = {
        "image": resolved_url,
        "prompt": prompt,
        "negative_prompt": (
            "blurry, distorted, text, watermark, logo, low quality, "
            "jerky motion, fast motion, unnatural movement"
        ),
        "resolution": config.WAVESPEED_VIDEO_RESOLUTION,
        "duration": config.WAVESPEED_VIDEO_DURATION,
        "seed": -1,   # random
    }

    log.info(
        "Submitting WaveSpeed image-to-video job (model: %s, resolution: %s, duration: %ss)…",
        config.WAVESPEED_MODEL, config.WAVESPEED_VIDEO_RESOLUTION, config.WAVESPEED_VIDEO_DURATION,
    )

    try:
        result = wavespeed.run(
            config.WAVESPEED_MODEL,
            payload,
            timeout=float(config.WAVESPEED_TIMEOUT),
            poll_interval=config.WAVESPEED_POLL_INTERVAL,
        )
    except Exception as e:
        err = str(e)
        # If the direct URL was rejected, retry with an uploaded copy
        if "url" in err.lower() or "fetch" in err.lower() or "image" in err.lower():
            log.warning("Direct URL failed (%s) — retrying with uploaded image…", e)
            payload["image"] = _upload_image(image_url)
            result = wavespeed.run(
                config.WAVESPEED_MODEL,
                payload,
                timeout=float(config.WAVESPEED_TIMEOUT),
                poll_interval=config.WAVESPEED_POLL_INTERVAL,
            )
        else:
            raise RuntimeError(f"WaveSpeed API error: {e}") from e

    outputs = result.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"WaveSpeed returned no outputs. Full response: {result}")

    video_url = outputs[0]
    log.info("WaveSpeed video ready: %s", video_url)

    return _download_video(video_url, output_path)


def _download_video(video_url: str, output_path: Path) -> Path:
    """Stream-download the finished MP4 to output_path."""
    log.info("Downloading video…")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(video_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    log.info("Video saved to: %s", output_path)
    return output_path
