"""YouTube videos: archival mkv + info.json via yt-dlp, no markdown."""

import json
import re
import subprocess
from pathlib import Path

from capture.resolvers.base import Resolution

# Netscape-format cookies, for age-restricted or member-only videos.
YOUTUBE_COOKIES = Path.home() / ".config" / "capture" / "youtube-cookies.txt"


def resolve_youtube(url: str) -> Resolution | None:
    """Video captures are mkv + info.json (the yt-dlp standard), no
    markdown: the info.json carries all metadata and the transcript
    lives in the mkv's embedded subtitles."""
    vid = youtube_id(url)
    if not vid:
        return None
    source = f"https://www.youtube.com/watch?v={vid}"
    probe = yt_dlp(["--dump-json", "--skip-download", source])
    if probe.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {source}: {probe.stderr.strip()[:300]}")
    meta = json.loads(probe.stdout)
    upload = meta.get("upload_date") or ""
    # "youtube.com - @handle" as the leading folder segments: sorts
    # under the youtube.com type prefix, then groups by channel.
    handle = (meta.get("uploader_id") or "").removeprefix("@").lower()
    handle = re.sub(r"[^a-z0-9._-]", "", handle)  # handles can be non-ASCII
    return Resolution(
        source=source,
        content=source,
        domain=f"youtube.com - @{handle}" if handle else None,
        use_browser=False,
        publish=f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if upload else None,
        skip_markdown=True,
        title=meta.get("title"),
        download_media=lambda folder, name: youtube_download(source, folder, name),
    )


def youtube_id(url: str) -> str | None:
    match = re.search(
        r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|live/)|youtu\.be/)"
        r"([A-Za-z0-9_-]{11})",
        url,
    )
    return match.group(1) if match else None


def yt_dlp(args: list[str]) -> subprocess.CompletedProcess:
    # Warnings stay on: stderr is captured and only printed when
    # something fails, and the cookie-expiry warning is the one clue
    # that distinguishes a dead session from a genuinely gated video.
    command = ["yt-dlp"]
    if YOUTUBE_COOKIES.exists():
        command += ["--cookies", str(YOUTUBE_COOKIES)]
    return subprocess.run(command + args, capture_output=True, text=True)


def youtube_download(source: str, folder: Path, name: str) -> None:
    """Max-quality archival download: one mkv with thumbnail, metadata,
    chapters, subtitles, and the info-json all embedded."""
    result = yt_dlp(
        [
            "-f",
            "bestvideo*+bestaudio/best",
            "--merge-output-format",
            "mkv",
            # Also remux single-format downloads: info-json and other
            # attachments only embed into mkv.
            "--remux-video",
            "mkv",
            "--embed-thumbnail",
            "--embed-metadata",
            "--embed-chapters",
            "--embed-subs",
            "--embed-info-json",
            "--write-info-json",
            # A --force re-capture means the existing copy is wrong or
            # stale. Without this yt-dlp keeps it and only the info.json
            # is rewritten, leaving metadata describing a file that is
            # not there.
            "--force-overwrites",
            "--sub-langs",
            "en,en-orig",
            "--write-auto-subs",
            "--sponsorblock-mark",
            "all",
            "-o",
            str(folder / f"{name}.%(ext)s"),
            source,
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(download_failure(source, result.stderr))
    video = folder / f"{name}.mkv"
    if not video.exists():
        # A clean exit with no file: the download was skipped rather than
        # performed, which would otherwise leave a folder holding an
        # info.json that describes a video it does not contain.
        raise RuntimeError(f"yt-dlp wrote no video for {source}")
    # Subtitle files were only needed for embedding.
    for stray in folder.glob(f"{name}*.vtt"):
        stray.unlink()
    for stray in folder.glob(f"{name}*.srt"):
        stray.unlink()


# yt-dlp's wording when the jar has been rotated out from under it.
STALE_COOKIES = "cookies are no longer valid"


def download_failure(source: str, stderr: str) -> str:
    """Why the download failed, phrased so the fix is obvious.

    An expired jar surfaces as "Sign in to confirm your age", because a
    logged-out client is exactly what an age-restricted video refuses --
    which sends you investigating the video when the session is what
    died. yt-dlp says which it is in a warning; say it back plainly.
    """
    detail = " ".join(stderr.split())[:300]
    if STALE_COOKIES in stderr:
        return (
            f"youtube cookies have expired: refresh {YOUTUBE_COOKIES} "
            f"and retry {source} ({detail})"
        )
    return f"video download failed for {source}: {detail}"
