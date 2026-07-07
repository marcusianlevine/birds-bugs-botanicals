"""
social_media.py - publish content to Instagram and TikTok.

Instagram: Meta Graph API v21
  -> photo posts use the iNaturalist image URL directly (already public HTTPS)

TikTok: Content Posting API v2
  -> videos are uploaded directly in chunks (FILE_UPLOAD source type)
  -> no public hosting required
"""

import logging
import math
import time
from pathlib import Path

import requests

import config

log = logging.getLogger(__name__)

TIKTOK_CHUNK_SIZE = 10 * 1024 * 1024    # 10 MB per chunk


def _require_instagram_config() -> None:
    missing = [
        name for name, val in (
            ("INSTAGRAM_ACCESS_TOKEN", config.INSTAGRAM_ACCESS_TOKEN),
            ("INSTAGRAM_ACCOUNT_ID", config.INSTAGRAM_ACCOUNT_ID),
        ) if not val
    ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}\n"
            f"See .env.example for setup instructions."
        )


# -- Instagram Graph API -------------------------------------------------------
#
# Flow for a photo post:
#   1. POST /{account_id}/media  { image_url, caption }  -> container_id
#   2. POST /{account_id}/media_publish  { creation_id }  -> media_id
#
# Instagram requires a publicly accessible HTTPS URL for all media.
# iNaturalist research-grade photo URLs are already public, so we pass them through.

