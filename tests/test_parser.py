from ygg_torznab.adapters.nostr.parser import (
    _build_tag_map,
    _extract_labels,
    parse_event,
)


def _sample_event() -> dict:
    return {
        "id": "abc123",
        "kind": 2003,
        "created_at": 1704067200,
        "content": "<p>desc</p>",
        "tags": [
            ["title", "Inception.2010.1080p.BluRay"],
            ["x", "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"],
            ["size", "734003200"],
            ["published_at", "1704067200"],
            ["t", "film"],
            ["l", "u2p.cat:2183"],
            ["l", "u2p.seed:42"],
            ["l", "u2p.leech:5"],
            ["l", "u2p.completed:1337"],
            ["ygg"],
        ],
    }


def test_parse_event_success() -> None:
    result = parse_event(_sample_event())
    assert result is not None
    assert result.title == "Inception.2010.1080p.BluRay"
    assert result.infohash == "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
    assert result.size_bytes == 734003200
    assert result.seeders == 42
    assert result.leechers == 5
    assert result.grabs == 1337
    assert result.category_id == 2183
    assert result.has_ygg_tag is True
    assert result.magnet_uri.startswith("magnet:?")
    assert "opentrackr" in result.magnet_uri  # ygg tag → extra trackers


def test_parse_event_missing_title() -> None:
    event = _sample_event()
    event["tags"] = [t for t in event["tags"] if t[0] != "title"]
    assert parse_event(event) is None


def test_parse_event_missing_infohash() -> None:
    event = _sample_event()
    event["tags"] = [t for t in event["tags"] if t[0] != "x"]
    assert parse_event(event) is None


def test_parse_event_no_ygg_tag() -> None:
    event = _sample_event()
    event["tags"] = [t for t in event["tags"] if t[0] != "ygg"]
    result = parse_event(event)
    assert result is not None
    assert result.has_ygg_tag is False
    assert "opentrackr" not in result.magnet_uri


def test_parse_event_missing_published_at_uses_created_at() -> None:
    event = _sample_event()
    event["tags"] = [t for t in event["tags"] if t[0] != "published_at"]
    result = parse_event(event)
    assert result is not None
    assert result.publish_date.year == 2024


def test_parse_event_missing_size_defaults_to_zero() -> None:
    event = _sample_event()
    event["tags"] = [t for t in event["tags"] if t[0] != "size"]
    result = parse_event(event)
    assert result is not None
    assert result.size_bytes == 0


def test_parse_event_missing_labels_default_to_zero() -> None:
    event = _sample_event()
    event["tags"] = [t for t in event["tags"] if t[0] != "l"]
    result = parse_event(event)
    assert result is not None
    assert result.seeders == 0
    assert result.leechers == 0
    assert result.grabs == 0
    assert result.category_id == 0


def test_extract_labels() -> None:
    tags = [["l", "u2p.seed:10"], ["l", "u2p.leech:3"], ["t", "film"]]
    labels = _extract_labels(tags)
    assert labels == {"u2p.seed": 10, "u2p.leech": 3}


def test_extract_labels_invalid_value() -> None:
    tags = [["l", "u2p.seed:abc"]]
    labels = _extract_labels(tags)
    assert labels == {"u2p.seed": 0}


def test_build_tag_map() -> None:
    tags = [["title", "T"], ["x", "hash"], ["title", "duplicate"]]
    m = _build_tag_map(tags)
    assert m["title"] == "T"  # first wins
    assert m["x"] == "hash"


def test_build_tag_map_short_tags_ignored() -> None:
    tags = [["title", "T"], ["solo"]]
    m = _build_tag_map(tags)
    assert "solo" not in m


def test_parse_event_empty_tags() -> None:
    event = {"id": "x", "kind": 2003, "created_at": 0, "tags": []}
    assert parse_event(event) is None
