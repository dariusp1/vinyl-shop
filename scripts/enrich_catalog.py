#!/usr/bin/env python3
"""
Parse and translate catalog.json using Claude API.

For each record, extracts clean label/artist/title/description from the
messy raw artist field, then translates the description to Chinese.
Writes enriched fields back into catalog.json.

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python enrich_catalog.py
"""

import json
import os
import time
from pathlib import Path

import anthropic

REPO         = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO / "data" / "catalog.json"
ENV_PATH     = REPO / ".env"

# Load from .env if not already in environment
if not os.environ.get("ANTHROPIC_API_KEY") and ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def enrich_record(raw: str, price: str) -> dict:
    """Call Claude to parse and translate a raw catalog entry."""
    prompt = f"""This is a raw entry from a vinyl record shop catalog. The text was OCR'd from a PDF and contains everything jumbled together: catalog number, label name, artist, album title, format info, and a description blurb.

Raw text: {raw!r}
Price: {price}

Extract the following and return ONLY valid JSON (no markdown, no explanation):
{{
  "label": "label name only",
  "artist": "artist name only",
  "title": "album title only",
  "genre": "genre if present, else empty string",
  "format": "format/pressing info e.g. UK12'', US2LP, etc.",
  "description_cn": "the description blurb translated to natural, concise Chinese (1-3 sentences). If no description, write a short one based on the artist/album. Keep it factual and appealing to music fans."
}}

Rules:
- artist and title should be in their original language (English/Japanese/etc)
- description_cn must be in Chinese
- If something is unknown, use empty string not "Unknown"
"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def main() -> None:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)

    total = len(catalog)
    for i, record in enumerate(catalog, 1):
        # Skip if already enriched
        if record.get("description_cn") and record.get("artist_clean"):
            print(f"[{i}/{total}] [skip] {record['slug'][:50]}")
            continue

        raw = record.get("artist", "")
        price = record.get("price", "")
        print(f"[{i}/{total}] {record['slug'][:50]}")

        try:
            enriched = enrich_record(raw, price)
            record["artist_clean"]   = enriched.get("artist", "")
            record["title_clean"]    = enriched.get("title", "")
            record["label_clean"]    = enriched.get("label", "")
            record["genre_clean"]    = enriched.get("genre", "")
            record["format_clean"]   = enriched.get("format", "")
            record["description_cn"] = enriched.get("description_cn", "")
            print(f"  {record['artist_clean']} — {record['title_clean']}")
            print(f"  {record['description_cn'][:60]}...")
        except Exception as e:
            print(f"  [error] {e}")

        # Save after each record so progress isn't lost on failure
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)

        time.sleep(0.3)  # be gentle to API

    print(f"\nDone. Catalog saved to {CATALOG_PATH}")


if __name__ == "__main__":
    main()
