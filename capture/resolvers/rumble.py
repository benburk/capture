"""Rumble videos: archival mkv + info.json via yt-dlp, no markdown."""

import json
import re
import subprocess
from pathlib import Path

from capture.extract import slugify
from capture.resolvers.base import Resolution

# Video pages ("v40c8ot-some-title.html") and embed player URLs. Anchored
# to the host so a wayback snapshot of a rumble page stays with the
# wayback resolver.
RUMBLE_URL = re.compile(
    r"https?://(?:www\.)?rumble\.com/"
    r"(?:(?P<page>v[0-9a-z]+-[^/?#]*\.html)|embed/(?P<embed>v[0-9a-z]+))"
)


def resolve_rumble(url: str) -> Resolution | None:
    """Video captures are mkv + info.json (the yt-dlp standard), no
    markdown: the same shape youtube and vimeo captures take."""
    source = rumble_source(url)
    if not source:
        return None
    probe = yt_dlp(["--dump-json", "--skip-download", source])
    if probe.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {source}: {probe.stderr.strip()[:300]}")
    meta = json.loads(probe.stdout)
    upload = meta.get("upload_date") or ""
    # "rumble.com - <channel>" as the leading folder segments: sorts
    # under the rumble.com type prefix, then groups by channel. Rumble
    # gives no account id, only the display name.
    channel = slugify(meta.get("channel") or meta.get("uploader") or "")
    return Resolution(
        source=meta.get("webpage_url") or source,
        content=source,
        domain=f"rumble.com - {channel}" if channel else None,
        use_browser=False,
        publish=f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if upload else None,
        skip_markdown=True,
        title=meta.get("title"),
        download_media=lambda folder, name: rumble_download(source, folder, name),
    )


def rumble_source(url: str) -> str | None:
    """The page or embed URL without query or fragment, or None for
    non-rumble URLs."""
    match = RUMBLE_URL.match(url)
    if not match:
        return None
    if match.group("page"):
        return f"https://rumble.com/{match.group('page')}"
    return f"https://rumble.com/embed/{match.group('embed')}/"


def yt_dlp(args: list[str]) -> subprocess.CompletedProcess:
    # Rumble's API answers a plain client with 403; a browser's TLS
    # fingerprint, via curl_cffi, gets through.
    command = ["yt-dlp", "--no-warnings", "--impersonate", "chrome"]
    return subprocess.run(command + args, capture_output=True, text=True)


def rumble_download(source: str, folder: Path, name: str) -> None:
    """Max-quality archival download: one mkv with thumbnail, metadata,
    chapters, and the info-json embedded. No subtitles, auto-subs, or
    sponsorblock: rumble serves none of them."""
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
            "--embed-info-json",
            "--write-info-json",
            # A --force re-capture means the existing copy is wrong or
            # stale. Without this yt-dlp keeps it and only the info.json
            # is rewritten, leaving metadata describing a file that is
            # not there.
            "--force-overwrites",
            "-o",
            str(folder / f"{name}.%(ext)s"),
            source,
        ]
    )
    if result.returncode != 0:
        detail = " ".join(result.stderr.split())[:300]
        raise RuntimeError(f"video download failed for {source}: {detail}")
    if not (folder / f"{name}.mkv").exists():
        raise RuntimeError(f"yt-dlp wrote no video for {source}")