def post_instagram_photo(image_url: str, caption: str, alt_text: str = "") -> str:
    """
    Publish a photo to Instagram using a public image URL.

    Args:
        image_url: Publicly accessible HTTPS URL (e.g. direct iNaturalist URL).
        caption:   Post caption including hashtags.
        alt_text:  Accessibility description for the image.

    Returns:
        Published media ID string.
    """
    _require_instagram_config()
    account_id = config.INSTAGRAM_ACCOUNT_ID
    token = config.INSTAGRAM_ACCESS_TOKEN

    log.info("Creating Instagram media container...")
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": token,
    }
    if alt_text:
        payload["alt_text"] = alt_text

    resp = requests.post(
        f"{config.INSTAGRAM_GRAPH_URL}/{account_id}/media",
        data=payload,
        timeout=30,
    )
    _check_ig_response(resp)
    container_id = resp.json()["id"]
    log.info("Instagram container created: %s", container_id)

    time.sleep(2)
    publish_resp = requests.post(
        f"{config.INSTAGRAM_GRAPH_URL}/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    _check_ig_response(publish_resp)
    media_id = publish_resp.json()["id"]
    log.info("Instagram post published! media_id=%s", media_id)
    return media_id


def post_instagram_reel(video_url: str, caption: str) -> str:
    """
    Publish a Reel to Instagram using a public video URL.

    Returns:
        Published media ID string.
    """
    _require_instagram_config()
    account_id = config.INSTAGRAM_ACCOUNT_ID
    token = config.INSTAGRAM_ACCESS_TOKEN

    log.info("Creating Instagram Reel container...")
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": token,
    }

    resp = requests.post(
        f"{config.INSTAGRAM_GRAPH_URL}/{account_id}/media",
        data=payload,
        timeout=30,
    )
    _check_ig_response(resp)
    container_id = resp.json()["id"]
    log.info("Instagram Reel container created: %s", container_id)

    _wait_for_instagram_container(container_id, token)

    publish_resp = requests.post(
        f"{config.INSTAGRAM_GRAPH_URL}/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    _check_ig_response(publish_resp)
    media_id = publish_resp.json()["id"]
    log.info("Instagram Reel published! media_id=%s", media_id)
    return media_id


def _wait_for_instagram_container(container_id: str, token: str, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(
            f"{config.INSTAGRAM_GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=15,
        )
        _check_ig_response(resp)
        status = resp.json().get("status_code", "")
        log.debug("Instagram container status: %s", status)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram media container failed with status: {status}")
        time.sleep(10)
    raise TimeoutError("Instagram media container did not finish processing in time.")


def _check_ig_response(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        raise RuntimeError(f"Instagram API error {resp.status_code}: {resp.text}")
    body = resp.json()
    if "error" in body:
        err = body["error"]
        raise RuntimeError(f"Instagram API error: {err.get('message', err)}")


# -- TikTok Content Posting API - FILE_UPLOAD ----------------------------------
#
# Flow:
#   1. POST /v2/post/publish/video/init/
#        source: FILE_UPLOAD, video_size, chunk_size, total_chunk_count
#      -> publish_id, upload_url
#   2. PUT <upload_url>  (one request per chunk, Content-Range header)
#   3. POST /v2/post/publish/status/fetch/  { publish_id }
#      -> poll until status == PUBLISH_COMPLETE

def post_tiktok_video(video_path: Path, caption: str) -> str:
    """
    Upload a local MP4 and publish it to TikTok.

    Args:
        video_path: Path to the local .mp4 file.
        caption:    Post caption (max 150 chars for the title field).

    Returns:
        publish_id string.
    """
    if not config.TIKTOK_ACCESS_TOKEN:
        raise EnvironmentError(
            "Missing required environment variable: TIKTOK_ACCESS_TOKEN\n"
            "Run `python tiktok_auth.py --save-env` to generate one, or see "
            ".env.example for setup instructions."
        )
    token = config.TIKTOK_ACCESS_TOKEN
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    video_size = video_path.stat().st_size
    total_chunks = math.ceil(video_size / TIKTOK_CHUNK_SIZE)

    log.info(
        "Initiating TikTok FILE_UPLOAD: %s (%.1f MB, %d chunk(s))...",
        video_path.name, video_size / 1_048_576, total_chunks,
    )

    # Step 1: init
    init_payload = {
        "post_info": {
            "title": caption[:150],
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": TIKTOK_CHUNK_SIZE,
            "total_chunk_count": total_chunks,
        },
    }

    resp = requests.post(
        f"{config.TIKTOK_BASE_URL}/post/publish/video/init/",
        json=init_payload,
        headers=headers,
        timeout=30,
    )
    _check_tt_response(resp)
    data = resp.json().get("data", {})
    publish_id = data.get("publish_id")
    upload_url = data.get("upload_url")
    if not publish_id or not upload_url:
        raise RuntimeError(f"TikTok init did not return publish_id/upload_url: {resp.json()}")
    log.info("TikTok publish_id: %s", publish_id)

    # Step 2: upload chunks
    with open(video_path, "rb") as f:
        for chunk_index in range(total_chunks):
            start = chunk_index * TIKTOK_CHUNK_SIZE
            chunk_data = f.read(TIKTOK_CHUNK_SIZE)
            end = start + len(chunk_data) - 1

            log.info("Uploading chunk %d/%d (bytes %d-%d)...", chunk_index + 1, total_chunks, start, end)
            put_resp = requests.put(
                upload_url,
                data=chunk_data,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                },
                timeout=120,
            )
            if put_resp.status_code not in (200, 206):
                raise RuntimeError(
                    f"TikTok chunk upload failed ({put_resp.status_code}): {put_resp.text}"
                )

    log.info("All chunks uploaded. Polling for publish status...")

    # Step 3: poll
    _wait_for_tiktok_publish(publish_id, headers)
    return publish_id


def _wait_for_tiktok_publish(publish_id: str, headers: dict, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.post(
            f"{config.TIKTOK_BASE_URL}/post/publish/status/fetch/",
            json={"publish_id": publish_id},
            headers=headers,
            timeout=15,
        )
        _check_tt_response(resp)
        status = resp.json().get("data", {}).get("status", "")
        log.debug("TikTok publish status: %s", status)
        if status == "PUBLISH_COMPLETE":
            log.info("TikTok video published successfully!")
            return
        if status in ("FAILED", "CANCELLED"):
            fail_reason = resp.json().get("data", {}).get("fail_reason", "unknown")
            raise RuntimeError(f"TikTok publish failed: {fail_reason}")
        time.sleep(10)
    raise TimeoutError("TikTok video did not finish publishing in time.")


def _check_tt_response(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        raise RuntimeError(f"TikTok API error {resp.status_code}: {resp.text}")
    body = resp.json()
    error = body.get("error", {})
    if error.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok API error [{error.get('code')}]: {error.get('message')}")
