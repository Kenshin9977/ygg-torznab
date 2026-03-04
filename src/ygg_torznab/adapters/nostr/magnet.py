"""Build magnet URIs from infohash and tracker URLs."""

from urllib.parse import quote

MAIN_TRACKER = "https://tracker.yggleak.top/announce"

YGG_EXTRA_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
]


def build_magnet_uri(
    infohash: str, title: str, *, include_ygg_extra: bool = False
) -> str:
    """Build a magnet URI from an infohash and title."""
    trackers = [MAIN_TRACKER]
    if include_ygg_extra:
        trackers.extend(YGG_EXTRA_TRACKERS)

    parts = [f"magnet:?xt=urn:btih:{infohash}"]
    if title:
        parts.append(f"&dn={quote(title)}")
    for tracker in trackers:
        parts.append(f"&tr={quote(tracker)}")

    return "".join(parts)
