#!/usr/bin/env python3
"""
Second pass: replace tracks that were sourced from blind search with
ones found by searching each track name from the Discogs tracklist.

Usage:
    cd /Users/darius/vinyl-shop
    python3 scripts/repass_tracklist.py           # all search-fallback records
    python3 scripts/repass_tracklist.py --slug whp1473-...
    python3 scripts/repass_tracklist.py --list    # show which records qualify
"""

import argparse, json, os, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────
REPO      = Path(__file__).resolve().parent.parent
CATALOG   = REPO / "data" / "catalog.json"
AUDIO_DIR = REPO / "audio"
RECORDS   = REPO / "records"
CDN       = "https://pub-3675eb5935fc4273bdc62901c38dcce6.r2.dev"
BUCKET    = "vinyl-audio"
TARGET    = 4
MIN_BYTES = 50_000
FULL_ALBUM_SECS = 1500
DISCOGS_UA = "VinylShopScript/1.0"

# Records that used blind search fallback (no/failed Discogs videos).
# These are the ones worth redoing with tracklist-based search.
SEARCH_FALLBACK_SLUGS = [
    "whp1473-whp-archie-shepp-live-in-europe-jazz-eu2lp-unknown",
    "mms003ilp-madlib-invazion-madlib-medicine-show-no-3-beat-kon",
    "rmm0551-aoi-records-de-la-soul-art-official-intelligence-mos",
    "asa103-the-sun-black-disco-discovery-1975-1976",
    "mlp-15021-capitol-records-george-clinton-parliament-funkadel",
    "apronevil03-apron-steven-julien-and-kyle-hall-crown-house-12",
    "rm079bis-roche-musique-fkj-french-kiwi-juice-just-piano-hip",        # Discogs vids failed
    "bf-7135-brainfeeder-thundercat-tame-impala-no-more-lies-rock",       # partial search
    "nsd235lp-nature-sounds-talib-kweli-madlib-liberation-2-hip-h",       # partial (interview snuck in)
    "outs07-outsider-parliament-funkadelic-get-up-off-your-ass",          # partial search
    "ssv090-ab-sound-signature-theo-parrish-maurissa-rose-free-my",       # partial search
    "defb003760601-def-jam-recordings-navy-blue-ways-of-knowing-h",       # 0s reaction vids
]

