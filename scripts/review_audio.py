#!/usr/bin/env python3
"""Interactive audio preview review tool.

Serves a local page at http://localhost:7331 where you can listen to
each record's audio previews and mark them as OK or flagged.

Usage:
    cd /Users/darius/vinyl-shop
    python3 scripts/review_audio.py

Results are saved to data/review_results.json as you go.
"""

import json
import os
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO       = Path(__file__).resolve().parent.parent
CATALOG    = REPO / "data" / "catalog.json"
TRACKS     = REPO / "data" / "standout_tracks.json"
RECORDS    = REPO / "records"
AUDIO_DIR  = REPO / "audio"
RESULTS    = REPO / "data" / "review_results.json"
PORT       = 7331


# ── Data loading ──────────────────────────────────────────────────────────────

def load_records():
    catalog = json.load(open(CATALOG)) if CATALOG.exists() else []
    tracks  = json.load(open(TRACKS))  if TRACKS.exists()  else []

    cat_by_slug   = {r["slug"]: r for r in catalog}
    track_by_slug = {t["slug"]: t for t in tracks}

    page_slugs = sorted(
        d.name
        for d in RECORDS.iterdir()
        if d.is_dir() and (d / "index.html").exists()
    )

    records = []
    for slug in page_slugs:
        r = cat_by_slug.get(slug, {})
        t = track_by_slug.get(slug, {})

        # Prefer cleaned fields, fall back to raw, then slug
        artist = r.get("artist_clean") or r.get("artist") or slug
        title  = r.get("title_clean")  or r.get("title")  or ""
        label  = r.get("label_clean")  or r.get("label")  or ""
        genre  = r.get("genre_clean")  or r.get("genre")  or ""
        year   = r.get("year", "")

        # Collect local audio files
        flat    = AUDIO_DIR / f"{slug}.mp3"
        subdir  = AUDIO_DIR / slug
        multi   = sorted(subdir.glob("*.mp3")) if subdir.is_dir() else []

        audio_files = []
        if multi:
            audio_files = [f"/audio/{slug}/{f.name}" for f in multi]
        elif flat.exists():
            audio_files = [f"/audio/{slug}.mp3"]

        records.append({
            "slug":        slug,
            "artist":      artist,
            "title":       title,
            "label":       label,
            "genre":       genre,
            "year":        year,
            "intended_track":  t.get("track", ""),
            "search_query":    t.get("search", ""),
            "audio_files": audio_files,
        })

    return records


def load_results():
    if RESULTS.exists():
        return json.load(open(RESULTS))
    return {}


def save_results(results):
    json.dump(results, open(RESULTS, "w"), indent=2, ensure_ascii=False)


# ── HTML generation ───────────────────────────────────────────────────────────

