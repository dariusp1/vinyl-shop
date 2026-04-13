#!/usr/bin/env python3
"""
Fetch cover art from Discogs using release IDs embedded in snippet filenames.

Snippet filenames like sf305367-01-01-01.mp3 → Discogs release 305367.
Downloads cover to assets/covers/<slug>.jpg.

Usage:
    python fetch_covers.py
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO       = Path(__file__).resolve().parent.parent
AUDIO_DIR  = REPO / "audio"
COVERS_DIR = REPO / "assets" / "covers"
CATALOG    = REPO / "data" / "catalog.json"

# Map slug → Discogs release ID (extracted from sf* snippet filenames)
SLUG_TO_RELEASE_ID = {
    "arilp-025-ariwa-sounds-mad-professor-a-caribbean-taste-of-re": "730508",
    "rmm-0561-9d7778-chrysalis-de-la-soul-aoi-bionix-hip-hop-eu2l": "86514",
    "bf-105-brainfeeder-thundercat-fair-chance-floating-points-ho": "800441",
    "jid-019lp-jazz-is-dead-adrian-younge-instrumentals-jid019-bl": "965141",
    "rse-0084-1-mf-doom-mmfood-colored-vinyl-us2lp": "305367",
    "ere-712-empire-blackground-aaliyah-one-in-a-million": "842829",
    "jid-016lp-jazz-is-dead-phil-ranelin-wendell-harrison": "919447",
    "ere-863-empire-larry-june-spaceships-on-the-blade-uk2lp-unkn": "926204",
    "joyce-wrice-stay-around-uslp-unknown": "902694",
    "ere-811-griselda-records-empire-benny-the-butcher-tana-talk": "871115",
    "sth-2110-stones-throw-quasimoto-us2lp-unknown": "177418",
    "fat-possum-armand-hammer-us2lp-unknown": "964734",
    "ere-956-drumwork-music-group-llc-conway-the-machine-wont-he": "946293",
    "arilp-005-ariwa-sounds-mad-professor-dub-me-crazy-pt-3-the-r": "512065",
    "arilp-011-ariwa-sounds-mad-professor-dub-me-crazy-pt-4-escap": "504635",
}


def fetch_cover_url(release_id: str) -> str | None:
    url = f"https://api.discogs.com/releases/{release_id}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "OSNSVinylShop/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        images = data.get("images", [])
        # Prefer primary image
        for img in images:
            if img.get("type") == "primary":
                return img.get("uri") or img.get("uri150")
        # Fall back to first image
        if images:
            return images[0].get("uri") or images[0].get("uri150")
    except Exception as e:
        print(f"  [error] Discogs API: {e}")
    return None


def download_image(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OSNSVinylShop/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"  [error] download failed: {e}")
        return False


def main() -> None:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, []

    total = len(SLUG_TO_RELEASE_ID)
    for i, (slug, release_id) in enumerate(SLUG_TO_RELEASE_ID.items(), 1):
        dest = COVERS_DIR / f"{slug}.jpg"
        if dest.exists():
            print(f"[{i}/{total}] [skip] {slug}")
            ok += 1
            continue

        print(f"[{i}/{total}] {slug}")
        print(f"  Fetching Discogs release {release_id}...")
        img_url = fetch_cover_url(release_id)
        if not img_url:
            print(f"  [fail] no image found")
            failed.append(slug)
            time.sleep(1)
            continue

        print(f"  Downloading cover...")
        if download_image(img_url, dest):
            print(f"  [ok] saved to {dest.name}")
            ok += 1
        else:
            failed.append(slug)

        # Be polite to Discogs API — 1 request/sec
        time.sleep(1.1)

    print(f"\nDone: {ok}/{total} covers fetched.")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
