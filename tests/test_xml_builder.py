import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from ygg_torznab.adapters.torznab.xml_builder import (
    TORZNAB_NS,
    build_caps_xml,
    build_error_xml,
    build_search_xml,
)
from ygg_torznab.domain.models import SearchResponse, TorrentResult


def _make_result() -> TorrentResult:
    return TorrentResult(
        infohash="a" * 40,
        title="Inception.2010.BluRay",
        category_id=2183,
        size_bytes=1024 * 1024 * 700,
        seeders=10,
        leechers=2,
        grabs=500,
        publish_date=datetime(2024, 1, 1, tzinfo=UTC),
        magnet_uri="magnet:?xt=urn:btih:" + "a" * 40,
    )


def test_build_caps_xml() -> None:
    xml_str = build_caps_xml()
    root = ET.fromstring(xml_str)

    assert root.tag == "caps"
    assert root.find("server") is not None
    assert root.find("searching") is not None

    categories = root.findall("categories/category")
    assert len(categories) > 0


def test_build_search_xml() -> None:
    result = _make_result()
    response = SearchResponse(results=[result], total=1, offset=0)

    xml_str = build_search_xml(response, "http://localhost:8715/api")
    root = ET.fromstring(xml_str)

    assert root.tag == "rss"
    items = root.findall("channel/item")
    assert len(items) == 1
    assert items[0].findtext("title") == "Inception.2010.BluRay"
    assert items[0].findtext("guid") == "a" * 40


def test_build_search_xml_has_magneturl_attr() -> None:
    result = _make_result()
    response = SearchResponse(results=[result], total=1, offset=0)

    xml_str = build_search_xml(response, "http://localhost:8715/api")
    root = ET.fromstring(xml_str)

    item = root.find("channel/item")
    assert item is not None
    attrs = {el.get("name"): el.get("value") for el in item.findall(f"{{{TORZNAB_NS}}}attr")}
    assert "magneturl" in attrs
    assert attrs["magneturl"].startswith("magnet:?")


def test_build_search_xml_has_infohash_attr() -> None:
    result = _make_result()
    response = SearchResponse(results=[result], total=1, offset=0)

    xml_str = build_search_xml(response, "http://localhost:8715/api")
    root = ET.fromstring(xml_str)

    item = root.find("channel/item")
    assert item is not None
    attrs = {el.get("name"): el.get("value") for el in item.findall(f"{{{TORZNAB_NS}}}attr")}
    assert attrs["infohash"] == "a" * 40


def test_build_search_xml_enclosure_is_magnet() -> None:
    result = _make_result()
    response = SearchResponse(results=[result], total=1, offset=0)

    xml_str = build_search_xml(response, "http://localhost:8715/api")
    root = ET.fromstring(xml_str)

    item = root.find("channel/item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.get("url", "").startswith("magnet:?")


def test_build_search_xml_no_link_element() -> None:
    result = _make_result()
    response = SearchResponse(results=[result], total=1, offset=0)

    xml_str = build_search_xml(response, "http://localhost:8715/api")
    root = ET.fromstring(xml_str)

    item = root.find("channel/item")
    assert item is not None
    assert item.find("link") is None


def test_build_error_xml() -> None:
    xml_str = build_error_xml(100, "Incorrect API key")
    root = ET.fromstring(xml_str)

    assert root.tag == "error"
    assert root.get("code") == "100"
    assert root.get("description") == "Incorrect API key"
