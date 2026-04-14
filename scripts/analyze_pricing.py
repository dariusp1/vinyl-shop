#!/usr/bin/env python3
"""
Compare catalog prices against Discogs lowest marketplace price.

Usage:
    python3 scripts/analyze_pricing.py

Rate limit: Discogs unauthenticated = 25 req/min.
Script uses 3s delay between records (2 requests each) = ~10 req/min.
"""

import json, time, urllib.parse, urllib.request
from pathlib import Path

REPO    = Path(__file__).resolve().parent.parent
CATALOG = REPO / "data" / "catalog.json"
UA      = "VinylShopScript/1.0"
CNY_PER_USD = 7.25   # update if needed

def discogs_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except Exception:
        return None

def find_release(artist, title, slug):
    catno_guess = slug.split("-")[0].upper()
    query = urllib.parse.urlencode({
        "q": f"{artist} {title}",
        "type": "release", "per_page": "5"
    })
    data = discogs_get(f"https://api.discogs.com/database/search?{query}")
    if not data or not data.get("results"):
        return None, None, None
    results = data["results"]
    best = None
    for res in results:
        if catno_guess in res.get("catno", "").upper().replace("-","").replace(" ",""):
            best = res
            break
    if not best:
        best = results[0]
    return best["id"], best.get("title",""), best.get("catno","")

def get_stats(release_id):
    stats = discogs_get(f"https://api.discogs.com/marketplace/stats/{release_id}")
    if not stats:
        return None, None
    num = stats.get("num_for_sale", 0)
    lp  = stats.get("lowest_price")
    low_usd = lp["value"] if lp and lp.get("value") else None
    return num, low_usd

def main():
    catalog = json.load(open(CATALOG))
    CNY = CNY_PER_USD

    rows = []
    for r in catalog:
        artist = r.get("artist_clean") or r["artist"]
        title  = r.get("title_clean")  or r["title"]
        slug   = r["slug"]
        fmt    = r.get("format_clean", "")
        our_str = r.get("price", "")
        our = int(our_str[1:]) if our_str.startswith("¥") else None

        release_id, disc_title, catno = find_release(artist, title, slug)
        time.sleep(1.5)

        num_for_sale = None
        low_cny = None
        low_usd = None

        if release_id:
            num_for_sale, low_usd = get_stats(release_id)
            if low_usd:
                low_cny = round(low_usd * CNY)
        time.sleep(1.5)

        rows.append({
            "artist": artist, "title": title, "format": fmt,
            "our": our, "low_usd": low_usd, "low_cny": low_cny,
            "num_for_sale": num_for_sale,
            "disc_title": disc_title, "catno": catno,
        })

        diff = ""
        if our and low_cny:
            pct = (our - low_cny) / low_cny * 100
            diff = f"  {'+' if pct >= 0 else ''}{pct:.0f}%"
        print(f"  {'✓' if low_cny else '✗'}  ¥{our:>4}  discogs=¥{low_cny or '?':>5}  {artist[:28]} — {title[:28]}{diff}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'═'*72}")
    matched = [x for x in rows if x["low_cny"]]
    no_data = [x for x in rows if not x["low_cny"]]

    print(f"Matched: {len(matched)}/{len(rows)} records have Discogs market data\n")

    if matched:
        print("── Pricing vs Discogs lowest listed price (CNY @ {:.2f}) ──".format(CNY))
        print(f"  {'Artist':<28}  {'Title':<28}  {'Ours':>5}  {'Disc.':>5}  {'Diff':>6}  {'#listed':>7}")
        print(f"  {'-'*28}  {'-'*28}  {'-'*5}  {'-'*5}  {'-'*6}  {'-'*7}")
        for x in sorted(matched, key=lambda x: (x["our"] or 0) - (x["low_cny"] or 0)):
            our, low = x["our"], x["low_cny"]
            diff = our - low
            pct  = diff / low * 100
            tag  = "UNDER" if pct < -10 else ("OVER" if pct > 30 else "ok")
            print(f"  {x['artist']:<28}  {x['title']:<28}  ¥{our:>4}  ¥{low:>4}  {pct:>+5.0f}%  {x['num_for_sale']:>7}  {tag}")

        print()
        diffs = [(x["our"] - x["low_cny"]) / x["low_cny"] * 100 for x in matched]
        print(f"  Average delta vs Discogs low:  {sum(diffs)/len(diffs):+.0f}%")
        under = [x for x in matched if (x["our"] - x["low_cny"]) / x["low_cny"] * 100 < -10]
        over  = [x for x in matched if (x["our"] - x["low_cny"]) / x["low_cny"] * 100 > 30]
        if under:
            print(f"\n  Priced UNDER market (>10% below Discogs low):")
            for x in under:
                print(f"    ¥{x['our']} vs ¥{x['low_cny']} Discogs — {x['artist']} — {x['title']}")
        if over:
            print(f"\n  Priced OVER market (>30% above Discogs low):")
            for x in over:
                print(f"    ¥{x['our']} vs ¥{x['low_cny']} Discogs — {x['artist']} — {x['title']}")

    if no_data:
        print(f"\n── No Discogs market data ({len(no_data)} records) ──")
        for x in no_data:
            print(f"  ¥{x['our']:>4}  {x['artist']} — {x['title']}")

if __name__ == "__main__":
    main()
