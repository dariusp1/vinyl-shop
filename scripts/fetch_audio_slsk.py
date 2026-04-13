#!/usr/bin/env python3
"""Fetch 30-second audio previews via slskd (Soulseek) for each record in catalog.json.

Requires slskd running at localhost:5030.

Usage:
    python fetch_audio_slsk.py                  # fetch all missing audio
    python fetch_audio_slsk.py --force          # re-fetch even if file exists
    python fetch_audio_slsk.py --slug some-slug # fetch a single record
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

from dotenv import dotenv_values

CATALOG    = Path(__file__).resolve().parent.parent / "data" / "catalog.json"
TRACKS     = Path(__file__).resolve().parent.parent / "data" / "standout_tracks.json"
AUDIO_DIR  = Path(__file__).resolve().parent.parent / "audio"
ENV_FILE   = Path(__file__).resolve().parent.parent / ".env"
SLSKD_URL  = "http://localhost:5030"
CLIP_START = 60   # seconds into track to start clip
CLIP_DURATION = 30

# MP3 only — lower quality is fine for 30s previews
FORMAT_PRIORITY = [".mp3", ".ogg", ".m4a", ".flac", ".wav"]


def load_credentials() -> tuple[str, str]:
    env = dotenv_values(ENV_FILE)
    # slskd API login (web UI credentials, NOT Soulseek network credentials)
    username = env.get("SLSKD_API_USERNAME") or os.environ.get("SLSKD_API_USERNAME", "slskd")
    password = env.get("SLSKD_API_PASSWORD") or os.environ.get("SLSKD_API_PASSWORD", "slskd")
    return username, password


def get_token(username: str, password: str) -> str:
    resp = requests.post(
        f"{SLSKD_URL}/api/v0/session",
        json={"username": username, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def clean_query(artist: str, title: str) -> str:
    import re
    artist_clean = ""
    if not re.match(r"^[A-Z]{2,}[\s\-]?\d+", artist.strip(), re.IGNORECASE):
        artist_clean = artist.strip()
    combined = f"{artist_clean} {title}".strip()
    combined = re.sub(r"^[A-Z]{2,}[\s\-]?\d+\S*\s+", "", combined, flags=re.IGNORECASE)
    combined = re.sub(r"^\d+\s+", "", combined)
    combined = re.sub(
        r"\b(US2LP|UKLP|EU2LP|UK2LP|UK12|UK7|US7|EULP|2LP|LP|EP|"
        r"NM|VG\+|VG|MINT|COLORED\s+VINYL|COLOR\s+VINYL|UNKNOWN)\b",
        "", combined, flags=re.IGNORECASE,
    )
    combined = re.sub(r"\(.*?\)", "", combined)
    combined = re.sub(r"\s{2,}", " ", combined).strip(" -–/|,.")
    return combined


def search(session: requests.Session, query: str, timeout: int = 45) -> list[dict]:
    """Run a search and return all file results."""
    resp = session.post(
        f"{SLSKD_URL}/api/v0/searches",
        json={"searchText": query, "fileLimit": 200, "filterResponses": False},
    )
    resp.raise_for_status()
    search_id = resp.json()["id"]

    # Poll until search completes
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        status = session.get(f"{SLSKD_URL}/api/v0/searches/{search_id}").json()
        response_count = status.get("responseCount", 0)
        if status.get("isComplete"):
            break

    # Wait a moment after completion for results to settle
    time.sleep(2)

    results = session.get(f"{SLSKD_URL}/api/v0/searches/{search_id}/responses").json()
    if not isinstance(results, list):
        results = []

    print(f"  [{len(results)} peers responded]")

    # Flatten to list of (username, file) pairs
    files = []
    for response in results:
        if not isinstance(response, dict):
            continue
        username = response.get("username", "")
        for f in response.get("files", []):
            if isinstance(f, dict):
                f["_username"] = username
                files.append(f)

    # Clean up search
    session.delete(f"{SLSKD_URL}/api/v0/searches/{search_id}")
    return files


def best_file(files: list[dict]) -> dict | None:
    """Pick the smallest MP3 around 192kbps — fast to download, fine for 30s previews."""
    MAX_SIZE = 15_000_000   # 15MB cap — avoids huge files
    MIN_SIZE = 1_000_000    # 1MB floor — avoids broken files

    mp3s = [
        f for f in files
        if Path(f["filename"]).suffix.lower() == ".mp3"
        and MIN_SIZE < f.get("size", 0) < MAX_SIZE
    ]

    if not mp3s:
        # Fall back to any small audio file if no MP3 found
        mp3s = [
            f for f in files
            if Path(f["filename"]).suffix.lower() in (".ogg", ".m4a")
            and MIN_SIZE < f.get("size", 0) < MAX_SIZE
        ]

    if not mp3s:
        return None

    # Prefer bitrate closest to 192kbps, then smallest file
    def score(f: dict) -> tuple:
        br = f.get("bitRate") or 192
        return (abs(br - 192), f.get("size", 999_999_999))

    mp3s.sort(key=score)
    return mp3s[0]


def download_file(session: requests.Session, username: str, filename: str, size: int) -> bool:
    """Enqueue a download in slskd."""
    try:
        resp = session.post(
            f"{SLSKD_URL}/api/v0/transfers/downloads/{username}",
            json=[{"filename": filename, "size": size}],
        )
        print(f"  [debug] status={resp.status_code} body={resp.content[:300]}")
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"  [debug] exception: {e}")
        return False


def wait_for_download(session: requests.Session, username: str, filename: str, timeout: int = 300) -> Path | None:
    """Poll until slskd reports the download is complete, return local path."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            raw = session.get(f"{SLSKD_URL}/api/v0/transfers/downloads/{username}").json()
        except Exception:
            continue

        # slskd may return a list of dicts, a dict with nested lists, or a list of directories
        transfers = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    # flat list of transfer dicts
                    transfers.append(item)
                    # or nested: item may be a directory with a "files" list
                    for f in item.get("files", []):
                        if isinstance(f, dict):
                            transfers.append(f)
        elif isinstance(raw, dict):
            transfers = raw.get("downloads", [raw])

        for t in transfers:
            if not isinstance(t, dict):
                continue
            t_file = t.get("filename", "")
            if t_file != filename:
                continue
            state = t.get("state", "")
            print(f"  [state] {state}")
            if "Succeeded" in state:
                local = t.get("localFilename") or t.get("outputFilename")
                if local:
                    return Path(local)
            elif "Errored" in state or "Cancelled" in state:
                print(f"  [fail] transfer state: {state}")
                return None
    return None


