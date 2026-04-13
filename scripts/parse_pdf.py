#!/usr/bin/env python3
"""Parse vinyl record catalog from PDF into structured JSON.

Review catalog.json manually after running — OCR extraction may need cleanup.
The parsing heuristics below are best-effort and will likely need tuning
depending on the actual PDF layout.
"""

import json
import re
import unicodedata
from pathlib import Path

import pdfplumber

PDF_PATH = Path("/Users/darius/Downloads/records.pdf")
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"

# Common vinyl condition grades
CONDITION_PATTERN = re.compile(r"\b(M|NM|NM-|VG\+|VG|VG-|G\+|G|F|P)\b")
# Price in yen
PRICE_PATTERN = re.compile(r"[¥￥][\d,]+")
# 4-digit year
YEAR_PATTERN = re.compile(r"\b(19[5-9]\d|20[0-2]\d)\b")


def slugify(text: str, max_length: int = 60) -> str:
    """Convert text to a URL-safe slug, capped at max_length characters."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:max_length].strip("-")


def parse_record_line(line: str) -> dict | None:
    """Attempt to parse a single line/block into a record dict.

    This is a heuristic parser — adjust the logic based on the actual
    PDF structure after inspecting the first run's output.
    """
    line = line.strip()
    if not line or len(line) < 10:
        return None

    price_match = PRICE_PATTERN.search(line)
    if not price_match:
        return None  # likely not a record line

    price = price_match.group(0)
    year_match = YEAR_PATTERN.search(line)
    year = year_match.group(0) if year_match else ""
    condition_match = CONDITION_PATTERN.search(line)
    condition = condition_match.group(0) if condition_match else ""

    # Remove extracted fields to isolate artist/title/label/genre
    remainder = line
    for match in [price_match, year_match, condition_match]:
        if match:
            remainder = remainder[: match.start()] + remainder[match.end() :]
    remainder = remainder.strip(" \t-–—/|,")

    # Heuristic: split by common delimiters
    parts = re.split(r"\s*[-–—/|]\s*", remainder, maxsplit=3)
    parts = [p.strip() for p in parts if p.strip()]

    artist = parts[0] if len(parts) > 0 else "Unknown"
    title = parts[1] if len(parts) > 1 else "Unknown"
    label = parts[2] if len(parts) > 2 else ""
    genre = parts[3] if len(parts) > 3 else ""

    slug = slugify(f"{artist} {title}")
    if not slug:
        slug = slugify(artist or title or "unknown")

    return {
        "slug": slug,
        "artist": artist,
        "title": title,
        "year": year,
        "label": label,
        "genre": genre,
        "price": price,
        "condition": condition,
    }


def main() -> None:
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        print("Place your catalog PDF at that path and re-run.")
        return

    records: list[dict] = []
    seen_slugs: set[str] = set()

    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                record = parse_record_line(line)
                if record:
                    # Deduplicate slugs
                    base_slug = record["slug"]
                    counter = 1
                    while record["slug"] in seen_slugs:
                        record["slug"] = f"{base_slug}-{counter}"
                        counter += 1
                    seen_slugs.add(record["slug"])
                    records.append(record)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"Parsed {len(records)} records from {PDF_PATH.name}")
    print(f"Catalog written to {OUTPUT_PATH}")
    print()
    print("⚠  Review catalog.json manually — OCR extraction may need cleanup.")


if __name__ == "__main__":
    main()