def build_page(records, results):
    total    = len(records)
    reviewed = sum(1 for r in records if r["slug"] in results)
    ok_count = sum(1 for v in results.values() if v["status"] == "ok")
    flag_count = reviewed - ok_count

    cards = []
    for i, rec in enumerate(records):
        slug   = rec["slug"]
        status = results.get(slug, {}).get("status", "pending")
        note   = results.get(slug, {}).get("note", "")

        status_class = {
            "ok":      "status-ok",
            "flag":    "status-flag",
            "pending": "status-pending",
        }.get(status, "status-pending")

        status_label = {"ok": "✓ OK", "flag": "⚑ Flagged", "pending": "–"}.get(status, "–")

        players = ""
        for j, af in enumerate(rec["audio_files"]):
            fname = af.split("/")[-1]
            # Make filename human-readable: strip extension, replace _ with space
            label = re.sub(r"_", " ", Path(fname).stem)
            label = re.sub(r"^track[\s_]0*(\d+)", r"Track \1", label, flags=re.IGNORECASE)
            players += f"""
            <div class="track-row">
              <span class="track-label">{label}</span>
              <audio controls preload="none">
                <source src="{af}" type="audio/mpeg">
              </audio>
            </div>"""

        intended = rec["intended_track"] or "—"
        search   = rec["search_query"]   or "—"
        meta_line = f"{rec['label']} · {rec['genre']} · {rec['year']}".strip(" ·")

        cards.append(f"""
    <div class="card {status_class}" id="card-{slug}" data-slug="{slug}">
      <div class="card-header">
        <div class="card-index">{i+1}/{total}</div>
        <div class="card-status">{status_label}</div>
      </div>
      <div class="card-body">
        <div class="record-info">
          <div class="record-artist">{rec['artist']}</div>
          <div class="record-title">{rec['title']}</div>
          <div class="record-meta">{meta_line}</div>
          <div class="record-track">Intended preview: <strong>{intended}</strong></div>
          <div class="record-search">Search query: <code>{search}</code></div>
        </div>
        <div class="players">{players if players else '<em class="no-audio">No local audio found</em>'}</div>
        <div class="actions">
          <button class="btn-ok"   onclick="mark('{slug}', 'ok')">✓ OK</button>
          <button class="btn-flag" onclick="mark('{slug}', 'flag')">⚑ Flag</button>
          <textarea class="note-field" placeholder="Optional note…" onchange="saveNote('{slug}', this.value)">{note}</textarea>
        </div>
      </div>
    </div>""")

    cards_html = "\n".join(cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Audio Review — Vinyl Shop</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #111; color: #ddd; padding: 24px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 8px; color: #fff; }}
  .summary {{ margin-bottom: 24px; font-size: .9rem; color: #999; }}
  .summary span {{ color: #fff; font-weight: bold; }}
  .progress-bar {{ background: #333; border-radius: 4px; height: 6px; margin-bottom: 24px; }}
  .progress-fill {{ background: #4ade80; height: 6px; border-radius: 4px;
                    width: {int(reviewed/total*100) if total else 0}%; transition: width .3s; }}
  .filters {{ margin-bottom: 20px; display: flex; gap: 8px; }}
  .filter-btn {{ padding: 6px 14px; border: 1px solid #444; border-radius: 20px; background: #222;
                 color: #ccc; cursor: pointer; font-size: .8rem; }}
  .filter-btn.active {{ background: #444; color: #fff; border-color: #888; }}
  .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 10px;
           margin-bottom: 16px; overflow: hidden; transition: border-color .2s; }}
  .card.status-ok   {{ border-left: 4px solid #4ade80; }}
  .card.status-flag {{ border-left: 4px solid #f87171; }}
  .card.status-pending {{ border-left: 4px solid #555; }}
  .card-header {{ display: flex; justify-content: space-between; align-items: center;
                  padding: 10px 16px; background: #222; border-bottom: 1px solid #333; }}
  .card-index  {{ font-size: .75rem; color: #666; }}
  .card-status {{ font-size: .8rem; font-weight: bold; }}
  .status-ok   .card-status {{ color: #4ade80; }}
  .status-flag .card-status {{ color: #f87171; }}
  .status-pending .card-status {{ color: #666; }}
  .card-body {{ padding: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 800px) {{ .card-body {{ grid-template-columns: 1fr; }} }}
  .record-artist {{ font-size: 1rem; font-weight: 600; color: #fff; margin-bottom: 2px; }}
  .record-title  {{ font-size: .95rem; color: #aaa; margin-bottom: 6px; }}
  .record-meta   {{ font-size: .75rem; color: #666; margin-bottom: 8px; }}
  .record-track  {{ font-size: .8rem; color: #bbb; margin-bottom: 4px; }}
  .record-search {{ font-size: .75rem; color: #777; }}
  .record-search code {{ background: #2a2a2a; padding: 1px 5px; border-radius: 3px;
                          font-size: .75rem; color: #9ca3af; }}
  .players {{ display: flex; flex-direction: column; gap: 8px; }}
  .track-row {{ display: flex; flex-direction: column; gap: 4px; }}
  .track-label {{ font-size: .72rem; color: #777; text-transform: capitalize;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  audio {{ width: 100%; height: 32px; }}
  .no-audio {{ font-size: .8rem; color: #555; }}
  .actions {{ grid-column: 1 / -1; display: flex; gap: 10px; align-items: flex-start; }}
  .btn-ok, .btn-flag {{ padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer;
                         font-size: .85rem; font-weight: 600; }}
  .btn-ok   {{ background: #166534; color: #4ade80; }}
  .btn-ok:hover   {{ background: #15803d; }}
  .btn-flag {{ background: #7f1d1d; color: #f87171; }}
  .btn-flag:hover {{ background: #991b1b; }}
  .note-field {{ flex: 1; background: #222; border: 1px solid #444; border-radius: 6px;
                  color: #ccc; padding: 6px 10px; font-size: .8rem; resize: vertical;
                  min-height: 36px; }}
  .flagged-summary {{ margin-top: 32px; padding: 16px; background: #1a1a1a;
                       border: 1px solid #555; border-radius: 10px; }}
  .flagged-summary h2 {{ font-size: 1rem; margin-bottom: 12px; color: #f87171; }}
  .flagged-summary li {{ font-size: .85rem; padding: 4px 0; color: #ccc; }}
  .hidden {{ display: none !important; }}
</style>
</head>
<body>
<h1>Vinyl Shop — Audio Preview Review</h1>
<div class="summary">
  <span>{reviewed}</span>/{total} reviewed &nbsp;·&nbsp;
  <span style="color:#4ade80">{ok_count}</span> OK &nbsp;·&nbsp;
  <span style="color:#f87171">{flag_count}</span> flagged
</div>
<div class="progress-bar"><div class="progress-fill"></div></div>

<div class="filters">
  <button class="filter-btn active" onclick="filter('all', this)">All ({total})</button>
  <button class="filter-btn" onclick="filter('pending', this)">Pending</button>
  <button class="filter-btn" onclick="filter('ok', this)">OK</button>
  <button class="filter-btn" onclick="filter('flag', this)">Flagged</button>
</div>

{cards_html}

<div class="flagged-summary" id="flagged-list" style="display:none">
  <h2>Flagged records</h2>
  <ul id="flagged-ul"></ul>
</div>

<script>
async function mark(slug, status) {{
  const res = await fetch('/mark', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{slug, status}})
  }});
  if (res.ok) location.reload();
}}

async function saveNote(slug, note) {{
  await fetch('/note', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{slug, note}})
  }});
}}

function filter(type, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.card').forEach(card => {{
    if (type === 'all') {{
      card.classList.remove('hidden');
    }} else if (type === 'pending') {{
      card.classList.toggle('hidden', !card.classList.contains('status-pending'));
    }} else if (type === 'ok') {{
      card.classList.toggle('hidden', !card.classList.contains('status-ok'));
    }} else if (type === 'flag') {{
      card.classList.toggle('hidden', !card.classList.contains('status-flag'));
    }}
  }});
}}

// Build flagged summary
const flagged = document.querySelectorAll('.status-flag');
if (flagged.length > 0) {{
  document.getElementById('flagged-list').style.display = '';
  const ul = document.getElementById('flagged-ul');
  flagged.forEach(card => {{
    const li = document.createElement('li');
    const artist = card.querySelector('.record-artist').textContent;
    const title  = card.querySelector('.record-title').textContent;
    const note   = card.querySelector('.note-field').value;
    li.textContent = artist + ' — ' + title + (note ? ' · ' + note : '');
    ul.appendChild(li);
  }});
}}
</script>
</body>
</html>"""


# ── HTTP server ───────────────────────────────────────────────────────────────

records_cache = None
results_cache = None
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silence request logs

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, path: Path):
        if not path.exists():
            self.send_response(404); self.end_headers(); return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", len(data))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        global records_cache, results_cache
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        if path == "/" or path == "/index.html":
            with lock:
                html = build_page(records_cache, results_cache)
            self.send_html(html)

        elif path.startswith("/audio/"):
            rel  = path[len("/audio/"):]
            file = AUDIO_DIR / urllib.parse.unquote(rel)
            self.serve_file(file)

        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        global results_cache
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length))

        with lock:
            if parsed.path == "/mark":
                slug   = body["slug"]
                status = body["status"]
                if slug not in results_cache:
                    results_cache[slug] = {}
                results_cache[slug]["status"] = status
                save_results(results_cache)
                self.send_json(200, {"ok": True})

            elif parsed.path == "/note":
                slug = body["slug"]
                note = body.get("note", "")
                if slug not in results_cache:
                    results_cache[slug] = {}
                results_cache[slug]["note"] = note
                save_results(results_cache)
                self.send_json(200, {"ok": True})

            else:
                self.send_response(404); self.end_headers()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global records_cache, results_cache
    records_cache = load_records()
    results_cache = load_results()

    total    = len(records_cache)
    reviewed = sum(1 for r in records_cache if r["slug"] in results_cache)
    print(f"Vinyl Shop Audio Review")
    print(f"  {total} records  |  {reviewed} already reviewed")
    print(f"  Open: http://localhost:{PORT}")
    print(f"  Ctrl-C to stop. Results auto-save to data/review_results.json")
    print()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
