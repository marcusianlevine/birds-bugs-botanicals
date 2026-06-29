"""
video_generator.py – submit an image-to-video job to Kling AI and retrieve the result.

Kling API reference: https://kling.ai/document-api/api/get-started/authentication
Auth: Bearer token (API key only — as of June 2026, no JWT required)
"""

import logging
import time
from pathlib import Path

import requests

import config

log = logging.getLogger(__name__)


# ── Auth ───────────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.KLING_API_KEY}",
        "Content-Type": "application/json",
    }


# ── Submit job ─────────────────────────────────────────────────────────────────

def submit_image_to_video(image_url: str, prompt: str) -> str:
    """
    Submit an image-to-video task to Kling AI.

    Args:
        image_url: Publicly accessible URL of the source image.
        prompt:    Motion/style prompt for the animation.

    Returns:
        task_id string (used to poll for completion).

    Raises:
        RuntimeError on API error.
    """
    payload = {
        "model_name": "kling-v1-5",   # latest model as of mid-2025
        "image": image_url,
        "prompt": prompt,
        "negative_prompt": (
            "blurry, distorted, text, watermark, logo, low quality, "
            "jerky motion, fast motion, unnatural movement"
        ),
        "cfg_scale": 0.5,
        "mode": "std",
        "aspect_ratio": config.KLING_VIDEO_RATIO,
        "duration": str(config.KLING_VIDEO_DURATION),
    }

    log.info("Submitting Kling image-to-video job (model: kling-v1-5)…")
    resp = requests.post(
        f"{config.KLING_BASE_URL}/v1/videos/image2video",
        json=payload,
        headers=_headers(),
        timeout=30,
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(
            f"Kling API error {resp.status_code}: {resp.text}"
        ) from e

    data = resp.json()
    task_id = data.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"Kling did not return a task_id. Response: {data}")

    log.info("Kling task submitted. task_id=%s", task_id)
    return task_id


# ── Poll for result ────────────────────────────────────────────────────────────

def poll_until_ready(task_id: str) -> str:
    """
    Poll Kling until the video is ready.

    Returns:
        The URL of the completed video.

    Raises:
        TimeoutError if the video isn't ready within KLING_POLL_TIMEOUT seconds.
        RuntimeError on API or task failure.
    """
    deadline = time.time() + config.KLING_POLL_TIMEOUT
    log.info("Polling Kling for task %s…", task_id)

    while time.time() < deadline:
        resp = requests.get(
            f"{config.KLING_BASE_URL}/v1/videos/image2video/{task_id}",
            headers=_headers(),
            timeout=15,
        )
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"Kling poll error: {resp.text}") from e

        data = resp.json().get("data", {})
        status = data.get("task_status", "")
        log.debug("Kling task status: %s", status)

        if status == "succeed":
            # Extract video URL
            works = data.get("task_result", {}).get("videos", [])
            if not works:
                raise RuntimeError("Kling reported success but no video found in response.")
            video_url = works[0].get("url")
            if not video_url:
                raise RuntimeError("Kling video URL is empty.")
            log.info("Kling video ready: %s", video_url)
            return video_url

        if status == "failed":
            msg = data.get("task_status_msg", "unknown error")
            raise RuntimeError(f"Kling task failed: {msg}")

        # Still processing – wait and try again
        time.sleep(config.KLING_POLL_INTERVAL)

    raise TimeoutError(
        f"Kling video task {task_id} did not complete within "
        f"{config.KLING_POLL_TIMEOUT} seconds."
    )


# ── Download video ─────────────────────────────────────────────────────────────

def download_video(video_url: str, output_path: Path) -> Path:
    """
    Download the generated MP4 to output_path.

    Returns:
        Path to the saved file.
    """
    log.info("Downloading video from Kling…")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(video_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    log.info("Video saved to: %s", output_path)
    return output_path


# ── Convenience wrapper ────────────────────────────────────────────────────────

def generate_video(image_url: str, prompt: str, output_path: Path) -> Path:
    """
    Full pipeline: submit → poll → download.

    Args:
        image_url:   Public URL of the source image.
        prompt:      Motion prompt.
        output_path: Where to save the MP4.

    Returns:
        Path to the saved MP4 file.
    """
    task_id = submit_image_to_video(image_url, prompt)
    video_url = poll_until_ready(task_id)
    return download_video(video_url, output_path)
