#!/usr/bin/env python3
"""Generate QR code PNGs for each record in the catalog."""

import argparse
import json
from pathlib import Path

import qrcode

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"
QR_DIR = Path(__file__).resolve().parent.parent / "qr"

DEFAULT_BASE_URL = "https://USERNAME.github.io/vinyl-shop"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate QR codes for vinyl records")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URL for the site (e.g. https://myuser.github.io/vinyl-shop)",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    if not CATALOG_PATH.exists():
        print(f"ERROR: {CATALOG_PATH} not found. Run parse_pdf.py first.")
        return

    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)

    QR_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for record in catalog:
        slug = record["slug"]
        url = f"{base_url}/records/{slug}/"

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img.save(QR_DIR / f"{slug}.png")
        count += 1

    print(f"Generated {count} QR codes in {QR_DIR}")


if __name__ == "__main__":
    main()
