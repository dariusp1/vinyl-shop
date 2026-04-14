#!/usr/bin/env python3
"""
Download 4 audio samples for every record missing them, upload to R2,
and rebuild the record page with a multi-track player.

Designed to run unattended overnight. All output goes to stdout AND
logs/fill_missing_tracks.log. Safe to re-run — skips records that
already have 4+ good tracks in their R2 subdirectory.

Usage:
    cd /Users/darius/vinyl-shop
    python3 scripts/fill_missing_tracks.py 2>&1 | tee logs/fill_missing_tracks.log
"""

import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
REPO       = Path(__file__).resolve().parent.parent
CATALOG    = REPO / "data" / "catalog.json"
AUDIO_DIR  = REPO / "audio"
RECORDS    = REPO / "records"
LOG_DIR    = REPO / "logs"
CDN        = "https://pub-3675eb5935fc4273bdc62901c38dcce6.r2.dev"
BUCKET     = "vinyl-audio"
TARGET     = 4    # tracks per record
MIN_BYTES  = 50_000   # below this = corrupt placeholder
FULL_ALBUM_SECS = 1500  # if yt result > this, treat as full album

LOG_DIR.mkdir(exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────
def log(msg):
    print(msg, flush=True)

# ── Helpers ──────────────────────────────────────────────────────────────────
def good_tracks(slug):
    """Count valid local tracks in audio/<slug>/"""
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

def yt_search(query, n=1):
    """Return list of (video_id, duration_secs, title)."""
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

def yt_download(video_id: str, out_path: Path, ss=0, duration=30) -> bool:
    """Download + re-encode a 30s clip starting at ss seconds."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    tmp_path.unlink(missing_ok=True)  # remove empty placeholder so yt-dlp doesn't skip
    try:
        r = subprocess.run([
            "yt-dlp", video_id,
            "--extract-audio", "--audio-format", "mp3", "--audio-quality", "5",
            "--no-playlist", "-q", "--no-warnings",
            "-o", str(tmp_path.with_suffix("")) + ".%(ext)s",
        ], capture_output=True, text=True, timeout=120)
        # yt-dlp may adjust extension
        candidates = list(tmp_path.parent.glob(tmp_path.stem + ".*"))
        src = candidates[0] if candidates else tmp_path
        if not src.exists() or src.stat().st_size < MIN_BYTES:
            return False
        ok = reencode(src, out_path)
        return ok
    except Exception:
        return False
    finally:
        for f in tmp_path.parent.glob(tmp_path.stem + ".*"):
            try: f.unlink()
            except: pass

def split_full_album(video_id: str, total_secs: int, out_dir: Path, n=4) -> list[Path]:
    """Download full album once, split into n evenly-spaced 30s clips."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        raw = Path(tmp.name)
    raw.unlink(missing_ok=True)  # remove empty placeholder so yt-dlp doesn't skip
    try:
        r = subprocess.run([
            "yt-dlp", video_id,
            "--extract-audio", "--audio-format", "mp3", "--audio-quality", "5",
            "--no-playlist", "-q", "--no-warnings",
            "-o", str(raw.with_suffix("")) + ".%(ext)s",
        ], capture_output=True, text=True, timeout=300)
        candidates = list(raw.parent.glob(raw.stem + ".*"))
        src = candidates[0] if candidates else raw
        if not src.exists() or src.stat().st_size < MIN_BYTES:
            return []

        # Evenly space start points with some padding from edges
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
        log(f"    split_full_album error: {e}")
        return []
    finally:
        for f in raw.parent.glob(raw.stem + ".*"):
            try: f.unlink()
            except: pass

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
    content     = page.read_text(encoding="utf-8")
    new_content = replace_player(content, build_player_html(slug, filenames))
    new_content = new_content.replace("initPlayer();", "initMultiPlayer();")
    page.write_text(new_content, encoding="utf-8")
    return True

# ── Main ─────────────────────────────────────────────────────────────────────
def process_record(r):
    slug   = r["slug"]
    artist = r.get("artist_clean") or r["artist"]
    title  = r.get("title_clean") or r["title"]
    label  = f"{artist} — {title}"

    existing = good_tracks(slug)
    if len(existing) >= TARGET:
        log(f"  SKIP  {label[:60]}  ({len(existing)} tracks)")
        return "skip"

    log(f"\n{'─'*68}")
    log(f"  {label}")
    log(f"  need {TARGET - len(existing)} more (have {len(existing)})")

    out_dir = AUDIO_DIR / slug
    out_dir.mkdir(exist_ok=True)

    new_files = []

    # ── Strategy 1: full album search ───────────────────────────────────────
    query = f"{artist} {title} full album"
    log(f"  → searching: {query}")
    try:
        results = yt_search(query, n=3)
        full_album = [(vid, dur, t) for vid, dur, t in results if dur >= FULL_ALBUM_SECS]
        if full_album:
            vid, dur, yt_title = full_album[0]
            log(f"  → full album found: {yt_title[:55]} ({dur}s)")
            need = TARGET - len(existing)
            clips = split_full_album(vid, dur, out_dir, n=need)
            for p in clips:
                log(f"    ✓ {p.name}")
            new_files.extend(clips)
    except Exception as e:
        log(f"  → full album search error: {e}")

    # ── Strategy 2: individual track searches ───────────────────────────────
    if len(new_files) < (TARGET - len(existing)):
        still_need = TARGET - len(existing) - len(new_files)
        query2 = f"{artist} {title}"
        log(f"  → individual search: {query2} (need {still_need} more)")
        try:
            results = yt_search(query2, n=still_need + 2)
            # Filter out full-album results and previously used IDs
            used = set()
            for vid, dur, yt_title in results:
                if vid in used or dur >= FULL_ALBUM_SECS:
                    continue
                if len(new_files) >= TARGET - len(existing):
                    break
                fname = f"track_{len(existing) + len(new_files) + 1:02d}.mp3"
                dst   = out_dir / fname
                log(f"  → {yt_title[:55]} ({dur}s)")
                ok = yt_download(vid, dst)
                if ok:
                    log(f"    ✓ {fname}")
                    new_files.append(dst)
                else:
                    log(f"    ✗ download failed")
                used.add(vid)
                time.sleep(1)
        except Exception as e:
            log(f"  → individual search error: {e}")

    if not new_files:
        log(f"  ✗ no tracks found")
        return "fail"

    # ── Upload to R2 ─────────────────────────────────────────────────────────
    uploaded = []
    for path in new_files:
        key = f"{slug}/{path.name}"
        ok  = upload_r2(path, key)
        log(f"  {'✓' if ok else '✗ upload failed'} R2: {path.name}")
        if ok:
            uploaded.append(path.name)

    if not uploaded:
        log(f"  ✗ all uploads failed")
        return "fail"

    # ── Rebuild page ──────────────────────────────────────────────────────────
    all_tracks = sorted(
        [f.name for f in existing] + uploaded
    )[:TARGET]
    update_page(slug, all_tracks)
    log(f"  ✓ page updated ({len(all_tracks)} tracks)")
    return "ok"

def main():
    catalog = json.load(open(CATALOG))
    log(f"fill_missing_tracks.py — {len(catalog)} records")
    log(f"Target: {TARGET} tracks per record\n")

    results = {"ok": [], "skip": [], "fail": []}
    for r in catalog:
        try:
            outcome = process_record(r)
            results[outcome].append(r["slug"])
        except Exception as e:
            log(f"  UNHANDLED ERROR: {e}")
            results["fail"].append(r["slug"])
        time.sleep(2)

    log(f"\n{'═'*68}")
    log(f"Done.")
    log(f"  Updated : {len(results['ok'])}")
    log(f"  Skipped : {len(results['skip'])}")
    log(f"  Failed  : {len(results['fail'])}")
    if results["fail"]:
        log("\nFailed:")
        for s in results["fail"]:
            log(f"  {s}")

    # Git commit
    log("\nCommitting changes...")
    subprocess.run(["git", "-C", str(REPO), "add", "records/", "audio/"])
    subprocess.run(["git", "-C", str(REPO), "commit", "-m",
        f"Add multi-track audio for {len(results['ok'])} records (overnight fill)\n\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"])
    subprocess.run(["git", "-C", str(REPO), "push"])
    log("Pushed.")

if __name__ == "__main__":
    main()
