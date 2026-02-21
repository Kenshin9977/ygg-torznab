"""Parse YGG search results HTML into TorrentResult objects."""

import logging
import re
from datetime import UTC, datetime

from selectolax.parser import HTMLParser

from ygg_torznab.domain.models import TorrentResult

logger = logging.getLogger(__name__)

_SIZE_UNITS: dict[str, int] = {
    "o": 1,
    "ko": 1024,
    "mo": 1024**2,
    "go": 1024**3,
    "to": 1024**4,
}

_SIZE_RE = re.compile(r"([\d.,]+)\s*(To|Go|Mo|Ko|o)", re.IGNORECASE)
_ID_RE = re.compile(r"/(\d+)-[^/]*$")


def parse_size(size_str: str) -> int:
    """Parse French size string like '86.12Go' to bytes."""
    match = _SIZE_RE.search(size_str)
    if not match:
        return 0
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    return int(value * _SIZE_UNITS.get(unit, 1))


def extract_torrent_id(url: str) -> int:
    """Extract torrent ID from a YGG detail URL."""
    match = _ID_RE.search(url)
    if not match:
        raise ValueError(f"Cannot extract torrent ID from URL: {url}")
    return int(match.group(1))


def parse_total_results(html: HTMLParser) -> int:
    """Extract total result count from the page header."""
    node = html.css_first("section.content h2 font")
    if node is None:
        return 0
    text = node.text(strip=True)
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else 0


def parse_search_results(html_content: str, domain: str) -> tuple[list[TorrentResult], int]:
    """Parse YGG search HTML and return (results, total_count)."""
    html = HTMLParser(html_content)
    total = parse_total_results(html)

    results: list[TorrentResult] = []
    rows = html.css("div.table-responsive.results table.table tbody tr")

    for row in rows:
        cells = row.css("td")
        if len(cells) < 9:
            continue

        try:
            result = _parse_row(cells, domain)
            results.append(result)
        except Exception:
            logger.debug("Failed to parse row", exc_info=True)
            continue

    return results, total


def _parse_row(cells: list, domain: str) -> TorrentResult:  # type: ignore[type-arg]
    cat_node = cells[0].css_first("div.hidden")
    category_id = int(cat_node.text(strip=True)) if cat_node else 0

    link_node = cells[1].css_first("a")
    title = link_node.text(strip=True) if link_node else ""
    detail_url = link_node.attributes.get("href", "") if link_node else ""
    torrent_id = extract_torrent_id(detail_url)

    date_node = cells[4].css_first("div.hidden")
    timestamp = int(date_node.text(strip=True)) if date_node else 0
    publish_date = datetime.fromtimestamp(timestamp, tz=UTC)

    size_bytes = parse_size(cells[5].text(strip=True))

    grabs = _safe_int(cells[6].text(strip=True))
    seeders = _safe_int(cells[7].text(strip=True))
    leechers = _safe_int(cells[8].text(strip=True))

    comments_text = cells[3].text(strip=True)
    comments = _safe_int(re.sub(r"\D", "", comments_text))

    download_url = f"https://{domain}/engine/download_torrent?id={torrent_id}"

    return TorrentResult(
        torrent_id=torrent_id,
        title=title,
        detail_url=detail_url,
        category_id=category_id,
        size_bytes=size_bytes,
        seeders=seeders,
        leechers=leechers,
        grabs=grabs,
        publish_date=publish_date,
        comments=comments,
        download_url=download_url,
    )


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
