#!/usr/bin/env python3
"""
Upload all audio files to Cloudflare R2 bucket via wrangler,
then update all record pages to use CDN URLs.

Usage:
    python scripts/upload_to_r2.py
"""

import subprocess
import sys
from pathlib import Path

REPO       = Path(__file__).resolve().parent.parent
AUDIO_DIR  = REPO / "audio"
RECORDS    = REPO / "records"
BUCKET     = "vinyl-audio"
CDN_BASE   = "https://pub-3675eb5935fc4273bdc62901c38dcce6.r2.dev"


def upload_file(local: Path, remote_key: str) -> bool:
    result = subprocess.run(
        ["wrangler", "r2", "object", "put", f"{BUCKET}/{remote_key}",
         "--file", str(local), "--content-type", "audio/mpeg"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [error] {result.stderr.strip()[:120]}")
        return False
    return True


def main():
    # Collect all mp3s
    mp3s = sorted(AUDIO_DIR.rglob("*.mp3"))
    total = len(mp3s)
    print(f"Uploading {total} files to R2 bucket '{BUCKET}'...\n")

    ok = 0
    for i, path in enumerate(mp3s, 1):
        # Remote key mirrors local path relative to AUDIO_DIR
        key = path.relative_to(AUDIO_DIR).as_posix()
        print(f"[{i}/{total}] {key}")
        if upload_file(path, key):
            ok += 1
            print(f"  [ok]")
        else:
            print(f"  [fail]")

    print(f"\nUploaded {ok}/{total} files.")

    # Update all record pages: replace relative audio src with CDN URLs
    print("\nUpdating record pages to use CDN URLs...")
    pages = list(RECORDS.rglob("index.html"))
    updated = 0
    for page in pages:
        content = page.read_text(encoding="utf-8")
        original = content

        # Replace ../../audio/ with CDN base URL
        content = content.replace("../../audio/", f"{CDN_BASE}/")

        if content != original:
            page.write_text(content, encoding="utf-8")
            updated += 1

    print(f"Updated {updated} record pages.")
    print(f"\nCDN base: {CDN_BASE}")


if __name__ == "__main__":
    main()
