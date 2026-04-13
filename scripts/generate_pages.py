#!/usr/bin/env python3
"""Generate individual record pages from catalog.json."""

import json
from html import escape
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"
RECORDS_DIR = Path(__file__).resolve().parent.parent / "records"

PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{artist} — {title} | 黑胶唱片店</title>
    <link rel="stylesheet" href="../../assets/style.css">
</head>
<body>
    <article class="record-page">
        <a href="../../" class="back-link">&larr; 返回目录</a>

        <div class="record-cover">
            <img
                src="../../assets/covers/{slug}.jpg"
                alt="{artist} — {title}"
                onerror="this.onerror=null;this.src='../../assets/covers/placeholder.svg';"
            >
        </div>

        <div class="record-meta">
            <h1 class="record-artist">{artist}</h1>
            <h2 class="record-title">{title}</h2>
            <dl class="meta-list">
                <dt>年份</dt><dd>{year}</dd>
                <dt>厂牌</dt><dd>{label}</dd>
                <dt>风格</dt><dd>{genre}</dd>
                <dt>品相</dt><dd><span class="badge">{condition}</span></dd>
                <dt>价格</dt><dd class="price">{price}</dd>
            </dl>
            {description_block}
        </div>

        <div class="player-section">
            <div id="progress-bar" class="progress-bar">
                <div id="progress-fill" class="progress-fill"></div>
            </div>
            <button id="play-btn" class="play-button">&#9654; 试听 30秒</button>
            <audio id="audio" preload="none">
                <source src="../../audio/{slug}.mp3" type="audio/mpeg">
            </audio>
        </div>

        <div class="buy-section">
            <button class="buy-button">立即购买 / 联系我们</button>
            <div class="contact-qr">
                <p>扫码添加微信咨询</p>
                <img src="../../qr/shop-wechat.png" alt="微信二维码"
                     onerror="this.parentElement.innerHTML='<p>微信号: VINYL_SHOP</p>';">
            </div>
        </div>
    </article>

    <script src="../../assets/player.js"></script>
    <script>initPlayer();</script>
</body>
</html>
"""


def main() -> None:
    if not CATALOG_PATH.exists():
        print(f"ERROR: {CATALOG_PATH} not found. Run parse_pdf.py first.")
        return

    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)

    count = 0
    for record in catalog:
        slug = record["slug"]
        page_dir = RECORDS_DIR / slug
        page_dir.mkdir(parents=True, exist_ok=True)

        # Use enriched fields if available, fall back to raw
        artist = record.get("artist_clean") or record.get("artist", "")
        title  = record.get("title_clean")  or record.get("title", "")
        label  = record.get("label_clean")  or record.get("label", "")
        genre  = record.get("genre_clean")  or record.get("genre", "")

        desc_cn = record.get("description_cn", "").strip()
        description_block = (
            f'<p class="record-description">{escape(desc_cn)}</p>'
            if desc_cn else ""
        )

        html = PAGE_TEMPLATE.format(
            slug=escape(slug),
            artist=escape(artist),
            title=escape(title),
            year=escape(record.get("year", "")),
            label=escape(label),
            genre=escape(genre),
            condition=escape(record.get("condition", "")),
            price=escape(record.get("price", "")),
            description_block=description_block,
        )

        with open(page_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(html)
        count += 1

    print(f"Generated {count} record pages in {RECORDS_DIR}")


if __name__ == "__main__":
    main()
