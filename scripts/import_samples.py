#!/usr/bin/env python3
"""
Copy sample MP3s from the Discogs snippet folders into audio/<slug>/
and update each record's index.html with a multi-track player.

Usage:
    python import_samples.py
"""

import re
import shutil
from pathlib import Path

SAMPLES_DIR = Path("/Users/darius/Downloads/Sample Packs/Music Samples")
REPO        = Path(__file__).resolve().parent.parent
AUDIO_DIR   = REPO / "audio"
RECORDS_DIR = REPO / "records"

# Map snippet folder name → record slug
FOLDER_TO_SLUG = {
    "snippets_a_caribbean_taste_of_technology_07-12-2023_1303":          "arilp-025-ariwa-sounds-mad-professor-a-caribbean-taste-of-re",
    "snippets_aoi_bionix_03-12-2023_1132":                               "rmm-0561-9d7778-chrysalis-de-la-soul-aoi-bionix-hip-hop-eu2l",
    "snippets_at_last_03-12-2023_1116":                                   "odiliv-002lp-odion-livingstone-grotto-at-last-funk-uklp-odio",
    "snippets_change_the_world_03-12-2023_1116":                          "lacr-031-la-club-resource-delroy-edwards-change-the-world-ho",
    "snippets_discovery_1975-1976_03-12-2023_1122":                       "asa103-as-shams-black-disco-discovery",
    "snippets_donuts_smile_cover_03-12-2023_1137":                        "sth-2126lp-stones-throw-j-dilla-donuts-smile-cover-us2lp-fin",
    "snippets_dub_me_crazy_pt_3_the_african_connection_03-12-2023_1118":  "arilp-005-ariwa-sounds-mad-professor-dub-me-crazy-pt-3-the-r",
    "snippets_dub_me_crazy_pt_4_escape_to_the_asylum_of_dub_06-12-2023_2024": "arilp-011-ariwa-sounds-mad-professor-dub-me-crazy-pt-4-escap",
    "snippets_fair_chance_floating_points_remix_03-12-2023_1116":         "bf-105-brainfeeder-thundercat-fair-chance-floating-points-ho",
    "snippets_in_the_company_of_others_ep_03-12-2023_1116":              "mm-39-mahogani-music-randolph-in-the-company-of-others-ep-ho",
    "snippets_instrumentals_jid019_-_black_vinyl_03-12-2023_1126":       "jid-019lp-jazz-is-dead-adrian-younge-instrumentals-jid019-bl",
    "snippets_mind_twister_03-12-2023_1117":                             "odiliv-003lp-odion-livingstone-apples-mind-twister-funk-uklp",
    "snippets_mm.food_colored_vinyl_03-12-2023_1136":                    "rse-0084-1-mf-doom-mmfood-colored-vinyl-us2lp",
    "snippets_one_in_a_million_-_col_vinyl_03-12-2023_1124":             "ere-712-empire-blackground-aaliyah-one-in-a-million",
    "snippets_perceptions_03-12-2023_1126":                              "nbn011-nbn-records-jamma-dee-perceptions-hip-hop-eu2lp-nothi",
    "snippets_perceptions_03-12-2023_1132":                              "nbn011-nbn-records-jamma-dee-perceptions-hip-hop-eu2lp-nothi",
    "snippets_phil_ranelin_wendell_harrison_jid016_-_black_vinyl_03-12-2023_1125": "jid-016lp-jazz-is-dead-phil-ranelin-wendell-harrison",
    "snippets_spaceships_on_the_blade_03-12-2023_1133":                  "ere-863-empire-larry-june-spaceships-on-the-blade-uk2lp-unkn",
    "snippets_stay_around_03-12-2023_1135":                              "joyce-wrice-stay-around-uslp-unknown",
    "snippets_tana_talk_4_03-12-2023_1124":                              "ere-811-griselda-records-empire-benny-the-butcher-tana-talk",
    "snippets_the_angel_you_dont_know_03-12-2023_1132":                  "nts-tadyk-nts-amaarae-the-angel-you-dont-know-hip-hop-uklp-1",
    "snippets_the_further_adventures_of_lord_quas_03-12-2023_1137":      "sth-2110-stones-throw-quasimoto-us2lp-unknown",
    "snippets_the_moon_dance_03-12-2023_1132":                           "apnea-104-apnea-hieroglyphic-being-the-moon-dance-eu2lp-unkn",
    "snippets_the_moon_dance_03-12-2023_1133":                           "apnea-104-apnea-hieroglyphic-being-the-moon-dance-eu2lp-unkn",
    "snippets_vibes_2_part_2_03-12-2023_1118":                           "rhm-0102-rush-hour-rick-wilhite-vibes-2-part-2-house-eu2lp-2",
    "snippets_we_buy_diabetic_test_strips_03-12-2023_1135":              "fat-possum-armand-hammer-us2lp-unknown",
    "snippets_wont_he_do_it_03-12-2023_1125":                            "ere-956-drumwork-music-group-llc-conway-the-machine-wont-he",
}


