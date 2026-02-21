"""Build Torznab-compatible XML responses."""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import format_datetime

from ygg_torznab.adapters.ygg.categories import TORZNAB_CATEGORIES, YGG_TO_TORZNAB
from ygg_torznab.domain.models import SearchResponse

TORZNAB_NS = "http://torznab.com/schemas/2015/feed"


def build_caps_xml(api_url: str) -> str:
    """Build the /api?t=caps XML response."""
    root = ET.Element("caps")

    server = ET.SubElement(root, "server", title="ygg-torznab", version="0.1.0")
    server.set("strapline", "YGG Torznab proxy")

    limits = ET.SubElement(root, "limits", default="50", max="50")
    _ = limits  # used via SubElement

    searching = ET.SubElement(root, "searching")
    ET.SubElement(searching, "search", available="yes", supportedParams="q")
    ET.SubElement(searching, "tv-search", available="yes", supportedParams="q,season,ep")
    ET.SubElement(searching, "movie-search", available="yes", supportedParams="q,imdbid")

    categories = ET.SubElement(root, "categories")
    for cat in TORZNAB_CATEGORIES:
        ET.SubElement(
            categories,
            "category",
            id=str(cat["id"]),
            name=str(cat["name"]),
        )

    return _to_xml_string(root)


def build_search_xml(response: SearchResponse, api_url: str) -> str:
    """Build a Torznab search results XML response."""
    ET.register_namespace("torznab", TORZNAB_NS)
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    rss = ET.Element("rss", version="2.0")

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "ygg-torznab"
    ET.SubElement(channel, "description").text = "YGG Torznab proxy"

    atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    response_el = ET.SubElement(channel, f"{{{TORZNAB_NS}}}response")
    response_el.set("offset", str(response.offset))
    response_el.set("total", str(response.total))

    for torrent in response.results:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = torrent.title
        ET.SubElement(item, "guid").text = str(torrent.torrent_id)
        ET.SubElement(item, "link").text = torrent.detail_url
        ET.SubElement(item, "pubDate").text = _format_rfc822(torrent.publish_date)
        ET.SubElement(item, "size").text = str(torrent.size_bytes)

        enclosure = ET.SubElement(item, "enclosure")
        download_via_proxy = f"{api_url}?t=download&id={torrent.torrent_id}"
        enclosure.set("url", download_via_proxy)
        enclosure.set("length", str(torrent.size_bytes))
        enclosure.set("type", "application/x-bittorrent")

        torznab_cat = YGG_TO_TORZNAB.get(torrent.category_id, 8000)
        _add_attr(item, "category", str(torznab_cat))
        _add_attr(item, "size", str(torrent.size_bytes))
        _add_attr(item, "seeders", str(torrent.seeders))
        _add_attr(item, "peers", str(torrent.seeders + torrent.leechers))
        _add_attr(item, "grabs", str(torrent.grabs))
        _add_attr(item, "downloadvolumefactor", "1")
        _add_attr(item, "uploadvolumefactor", "1")

    return _to_xml_string(rss)


def build_error_xml(code: int, description: str) -> str:
    """Build a Torznab error response."""
    root = ET.Element("error", code=str(code), description=description)
    return _to_xml_string(root)


def _add_attr(parent: ET.Element, name: str, value: str) -> None:
    attr = ET.SubElement(parent, f"{{{TORZNAB_NS}}}attr")
    attr.set("name", name)
    attr.set("value", value)


def _format_rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return format_datetime(dt, usegmt=True)


def _to_xml_string(root: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
