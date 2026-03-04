from ygg_torznab.adapters.nostr.magnet import (
    YGG_EXTRA_TRACKERS,
    build_magnet_uri,
)


def test_basic_magnet_uri() -> None:
    uri = build_magnet_uri("a1b2c3d4e5f6", "Test.Torrent")
    assert uri.startswith("magnet:?xt=urn:btih:a1b2c3d4e5f6")
    assert "&dn=Test.Torrent" in uri
    assert "tracker.yggleak.top" in uri


def test_magnet_with_ygg_extra_trackers() -> None:
    uri = build_magnet_uri("abc123", "T", include_ygg_extra=True)
    for _tracker in YGG_EXTRA_TRACKERS:
        assert "tr=" in uri
    assert "opentrackr" in uri


def test_magnet_without_ygg_extra_trackers() -> None:
    uri = build_magnet_uri("abc123", "T", include_ygg_extra=False)
    assert "opentrackr" not in uri
    assert "tracker.yggleak.top" in uri


def test_magnet_title_encoding() -> None:
    uri = build_magnet_uri("abc", "Movie Name (2024)")
    assert "Movie%20Name%20%282024%29" in uri


def test_magnet_empty_title() -> None:
    uri = build_magnet_uri("abc", "")
    assert "&dn=" not in uri
    assert uri.startswith("magnet:?xt=urn:btih:abc&tr=")


def test_magnet_only_main_tracker() -> None:
    uri = build_magnet_uri("hash", "T", include_ygg_extra=False)
    assert uri.count("&tr=") == 1


def test_magnet_extra_tracker_count() -> None:
    uri = build_magnet_uri("hash", "T", include_ygg_extra=True)
    assert uri.count("&tr=") == 1 + len(YGG_EXTRA_TRACKERS)