def trim_to_mp3(src: Path, dest: Path) -> bool:
    """Trim src audio to a 30s clip and save as mp3."""
    # Try starting at CLIP_START, fall back to 0 if file is too short
    for start in (CLIP_START, 0):
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src),
             "-ss", str(start), "-t", str(CLIP_DURATION),
             "-acodec", "libmp3lame", "-q:a", "5", "-loglevel", "error",
             str(dest)],
            capture_output=True,
        )
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 10_000:
            return True
    return False


def process_record(session: requests.Session, record: dict, force: bool) -> bool:
    artist = record.get("artist", "Unknown")
    title  = record.get("title", "Unknown")
    slug   = record["slug"]
    out    = AUDIO_DIR / f"{slug}.mp3"

    if out.exists() and not force:
        print(f"  [skip] already exists")
        return True

    query = record.get("_search_override") or clean_query(artist, title)
    print(f"  Searching: {query!r}")

    files = search(session, query)
    if not files:
        print(f"  [fail] no results")
        return False

    pick = best_file(files)
    if not pick:
        print(f"  [fail] no usable audio files in results")
        return False

    remote_user = pick["_username"]
    remote_file = pick["filename"]
    ext = Path(remote_file).suffix.lower()
    print(f"  Downloading: {Path(remote_file).name} from {remote_user}")

    if not download_file(session, remote_user, remote_file, pick.get("size", 0)):
        print(f"  [fail] could not enqueue download")
        return False

    local = wait_for_download(session, remote_user, remote_file)
    if not local or not local.exists():
        print(f"  [fail] download timed out or failed")
        return False

    if not trim_to_mp3(local, out):
        print(f"  [fail] ffmpeg trim failed")
        return False

    print(f"  [ok]   {slug}.mp3")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--slug")
    args = parser.parse_args()

    username, password = load_credentials()

    print("Authenticating with slskd...")
    try:
        token = get_token(username, password)
    except Exception as e:
        print(f"ERROR: Could not connect to slskd at {SLSKD_URL}: {e}")
        print("Is slskd running? Check: curl http://localhost:5030/api/v0/application")
        sys.exit(1)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    with open(TRACKS, encoding="utf-8") as f:
        tracks = json.load(f)

    # Skip entries with no known search query
    tracks = [t for t in tracks if t.get("search")]

    if args.slug:
        tracks = [t for t in tracks if t["slug"] == args.slug]
        if not tracks:
            print(f"ERROR: slug '{args.slug}' not found in standout_tracks.json")
            sys.exit(1)

    total = len(tracks)
    ok, failed = 0, []

    for i, record in enumerate(tracks, 1):
        label = f"{record['artist']} — {record['track']}"
        print(f"[{i}/{total}] {label}")
        # Use the curated search query and pass track name as title
        record_for_download = {
            "slug": record["slug"],
            "artist": record["artist"],
            "title": record["track"],
            "_search_override": record["search"],
        }
        if process_record(session, record_for_download, args.force):
            ok += 1
        else:
            failed.append(label)

    print(f"\nDone: {ok}/{total} fetched.")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