# ── Logging ──────────────────────────────────────────────────────────────────
def log(msg): print(msg, flush=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
def reencode(src: Path, dst: Path) -> bool:
    r = subprocess.run([
        "ffmpeg", "-y", "-i", str(src),
        "-t", "30", "-ar", "44100", "-ac", "1", "-b:a", "96k",
        str(dst), "-loglevel", "error"
    ], capture_output=True)
    return r.returncode == 0 and dst.exists() and dst.stat().st_size > MIN_BYTES

def upload_r2(local: Path, key: str) -> bool:
    r = subprocess.run([
        "wrangler", "r2", "object", "put", f"{BUCKET}/{key}",
        "--file", str(local), "--content-type", "audio/mpeg", "--remote"
    ], capture_output=True, text=True)
    return "Upload complete" in r.stdout

def yt_search_track(query, n=3):
    """Search YouTube, return list of (video_id, duration_secs, title)."""
    r = subprocess.run([
        "yt-dlp", f"ytsearch{n}:{query}",
        "--print", "%(id)s\t%(duration)s\t%(title)s",
        "--no-playlist", "-q", "--no-warnings"
    ], capture_output=True, text=True, timeout=30)
    results = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            try:
                results.append((parts[0], int(parts[1]), parts[2]))
            except ValueError:
                pass
    return results

def yt_download(video_id: str, out_path: Path) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    tmp_path.unlink(missing_ok=True)
    try:
        subprocess.run([
            "yt-dlp", video_id,
            "--extract-audio", "--audio-format", "mp3", "--audio-quality", "5",
            "--no-playlist", "-q", "--no-warnings",
            "-o", str(tmp_path.with_suffix("")) + ".%(ext)s",
        ], capture_output=True, text=True, timeout=120)
        candidates = list(tmp_path.parent.glob(tmp_path.stem + ".*"))
        src = candidates[0] if candidates else tmp_path
        if not src.exists() or src.stat().st_size < MIN_BYTES:
            return False
        return reencode(src, out_path)
    except Exception:
        return False
    finally:
        for f in tmp_path.parent.glob(tmp_path.stem + ".*"):
            try: f.unlink()
            except: pass

# ── Discogs ───────────────────────────────────────────────────────────────────
def discogs_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": DISCOGS_UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:
        log(f"    Discogs error: {e}")
        return None

def discogs_tracklist(artist, title, slug):
    """Return list of track titles from Discogs tracklist."""
    catno_guess = slug.split("-")[0].upper()
    query = urllib.parse.urlencode({
        "artist": artist, "release_title": title,
        "type": "release", "per_page": "5"
    })
    data = discogs_get(f"https://api.discogs.com/database/search?{query}")
    if not data or not data.get("results"):
        return []

    results = data["results"]
    best = None
    for res in results:
        if catno_guess in res.get("catno", "").upper().replace("-", "").replace(" ", ""):
            best = res
            break
    if not best:
        best = results[0]

    log(f"  → Discogs release: {best.get('title','')} [{best.get('catno','')}]")
    release = discogs_get(f"https://api.discogs.com/releases/{best['id']}")
    if not release:
        return []

    tracks = []
    for t in release.get("tracklist", []):
        title_t = t.get("title", "").strip()
        # Skip heading/index rows (no title or position looks like a side header)
        if title_t and t.get("type_", "track") == "track":
            tracks.append(title_t)
    return tracks

# ── Page builder ──────────────────────────────────────────────────────────────
def build_player_html(slug, filenames):
    items = []
    for fname in filenames:
        url = f"{CDN}/{slug}/{fname}"
        items.append(f"""        <div class="track-item">
            <div class="progress-bar"><div class="progress-fill"></div></div>
            <button class="play-button track-btn">&#9654; 试听</button>
            <audio preload="metadata" crossorigin="anonymous">
                <source src="{url}" type="audio/mpeg">
            </audio>
        </div>""")
    return (
        '        <div class="player-section">\n'
        '        <div class="track-list">\n'
        + "\n".join(items) + "\n"
        '        </div>\n'
        '        </div>'
    )

def replace_player(content, new_player):
    marker = '<div class="player-section">'
    start  = content.find(marker)
    if start == -1:
        return content
    depth, i = 0, start
    while i < len(content):
        if content[i:i+4] == "<div":   depth += 1; i += 4
        elif content[i:i+6] == "</div>": depth -= 1; i += 6
        else: i += 1
        if depth == 0: break
    return content[:start] + new_player + content[i:]

def update_page(slug, filenames):
    page = RECORDS / slug / "index.html"
    if not page.exists():
        return False
    content = page.read_text(encoding="utf-8")
    new_content = replace_player(content, build_player_html(slug, filenames))
    new_content = new_content.replace("initPlayer();", "initMultiPlayer();")
    page.write_text(new_content, encoding="utf-8")
    return True

# ── Process one record ────────────────────────────────────────────────────────
def process_record(r):
    slug   = r["slug"]
    artist = r.get("artist_clean") or r["artist"]
    title  = r.get("title_clean") or r["title"]
    label  = f"{artist} — {title}"

    log(f"\n{'─'*68}")
    log(f"  {label}")

    # Clear existing tracks
    out_dir = AUDIO_DIR / slug
    if out_dir.exists():
        for f in out_dir.glob("track_*.mp3"):
            f.unlink()
    out_dir.mkdir(exist_ok=True)

    # Fetch tracklist from Discogs
    log(f"  → fetching tracklist from Discogs…")
    time.sleep(1)
    tracks = discogs_tracklist(artist, title, slug)

    if not tracks:
        log(f"  ✗ no tracklist found, skipping")
        return "fail"

    log(f"  → {len(tracks)} tracks on release: {', '.join(tracks[:6])}{'…' if len(tracks) > 6 else ''}")

    # Pick TARGET tracks to search for (spread across the tracklist)
    if len(tracks) <= TARGET:
        pick = tracks
    else:
        step = len(tracks) / TARGET
        pick = [tracks[int(i * step)] for i in range(TARGET)]

    new_files = []
    for i, track_title in enumerate(pick, 1):
        query = f"{artist} {track_title}"
        log(f"  → [{i}/{len(pick)}] searching: {query}")
        try:
            results = yt_search_track(query, n=3)
            for vid, dur, yt_title in results:
                if dur >= FULL_ALBUM_SECS:
                    continue
                fname = f"track_{i:02d}.mp3"
                dst   = out_dir / fname
                log(f"      {yt_title[:60]} ({dur}s)")
                ok = yt_download(vid, dst)
                if ok:
                    log(f"      ✓ {fname}")
                    new_files.append(dst)
                    break
                else:
                    log(f"      ✗ failed, trying next…")
            else:
                if not new_files or new_files[-1].name != f"track_{i:02d}.mp3":
                    log(f"      ✗ no working result found")
        except Exception as e:
            log(f"      ✗ error: {e}")
        time.sleep(1)

    if not new_files:
        log(f"  ✗ no tracks downloaded")
        return "fail"

    # Upload to R2
    uploaded = []
    for path in new_files:
        key = f"{slug}/{path.name}"
        ok  = upload_r2(path, key)
        log(f"  {'✓' if ok else '✗'} R2: {path.name}")
        if ok:
            uploaded.append(path.name)

    if not uploaded:
        log(f"  ✗ all uploads failed")
        return "fail"

    update_page(slug, sorted(uploaded))
    log(f"  ✓ page updated ({len(uploaded)} tracks)")
    return "ok"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug",  help="process one specific slug")
    parser.add_argument("--list",  action="store_true", help="list qualifying records and exit")
    args = parser.parse_args()

    catalog = json.load(open(CATALOG))
    cat_by_slug = {r["slug"]: r for r in catalog}

    if args.slug:
        slugs = [args.slug]
    else:
        slugs = SEARCH_FALLBACK_SLUGS

    if args.list:
        log("Records queued for tracklist repass:")
        for s in slugs:
            r = cat_by_slug.get(s)
            if r:
                artist = r.get("artist_clean") or r["artist"]
                title  = r.get("title_clean") or r["title"]
                log(f"  {artist} — {title}")
            else:
                log(f"  {s} (not in catalog)")
        return

    log(f"repass_tracklist.py — {len(slugs)} record(s)\n")

    results = {"ok": [], "fail": []}
    for slug in slugs:
        r = cat_by_slug.get(slug)
        if not r:
            log(f"  SKIP (not in catalog): {slug}")
            continue
        try:
            outcome = process_record(r)
            results[outcome].append(slug)
        except Exception as e:
            log(f"  UNHANDLED ERROR: {e}")
            results["fail"].append(slug)
        time.sleep(2)

    log(f"\n{'═'*68}")
    log(f"Done.  Updated: {len(results['ok'])}  Failed: {len(results['fail'])}")
    if results["fail"]:
        log("Failed:")
        for s in results["fail"]:
            log(f"  {s}")

if __name__ == "__main__":
    main()