def friendly_name(filename: str) -> str:
    """Turn a filename like '1_jamma_dee_up_n_down_clip.mp3' into 'Up N Down'."""
    name = Path(filename).stem
    # Strip leading track number
    name = re.sub(r"^[a-z]?\d+_", "", name)
    # Strip known artist prefixes (e.g. 'jamma_dee_')
    name = re.sub(r"^[a-z]+_[a-z]+_", "", name)
    # Strip trailing _clip, _v1, _v2
    name = re.sub(r"_(clip|v\d+)$", "", name)
    # Underscores → spaces, title case
    name = name.replace("_", " ").replace("amp ", "& ").strip()
    return name.title()


def build_track_html(slug: str, mp3_files: list[Path]) -> str:
    """Generate .track-item HTML blocks for a list of MP3 files."""
    items = []
    for mp3 in sorted(mp3_files):
        rel_path = f"../../audio/{slug}/{mp3.name}"
        label = friendly_name(mp3.name)
        items.append(f"""\
        <div class="track-item">
            <span class="track-name">{label}</span>
            <div class="progress-bar"><div class="progress-fill"></div></div>
            <button class="play-button track-btn">&#9654; 试听</button>
            <audio preload="none"><source src="{rel_path}" type="audio/mpeg"></audio>
        </div>""")
    return "\n".join(items)


def update_html(html_path: Path, slug: str, mp3_files: list[Path]) -> None:
    """Replace the player-section in index.html with a multi-track version."""
    html = html_path.read_text(encoding="utf-8")

    track_items = build_track_html(slug, mp3_files)
    new_section = f"""\
        <div class="player-section">
            <div class="track-list">
{track_items}
            </div>
        </div>"""

    # Replace everything between <div class="player-section"> and its closing </div>
    pattern = re.compile(
        r'<div class="player-section">.*?</div>\s*</div>',
        re.DOTALL,
    )
    replacement = new_section + "\n"

    if pattern.search(html):
        new_html = pattern.sub(replacement, html, count=1)
    else:
        # Fallback: insert before buy-section
        new_html = html.replace(
            '<div class="buy-section">',
            new_section + '\n\n        <div class="buy-section">',
            1,
        )

    # Ensure initMultiPlayer is used
    new_html = new_html.replace("initPlayer();", "initMultiPlayer();")

    html_path.write_text(new_html, encoding="utf-8")


def main() -> None:
    # Collect MP3s per slug (deduplicate across duplicate folders)
    slug_to_files: dict[str, dict[str, Path]] = {}

    for folder_name, slug in FOLDER_TO_SLUG.items():
        folder = SAMPLES_DIR / folder_name
        if not folder.exists():
            print(f"  [skip] folder not found: {folder_name}")
            continue
        mp3s = [f for f in folder.iterdir() if f.suffix.lower() == ".mp3"]
        if slug not in slug_to_files:
            slug_to_files[slug] = {}
        for mp3 in mp3s:
            slug_to_files[slug][mp3.name] = mp3  # deduplicates by filename

    for slug, file_map in slug_to_files.items():
        dest_dir = AUDIO_DIR / slug
        dest_dir.mkdir(parents=True, exist_ok=True)

        copied = []
        for fname, src in sorted(file_map.items()):
            dest = dest_dir / fname
            shutil.copy2(src, dest)
            copied.append(dest)

        print(f"[{slug}] {len(copied)} tracks copied")

        html_path = RECORDS_DIR / slug / "index.html"
        if not html_path.exists():
            print(f"  [warn] no index.html found, skipping HTML update")
            continue

        update_html(html_path, slug, copied)
        print(f"  [ok] index.html updated")

    print(f"\nDone. {len(slug_to_files)} record pages updated.")
    print("Note: snippets_promises was skipped — no matching record in catalog.")


if __name__ == "__main__":
    main()
