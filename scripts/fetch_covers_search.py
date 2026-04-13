#!/usr/bin/env python3
"""
Fetch cover art from Discogs by searching artist + title.
Uses a hardcoded mapping of clean artist/title pairs derived from catalog data.

Usage:
    python fetch_covers_search.py
"""

import json
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

REPO       = Path(__file__).resolve().parent.parent
COVERS_DIR = REPO / "assets" / "covers"

# Clean artist/title pairs for records without known Discogs release IDs
# Format: slug → (artist, title)
SEARCH_MAP = {
    "lacr-031-la-club-resource-delroy-edwards-change-the-world-ho": ("Delroy Edwards", "Change The World"),
    "mm-39-mahogani-music-randolph-in-the-company-of-others-ep-ho": ("Paul Randolph", "In The Company Of Others"),
    "odiliv-002lp-odion-livingstone-grotto-at-last-funk-uklp-odio": ("Odion Livingstone", "Grotto At Last"),
    "odiliv-003lp-odion-livingstone-apples-mind-twister-funk-uklp": ("Odion Livingstone", "Apples Mind Twister"),
    "rhm-0102-rush-hour-rick-wilhite-vibes-2-part-2-house-eu2lp-2": ("Rick Wilhite", "Vibes 2 Part 2"),
    "asa103-as-shams-black-disco-discovery":                        ("AS", "Black Disco Discovery"),
    "bf-7135-brainfeeder-thundercat-tame-impala-no-more-lies-rock": ("Thundercat", "No More Lies"),
    "nbn011-nbn-records-jamma-dee-perceptions-hip-hop-eu2lp-nothi": ("Jamma-Dee", "Perceptions"),
    "nts-tadyk-nts-amaarae-the-angel-you-dont-know-hip-hop-uklp-1": ("Amaarae", "The Angel You Don't Know"),
    "apnea-104-apnea-hieroglyphic-being-the-moon-dance-eu2lp-unkn": ("Hieroglyphic Being", "The Moon Dance"),
    "sth-2126lp-stones-throw-j-dilla-donuts-smile-cover-us2lp-fin": ("J Dilla", "Donuts"),
    "rm079bis-roche-musique-fkj-french-kiwi-juice-just-piano-hip":  ("FKJ", "Just Piano"),
    "outs07-outsider-parliament-funkadelic-get-up-off-your-ass":    ("Funkadelic", "Get Up Off Your Ass"),
    "eqt121912-masego-lady-lady-hip-hop-uslp-unknown":              ("Masego", "Lady Lady"),
    "iot87lp-iot-records-azu-tiwaline-fifth-dream-techno-eu2lp-un": ("Azu Tiwaline", "Fifth Dream"),
    "whp1473-whp-archie-shepp-live-in-europe-jazz-eu2lp-unknown":   ("Archie Shepp", "Live In Europe"),
    "nsd235lp-nature-sounds-talib-kweli-madlib-liberation-2-hip-h": ("Talib Kweli & Madlib", "Liberation 2"),
    "mms003ilp-madlib-invazion-madlib-medicine-show-no-3-beat-kon": ("Madlib", "Beat Konducta In Africa"),
    "643511-ovo-sound-partynextdoor-partymobile-hip-hop-us2lp-the": ("PartyNextDoor", "Partymobile"),
    "defb003760601-def-jam-recordings-navy-blue-ways-of-knowing-h": ("Navy Blue", "Ways Of Knowing"),
    "rmm0551-aoi-records-de-la-soul-art-official-intelligence-mos": ("De La Soul", "Art Official Intelligence Mosaic Thump"),
    "uar015-delano-smith-norm-talley-straight-up-no-chaser-house":  ("Delano Smith & Norm Talley", "Straight Up No Chaser"),
    "js001-dj-harrison-monotones-hip-hop-uslp-studio-and-record-l": ("DJ Harrison", "Monotones"),
    "19658722231-john-legend-love-in-the-future-hip-hop-2lp-conta": ("John Legend", "Love In The Future"),
    "jazzr006-khan-jamal-infinity-jazz-uklp-unknown":               ("Khan Jamal", "Infinity"),
    "fw271-first-word-records-kaidi-tatham-only-way-house-uklp-th": ("Kaidi Tatham", "Only Way"),
    "bwood310lp-yussef-dayes-black-classical-music-jazz-2lp-unkno": ("Yussef Dayes", "Black Classical Music"),
    "apronevil03-apron-steven-julien-and-kyle-hall-crown-house-12": ("Funkinevil", "Crown"),
    "ast043-astral-black-jossy-mitsu-planet-j-2-ep-techno-uk12-a": ("Jossy Mitsu", "Planet J 2"),
    "bf-105-brainfeeder-thundercat-fair-chance-floating-points-ho": ("Thundercat", "Fair Chance"),
    "arilp-025-ariwa-sounds-mad-professor-a-caribbean-taste-of-re": ("Mad Professor", "Caribbean Taste Of Technology"),
    "ere-956-drumwork-music-group-llc-conway-the-machine-wont-he":  ("Conway The Machine", "Won't He Do It"),
    "ere-863-empire-larry-june-spaceships-on-the-blade-uk2lp-unkn": ("Larry June", "Spaceships On The Blade"),
    "joyce-wrice-stay-around-uslp-unknown":                         ("Joyce Wrice", "Stay Around"),
    # Records with no known identity — skip (placeholders generated separately)
    # "lb-0097lp180-luaka-bop-eulp-unknown": unknown Luaka Bop release
    # "ss095-96": unclear catalog entry
    # "ziq457-planet-mu-unknown": unknown Planet Mu release
    # "mrblp178rb-mr-bongo-unknown": unknown Mr. Bongo release
    # "odiliv-002lp-...": not on Discogs
    # "odiliv-003lp-...": not on Discogs
}


