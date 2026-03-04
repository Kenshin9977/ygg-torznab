"""Parse NIP-35 Kind 2003 Nostr events into TorrentResult objects."""

import logging
from datetime import UTC, datetime
from typing import Any

from ygg_torznab.adapters.nostr.magnet import build_magnet_uri
from ygg_torznab.domain.models import TorrentResult

logger = logging.getLogger(__name__)


def parse_event(event: dict[str, Any]) -> TorrentResult | None:
    """Parse a single NIP-35 Kind 2003 event into a TorrentResult.

    Returns None if the event is missing required fields (title or infohash).
    """
    tags = event.get("tags", [])
    tag_map = _build_tag_map(tags)

    title = tag_map.get("title")
    infohash = tag_map.get("x")

    if not title or not infohash:
        return None

    size_str = tag_map.get("size")
    published_at_str = tag_map.get("published_at")

    size_bytes = _safe_int(size_str)
    published_at = (
        datetime.fromtimestamp(int(published_at_str), tz=UTC)
        if published_at_str and published_at_str.isdigit()
        else datetime.fromtimestamp(event.get("created_at", 0), tz=UTC)
    )

    labels = _extract_labels(tags)
    category_id = labels.get("u2p.cat", 0)
    seeders = labels.get("u2p.seed", 0)
    leechers = labels.get("u2p.leech", 0)
    grabs = labels.get("u2p.completed", 0)

    has_ygg = any(len(tag) >= 1 and tag[0] == "ygg" for tag in tags)

    magnet_uri = build_magnet_uri(infohash, title, include_ygg_extra=has_ygg)

    return TorrentResult(
        infohash=infohash,
        title=title,
        category_id=category_id,
        size_bytes=size_bytes,
        seeders=seeders,
        leechers=leechers,
        grabs=grabs,
        publish_date=published_at,
        magnet_uri=magnet_uri,
        has_ygg_tag=has_ygg,
    )


def _build_tag_map(tags: list[list[str]]) -> dict[str, str]:
    """Build a dict of single-value tags (first occurrence wins)."""
    result: dict[str, str] = {}
    for tag in tags:
        if len(tag) >= 2 and tag[0] not in result:
            result[tag[0]] = tag[1]
    return result


def _extract_labels(tags: list[list[str]]) -> dict[str, int]:
    """Extract u2p.xxx labels from ["l", "u2p.xxx:value"] tags."""
    result: dict[str, int] = {}
    for tag in tags:
        if len(tag) >= 2 and tag[0] == "l" and tag[1].startswith("u2p."):
            key, _, value = tag[1].partition(":")
            result[key] = _safe_int(value)
    return result


def _safe_int(value: str | None) -> int:
    """Parse an integer from a string, returning 0 on failure."""
    try:
        return int(value) if value else 0
    except (ValueError, TypeError):
        return 0
