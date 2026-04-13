#!/usr/bin/env python3
"""Fetch 30-second audio previews from YouTube for each record in catalog.json.

Requirements:
    brew install yt-dlp ffmpeg

Usage:
    python fetch_audio.py                  # fetch all missing audio
    python fetch_audio.py --force          # re-fetch even if file exists
    python fetch_audio.py --slug some-slug # fetch a single record
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TRACKS = Path(__file__).resolve().parent.parent / "data" / "standout_tracks.json"
AUDIO_DIR = Path(__file__).resolve().parent.parent / "audio"
CLIP_DURATION = 30  # seconds
CLIP_START = 60     # skip intros — start clip at 1 minute in


def check_deps() -> None:
    for cmd in ("yt-dlp", "ffmpeg"):
        result = subprocess.run(["which", cmd], capture_output=True)
        if result.returncode != 0:
            print(f"ERROR: '{cmd}' not found. Install with: brew install {cmd}")
            sys.exit(1)


def clean_query(artist: str, title: str) -> str:
    """Build a clean YouTube search query by stripping catalog numbers,
    format codes, and pressing info that confuse search results."""
    import re

    # If artist is a catalog number (letters + optional space/dash + digits), ditch it
    artist_clean = ""
    if not re.match(r"^[A-Z]{2,}[\s\-]?\d+", artist.strip(), re.IGNORECASE):
        artist_clean = artist.strip()

    combined = f"{artist_clean} {title}".strip()

    # Strip leading catalog-number prefix from the whole string
    combined = re.sub(r"^[A-Z]{2,}[\s\-]?\d+\S*\s+", "", combined, flags=re.IGNORECASE)

    # Strip leading bare numbers (e.g. "1 MF DOOM")
    combined = re.sub(r"^\d+\s+", "", combined)

    # Strip format/pressing codes
    combined = re.sub(
        r"\b(US2LP|UKLP|EU2LP|UK2LP|UK12|UK7|US7|EULP|2LP|LP|EP|"
        r"NM|VG\+|VG|MINT|COLORED\s+VINYL|COLOR\s+VINYL|UNKNOWN)\b",
        "", combined, flags=re.IGNORECASE,
    )

    # Strip parentheticals and long runs of punctuation
    combined = re.sub(r"\(.*?\)", "", combined)
    combined = re.sub(r"\s{2,}", " ", combined).strip(" -–/|,.")
    return combined


def search_and_download(artist: str, title: str, slug: str, force: bool, record: dict = {}) -> bool:
    out_path = AUDIO_DIR / f"{slug}.mp3"

    if out_path.exists() and not force:
        print(f"  [skip] {slug}.mp3 already exists")
        return True

    query = record.get("search") or f"{artist} {title}"
    print(f"  Searching: {query}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Search YouTube and download best audio for top result
        dl_result = subprocess.run(
            [
                "yt-dlp",
                f"ytsearch1:{query}",
                "--no-playlist",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "5",        # ~128kbps — fine for previews
                "--output", str(tmp / "%(id)s.%(ext)s"),
                "--quiet",
                "--no-warnings",
                "--match-filter", "duration > 90",  # skip very short clips
            ],
            capture_output=True,
            text=True,
        )

        if dl_result.returncode != 0:
            print(f"  [fail] yt-dlp error: {dl_result.stderr.strip()[:120]}")
            return False

        mp3_files = list(tmp.glob("*.mp3"))
        if not mp3_files:
            print(f"  [fail] no audio downloaded for: {query}")
            return False

        src = mp3_files[0]

        # Trim: start at CLIP_START seconds, take CLIP_DURATION seconds
        trim_result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(src),
                "-ss", str(CLIP_START),
                "-t", str(CLIP_DURATION),
                "-acodec", "libmp3lame",
                "-q:a", "5",
                "-loglevel", "error",
                str(out_path),
            ],
            capture_output=True,
            text=True,
        )

        if trim_result.returncode != 0:
            # If seek point is beyond track length, grab from start instead
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(src),
                    "-t", str(CLIP_DURATION),
                    "-acodec", "libmp3lame",
                    "-q:a", "5",
                    "-loglevel", "error",
                    str(out_path),
                ],
                check=True,
            )

    print(f"  [ok]   {slug}.mp3")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-fetch existing files")
    parser.add_argument("--slug", help="Only fetch a single record by slug")
    args = parser.parse_args()

    check_deps()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    with open(TRACKS, encoding="utf-8") as f:
        catalog = [t for t in json.load(f) if t.get("search")]

    if args.slug:
        catalog = [r for r in catalog if r["slug"] == args.slug]
        if not catalog:
            print(f"ERROR: slug '{args.slug}' not found in standout_tracks.json")
            sys.exit(1)

    total = len(catalog)
    ok = 0
    failed = []

    for i, record in enumerate(catalog, 1):
        artist = record.get("artist", "Unknown")
        title = record.get("track", "Unknown")
        slug = record["slug"]
        print(f"[{i}/{total}] {artist} — {title}")
        success = search_and_download(artist, title, slug, args.force, record)
        if success:
            ok += 1
        else:
            failed.append(f"{artist} — {title} ({slug})")

    print()
    print(f"Done: {ok}/{total} fetched successfully.")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")
        print("\nRetry failed ones manually:")
        print("  yt-dlp 'ytsearch1:ARTIST TITLE' --extract-audio --audio-format mp3")


if __name__ == "__main__":
    main()
