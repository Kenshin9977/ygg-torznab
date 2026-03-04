"""Mapping between U2P/YGG category IDs and Torznab/Newznab category IDs.

U2P IDs (used on ygg.gratis Nostr relay) are identical to old YGG subcategory IDs.
"""

# Torznab standard categories
# 2000 = Movies, 5000 = TV, 3000 = Audio, 4000 = PC, 1000 = Console
# See: https://torznab.github.io/spec-1.3-draft/revisions/1.0-Torznab-Torrent-Support.html

YGG_TO_TORZNAB: dict[int, int] = {
    # Film/Video
    2183: 2000,   # Film -> Movies
    2184: 5000,   # Serie TV -> TV
    2178: 5070,   # Animation -> TV/Anime
    2179: 5070,   # Animation Serie -> TV/Anime
    2181: 5080,   # Documentaire -> TV/Documentary
    2182: 5000,   # Emission TV -> TV
    2180: 2060,   # Concert -> Movies/Concert (custom)
    2185: 2060,   # Spectacle -> Movies/Concert (custom)
    2186: 5060,   # Sport -> TV/Sport
    2187: 2060,   # Video-clips -> Movies/Other
    # Audio
    2148: 3000,   # Musique -> Audio
    2147: 3000,   # Karaoke -> Audio
    2149: 3000,   # Samples -> Audio
    2150: 3000,   # Podcast Radio -> Audio
    # Application
    2144: 4000,   # Application -> PC
    # Jeu video
    2142: 1000,   # Jeu video -> Console
    # eBook
    2140: 7000,   # eBook -> Books
    # Emulation
    2141: 1000,   # Emulation -> Console
}

# Build reverse mapping: Torznab category -> list of YGG/U2P subcategory IDs
TORZNAB_TO_YGG: dict[int, list[int]] = {}
for _ygg_id, _tz_id in YGG_TO_TORZNAB.items():
    TORZNAB_TO_YGG.setdefault(_tz_id, []).append(_ygg_id)
TORZNAB_TO_YGG = {k: sorted(v) for k, v in TORZNAB_TO_YGG.items()}

TORZNAB_CATEGORIES: list[dict[str, str | int]] = [
    {"id": 2000, "name": "Movies"},
    {"id": 2060, "name": "Movies/Concert"},
    {"id": 3000, "name": "Audio"},
    {"id": 5000, "name": "TV"},
    {"id": 5060, "name": "TV/Sport"},
    {"id": 5070, "name": "TV/Anime"},
    {"id": 5080, "name": "TV/Documentary"},
    {"id": 1000, "name": "Console"},
    {"id": 4000, "name": "PC"},
    {"id": 7000, "name": "Books"},
]

# Map Nostr #t tag values → Torznab parent category
TAG_TO_TORZNAB: dict[str, int] = {
    "film": 2000,
    "série-tv": 5000,
    "série tv": 5000,
    "animation": 5070,
    "animé": 5070,
    "animation-série": 5070,
    "documentaire": 5080,
    "documentary": 5080,
    "émission-tv": 5000,
    "émission tv": 5000,
    "television": 5000,
    "concert": 2060,
    "spectacle": 2060,
    "sport": 5060,
    "vidéo-clips": 2060,
    "musique": 3000,
    "music": 3000,
    "application": 4000,
    "software": 4000,
    "jeu-vidéo": 1000,
    "jeu vidéo": 1000,
    "game": 1000,
    "games": 1000,
    "ebook": 7000,
    "book": 7000,
    "books": 7000,
}

# Reverse: Torznab ID -> list of #t tag values for Nostr query filtering
TORZNAB_TO_TAGS: dict[int, list[str]] = {}
for _tag, _tz_id in TAG_TO_TORZNAB.items():
    TORZNAB_TO_TAGS.setdefault(_tz_id, []).append(_tag)


def torznab_cats_to_ygg_subcats(torznab_ids: list[int]) -> list[int]:
    """Convert Torznab category IDs to U2P subcategory IDs."""
    ygg_ids: list[int] = []
    for tz_id in torznab_ids:
        ygg_ids.extend(TORZNAB_TO_YGG.get(tz_id, []))
    return sorted(set(ygg_ids))


def torznab_cats_to_tags(torznab_ids: list[int]) -> list[str]:
    """Convert Torznab category IDs to Nostr #t tag values for query filtering."""
    tags: list[str] = []
    for tz_id in torznab_ids:
        tags.extend(TORZNAB_TO_TAGS.get(tz_id, []))
    return sorted(set(tags))
