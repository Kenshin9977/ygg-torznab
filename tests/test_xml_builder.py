import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from ygg_torznab.adapters.torznab.xml_builder import (
    build_caps_xml,
    build_error_xml,
    build_search_xml,
)
from ygg_torznab.domain.models import SearchResponse, TorrentResult


def test_build_caps_xml() -> None:
    xml_str = build_caps_xml()
    root = ET.fromstring(xml_str)

    assert root.tag == "caps"
    assert root.find("server") is not None
    assert root.find("searching") is not None

    categories = root.findall("categories/category")
    assert len(categories) > 0


def test_build_search_xml() -> None:
    result = TorrentResult(
        torrent_id=271361,
        title="Inception.2010.BluRay",
        detail_url="https://www.yggtorrent.org/torrent/film/271361-inception",
        category_id=2183,
        size_bytes=1024 * 1024 * 700,
        seeders=10,
        leechers=2,
        grabs=500,
        publish_date=datetime(2024, 1, 1, tzinfo=UTC),
        comments=3,
        download_url="https://www.yggtorrent.org/engine/download_torrent?id=271361",
    )
    response = SearchResponse(results=[result], total=1, offset=0)

    xml_str = build_search_xml(response, "http://localhost:8715/api")
    root = ET.fromstring(xml_str)

    assert root.tag == "rss"
    items = root.findall("channel/item")
    assert len(items) == 1
    assert items[0].findtext("title") == "Inception.2010.BluRay"
    assert items[0].findtext("guid") == "271361"


def test_build_error_xml() -> None:
    xml_str = build_error_xml(100, "Incorrect API key")
    root = ET.fromstring(xml_str)

    assert root.tag == "error"
    assert root.get("code") == "100"
    assert root.get("description") == "Incorrect API key"
