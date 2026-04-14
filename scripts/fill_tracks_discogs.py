#!/usr/bin/env python3
"""
Fill missing tracks using Discogs video links as primary source,
falling back to yt-dlp search. Processes N records at a time (default 3).

Usage:
    cd /Users/darius/vinyl-shop
    python3 scripts/fill_tracks_discogs.py            # process next 3 missing
    python3 scripts/fill_tracks_discogs.py --batch 5  # process next 5
    python3 scripts/fill_tracks_discogs.py --all      # process all missing
    python3 scripts/fill_tracks_discogs.py --slug nujabes-...  # one specific record
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

DISCOGS_UA = "VinylShopScript/1.0 +https://github.com/your-repo"

# ── Logging ──────────────────────────────────────────────────────────────────
def log(msg): print(msg, flush=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
def good_tracks(slug):
    d = AUDIO_DIR / slug
    if not d.exists():
        return []
    return sorted(f for f in d.glob("*.mp3") if f.stat().st_size > MIN_BYTES)

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

def yt_download(video_id: str, out_path: Path) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    tmp_path.unlink(missing_ok=True)  # remove placeholder so yt-dlp doesn't skip
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

def split_full_album(video_id: str, total_secs: int, out_dir: Path, n: int) -> list[Path]:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        raw = Path(tmp.name)
    raw.unlink(missing_ok=True)  # remove placeholder so yt-dlp doesn't skip
    try:
        subprocess.run([
            "yt-dlp", video_id,
            "--extract-audio", "--audio-format", "mp3", "--audio-quality", "5",
            "--no-playlist", "-q", "--no-warnings",
            "-o", str(raw.with_suffix("")) + ".%(ext)s",
        ], capture_output=True, text=True, timeout=300)
        candidates = list(raw.parent.glob(raw.stem + ".*"))
        src = candidates[0] if candidates else raw
        if not src.exists() or src.stat().st_size < MIN_BYTES:
            return []

        pad    = max(30, total_secs // 10)
        usable = total_secs - 2 * pad
        step   = usable / (n - 1) if n > 1 else usable
        starts = [int(pad + i * step) for i in range(n)]

        results = []
        for i, start in enumerate(starts, 1):
            dst = out_dir / f"track_{i:02d}.mp3"
            r2 = subprocess.run([
                "ffmpeg", "-y", "-ss", str(start), "-i", str(src),
                "-t", "30", "-ar", "44100", "-ac", "1", "-b:a", "96k",
                str(dst), "-loglevel", "error"
            ], capture_output=True)
            if r2.returncode == 0 and dst.stat().st_size > MIN_BYTES:
                results.append(dst)
        return results
    except Exception as e:
        log(f"    split error: {e}")
        return []
    finally:
        for f in raw.parent.glob(raw.stem + ".*"):
            try: f.unlink()
            except: pass

def yt_search(query, n=1):
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

# ── Discogs lookup ────────────────────────────────────────────────────────────
def discogs_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": DISCOGS_UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception:
        return None

def discogs_videos(artist, title, slug):
    """Return list of (video_id, duration_secs, title) from Discogs Videos section."""
    # Try to extract catalog number from slug (first hyphen-separated token(s))
    catno_guess = slug.split("-")[0].upper()

    query = urllib.parse.urlencode({
        "artist": artist, "release_title": title,
        "type": "release", "per_page": "5"
    })
    data = discogs_get(f"https://api.discogs.com/database/search?{query}")
    if not data or not data.get("results"):
        return []

    # Prefer result whose catno matches slug prefix
    results = data["results"]
    best = None
    for res in results:
        if catno_guess in res.get("catno", "").upper().replace("-", "").replace(" ", ""):
            best = res
            break
    if not best:
        best = results[0]

    release = discogs_get(f"https://api.discogs.com/releases/{best['id']}")
    if not release:
        return []

    videos = []
    for v in release.get("videos", []):
        uri = v.get("uri", "")
        m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", uri)
        if not m:
            continue
        vid_id = m.group(1)
        dur = v.get("duration", 0)
        title_v = v.get("title", "")
        videos.append((vid_id, dur, title_v))

    # Deduplicate by video ID
    seen = set()
    unique = []
    for item in videos:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)
    return unique

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

    existing = good_tracks(slug)
    if len(existing) >= TARGET:
        log(f"  SKIP  {label[:60]}  ({len(existing)} tracks)")
        return "skip"

    need = TARGET - len(existing)
    log(f"\n{'─'*68}")
    log(f"  {label}")
    log(f"  need {need} more (have {len(existing)})")

    out_dir = AUDIO_DIR / slug
    out_dir.mkdir(exist_ok=True)

    new_files = []

    # ── Strategy 1: Discogs videos ────────────────────────────────────────────
    log(f"  → fetching Discogs videos…")
    time.sleep(1)  # be polite to Discogs API
    videos = discogs_videos(artist, title, slug)
    log(f"  → {len(videos)} Discogs video(s) found")

    if videos:
        # Check for full album video first
        full_albums = [(vid, dur, t) for vid, dur, t in videos if dur >= FULL_ALBUM_SECS]
        track_videos = [(vid, dur, t) for vid, dur, t in videos if dur < FULL_ALBUM_SECS]

        if full_albums:
            vid, dur, yt_title = full_albums[0]
            log(f"  → full album: {yt_title[:55]} ({dur}s)")
            clips = split_full_album(vid, dur, out_dir, n=need)
            for p in clips:
                log(f"    ✓ {p.name}")
            new_files.extend(clips)

        # Download individual track videos
        for vid, dur, yt_title in track_videos:
            if len(new_files) >= need:
                break
            n_have = len(existing) + len(new_files)
            fname = f"track_{n_have + 1:02d}.mp3"
            dst   = out_dir / fname
            log(f"  → {yt_title[:55]} ({dur}s)")
            ok = yt_download(vid, dst)
            if ok:
                log(f"    ✓ {fname}")
                new_files.append(dst)
            else:
                log(f"    ✗ failed")
            time.sleep(1)

    # ── Strategy 2: yt-dlp search fallback ───────────────────────────────────
    if len(new_files) < need:
        still_need = need - len(new_files)
        query = f"{artist} {title}"
        log(f"  → search fallback: {query} (need {still_need} more)")
        try:
            results = yt_search(query, n=still_need + 3)
            used = set(v[0] for v in videos)  # don't re-try Discogs IDs
            for vid, dur, yt_title in results:
                if len(new_files) >= need:
                    break
                if vid in used or dur >= FULL_ALBUM_SECS:
                    continue
                n_have = len(existing) + len(new_files)
                fname = f"track_{n_have + 1:02d}.mp3"
                dst   = out_dir / fname
                log(f"  → {yt_title[:55]} ({dur}s)")
                ok = yt_download(vid, dst)
                if ok:
                    log(f"    ✓ {fname}")
                    new_files.append(dst)
                else:
                    log(f"    ✗ failed")
                used.add(vid)
                time.sleep(1)
        except Exception as e:
            log(f"  → search error: {e}")

    if not new_files:
        log(f"  ✗ no tracks found")
        return "fail"

    # ── Upload ────────────────────────────────────────────────────────────────
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

    # ── Rebuild page ──────────────────────────────────────────────────────────
    all_tracks = sorted([f.name for f in existing] + uploaded)[:TARGET]
    update_page(slug, all_tracks)
    log(f"  ✓ page updated ({len(all_tracks)} tracks)")
    return "ok"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=3, help="records to process (default 3)")
    parser.add_argument("--all",   action="store_true",  help="process all missing records")
    parser.add_argument("--slug",  type=str, default=None, help="process one specific slug")
    args = parser.parse_args()

    catalog = json.load(open(CATALOG))

    if args.slug:
        records = [r for r in catalog if r["slug"] == args.slug]
        if not records:
            log(f"Slug not found: {args.slug}")
            sys.exit(1)
    else:
        # Find records that need tracks
        needs = []
        for r in catalog:
            if len(good_tracks(r["slug"])) < TARGET:
                needs.append(r)
        if args.all:
            records = needs
        else:
            records = needs[:args.batch]

    log(f"fill_tracks_discogs.py — processing {len(records)} record(s)")

    results = {"ok": [], "skip": [], "fail": []}
    for r in records:
        try:
            outcome = process_record(r)
            results[outcome].append(r["slug"])
        except Exception as e:
            log(f"  UNHANDLED ERROR: {e}")
            results["fail"].append(r["slug"])
        time.sleep(2)

    log(f"\n{'═'*68}")
    log(f"Done.  Updated: {len(results['ok'])}  Skipped: {len(results['skip'])}  Failed: {len(results['fail'])}")
    if results["fail"]:
        log("Failed:")
        for s in results["fail"]:
            log(f"  {s}")

if __name__ == "__main__":
    main()