def search_discogs_release_id(artist: str, title: str) -> str | None:
    """Search Discogs and return the first release ID found."""
    params = {"type": "release", "per_page": "5"}
    if artist:
        params["artist"] = artist
    if title:
        params["release_title"] = title

    url = "https://api.discogs.com/database/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "OSNSVinylShop/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if results:
            return str(results[0]["id"])
    except urllib.error.HTTPError as e:
        print(f"  [error] search HTTP {e.code}: {e.reason}")
        if e.code == 429:
            print("  Rate limited — waiting 30s...")
            time.sleep(30)
    except Exception as e:
        print(f"  [error] search: {e}")
    return None


def fetch_image_url_from_release(release_id: str) -> str | None:
    """Fetch the primary image URL from a Discogs release page."""
    url = f"https://api.discogs.com/releases/{release_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "OSNSVinylShop/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        images = data.get("images", [])
        for img in images:
            if img.get("type") == "primary":
                return img.get("uri") or img.get("uri150")
        if images:
            return images[0].get("uri") or images[0].get("uri150")
    except urllib.error.HTTPError as e:
        print(f"  [error] release HTTP {e.code}: {e.reason}")
        if e.code == 429:
            print("  Rate limited — waiting 30s...")
            time.sleep(30)
    except Exception as e:
        print(f"  [error] release: {e}")
    return None


def search_discogs(artist: str, title: str) -> str | None:
    """Search Discogs and return a cover image URL, or None."""
    release_id = search_discogs_release_id(artist, title)
    if not release_id:
        return None
    time.sleep(1.5)  # brief pause before second API call
    return fetch_image_url_from_release(release_id)


def download_image(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OSNSVinylShop/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 2000:
            return False  # probably a placeholder/spacer
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"  [error] download: {e}")
        return False


def main() -> None:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)

    # Only process records without existing covers
    todo = {
        slug: pair
        for slug, pair in SEARCH_MAP.items()
        if not (COVERS_DIR / f"{slug}.jpg").exists()
    }

    print(f"Fetching covers for {len(todo)} records...\n")
    ok, failed = 0, []

    for i, (slug, (artist, title)) in enumerate(todo.items(), 1):
        print(f"[{i}/{len(todo)}] {slug[:60]}")
        print(f"  Search: {artist!r} / {title!r}")

        img_url = search_discogs(artist, title)

        # Retry with just title if artist+title returned nothing
        if not img_url and artist:
            print(f"  Retrying title only...")
            time.sleep(2)
            img_url = search_discogs("", title)

        if not img_url:
            print(f"  [fail] not found")
            failed.append(slug)
            time.sleep(2)
            continue

        dest = COVERS_DIR / f"{slug}.jpg"
        if download_image(img_url, dest):
            print(f"  [ok]")
            ok += 1
        else:
            print(f"  [fail] download")
            failed.append(slug)

        # 2s between requests to stay well under Discogs 60/min limit
        time.sleep(2)

    print(f"\nDone: {ok}/{len(todo)} covers fetched.")
    if failed:
        print("Failed:")
        for s in failed:
            print(f"  {s}")


if __name__ == "__main__":
    main()
