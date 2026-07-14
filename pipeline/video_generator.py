"""
video_generator.py - generate an image-to-video clip via WaveSpeed AI.

WaveSpeed API reference: https://wavespeed.ai/docs
Auth: WAVESPEED_API_KEY environment variable (picked up automatically by the SDK)

The SDK handles job submission and polling internally - wavespeed.run() blocks
until the video is ready and returns the result dict.

iNaturalist photo URLs are publicly accessible HTTPS, so we pass them directly.
If WaveSpeed rejects the URL (some hosts block cross-origin requests), we fall
back to downloading the image locally and uploading it via wavespeed.upload().
"""

import logging
import random
import shutil
import subprocess
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
    # iNaturalist URLs are reliably public - pass through directly.
    # Only fall back to upload if explicitly needed (e.g. local files or
    # restricted hosts). Keeping this fast path keeps latency low.
    return image_url


def _upload_image(image_url: str) -> str:
    """Download image_url and upload it to WaveSpeed storage. Returns hosted URL."""
    log.info("Uploading image to WaveSpeed storage (fallback path)...")
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
    if not config.WAVESPEED_API_KEY:
        raise EnvironmentError(
            "Missing required environment variable: WAVESPEED_API_KEY\n"
            "See .env.example for setup instructions."
        )

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
        "Submitting WaveSpeed image-to-video job (model: %s, resolution: %s, duration: %ss)...",
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
            log.warning("Direct URL failed (%s) - retrying with uploaded image...", e)
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

    saved = _download_video(video_url, output_path)

    if config.SOUNDSCAPE_ENABLED:
        _add_soundscape(saved)

    return saved


def _download_video(video_url: str, output_path: Path) -> Path:
    """Stream-download the finished MP4 to output_path."""
    log.info("Downloading video...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(video_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    log.info("Video saved to: %s", output_path)
    return output_path


# -- Soundscape muxing ---------------------------------------------------------
#
# WaveSpeed clips are silent. We overlay one of the pre-generated soundscapes in
# config.AUDIO_DIR (chosen at random), trimmed to the video length with a short
# fade-out. This is best-effort: any failure logs a warning and leaves the
# original silent video in place so the pipeline can still post.

def _ensure_ffmpeg_on_path() -> None:
    """
    Make `ffmpeg`/`ffprobe` resolvable via the static-ffmpeg dependency.

    static_ffmpeg.add_paths() downloads static builds on first call and prepends
    them to PATH. weak=True keeps a system-installed ffmpeg if one is already
    present. Safe no-op if the package is missing.
    """
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths(weak=True)
    except Exception as e:  # ImportError, or download/permission failure
        log.debug("static-ffmpeg unavailable (%s); relying on system ffmpeg.", e)

def _pick_soundscape() -> Path | None:
    """Return a random audio file from config.AUDIO_DIR, or None if none exist."""
    audio_dir = config.AUDIO_DIR
    if not audio_dir.is_dir():
        log.warning("Soundscape dir not found (%s) - keeping silent video.", audio_dir)
        return None
    tracks = sorted(
        p for p in audio_dir.iterdir()
        if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
    )
    if not tracks:
        log.warning("No soundscape files in %s - keeping silent video.", audio_dir)
        return None
    return random.choice(tracks)


def _probe_duration(path: Path) -> float | None:
    """Return media duration in seconds via ffprobe, or None if it can't be read."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        log.debug("Could not probe duration of %s: %s", path, e)
        return None


def _add_soundscape(video_path: Path) -> Path:
    """
    Mux a random soundscape onto video_path, in place.

    The audio is trimmed to the video length (-shortest) with a fade-out over the
    final config.SOUNDSCAPE_FADE_OUT seconds. On any error the original silent
    video is left untouched. Returns video_path either way.
    """
    _ensure_ffmpeg_on_path()
    if shutil.which("ffmpeg") is None:
        log.warning("ffmpeg not found on PATH - keeping silent video.")
        return video_path

    track = _pick_soundscape()
    if track is None:
        return video_path

    # Build the audio filter: fade out over the last N seconds of the clip.
    audio_filter = "aresample=async=1"
    duration = _probe_duration(video_path)
    fade = config.SOUNDSCAPE_FADE_OUT
    if duration and fade > 0 and duration > fade:
        audio_filter += f",afade=t=out:st={duration - fade:.3f}:d={fade:.3f}"

    tmp_out = video_path.with_suffix(".withaudio.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),          # 0: silent video
        "-i", str(track),               # 1: soundscape
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", config.SOUNDSCAPE_AUDIO_BITRATE,
        "-af", audio_filter,
        "-shortest",
        "-movflags", "+faststart",
        str(tmp_out),
    ]

    log.info("Adding soundscape '%s' to video...", track.name)
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        log.warning(
            "ffmpeg failed to add soundscape (%s) - keeping silent video.\n%s",
            e, e.stderr[-1000:] if e.stderr else "",
        )
        tmp_out.unlink(missing_ok=True)
        return video_path

    tmp_out.replace(video_path)
    log.info("Soundscape added: %s", video_path)
    return video_path
