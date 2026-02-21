from pathlib import Path

from ygg_torznab.adapters.ygg.scraper import (
    extract_torrent_id,
    parse_search_results,
    parse_size,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_size_go() -> None:
    assert parse_size("86.12Go") == int(86.12 * 1024**3)


def test_parse_size_mo() -> None:
    assert parse_size("700Mo") == 700 * 1024**2


def test_parse_size_ko() -> None:
    assert parse_size("512Ko") == 512 * 1024


def test_parse_size_to() -> None:
    assert parse_size("1.5To") == int(1.5 * 1024**4)


def test_parse_size_comma() -> None:
    assert parse_size("1,5Go") == int(1.5 * 1024**3)


def test_parse_size_invalid() -> None:
    assert parse_size("unknown") == 0


def test_extract_torrent_id() -> None:
    url = "https://www.yggtorrent.org/torrent/filmvid%C3%A9o/film/271361-inception+2010"
    assert extract_torrent_id(url) == 271361


def test_extract_torrent_id_large() -> None:
    url = "https://www.yggtorrent.org/torrent/audio/musique/1234567-some+torrent"
    assert extract_torrent_id(url) == 1234567


def test_parse_search_results_fixture() -> None:
    html = (FIXTURES_DIR / "search_inception.html").read_text(encoding="utf-8")
    results, total = parse_search_results(html, "www.yggtorrent.org")

    assert total > 0
    assert len(results) > 0

    first = results[0]
    assert first.torrent_id > 0
    assert first.title != ""
    assert first.category_id > 0
    assert first.size_bytes > 0
    assert first.seeders >= 0
    assert first.leechers >= 0
    assert "inception" in first.title.lower()
    assert first.download_url.startswith("https://www.yggtorrent.org/engine/download_torrent")


def test_parse_search_results_all_fields() -> None:
    html = (FIXTURES_DIR / "search_inception.html").read_text(encoding="utf-8")
    results, _ = parse_search_results(html, "www.yggtorrent.org")

    for result in results:
        assert result.torrent_id > 0
        assert result.title
        assert result.detail_url
        assert result.publish_date.year >= 2010
