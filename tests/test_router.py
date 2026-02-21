import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from unittest.mock import AsyncMock, PropertyMock

import pytest
from fastapi.testclient import TestClient

from ygg_torznab.config import Settings
from ygg_torznab.domain.models import RateLimitError, SearchResponse, TorrentResult
from ygg_torznab.main import app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(
        ygg_username="test",
        ygg_password="test",
        api_key="testkey",
    )
    mock_ygg = AsyncMock()
    type(mock_ygg).is_healthy = PropertyMock(return_value=True)

    app.state.settings = settings
    app.state.ygg_client = mock_ygg
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_ygg_client(client: TestClient) -> AsyncMock:
    return client.app.state.ygg_client  # type: ignore[union-attr, return-value]


def _make_result(torrent_id: int = 1, title: str = "Test Torrent") -> TorrentResult:
    return TorrentResult(
        torrent_id=torrent_id,
        title=title,
        detail_url=f"https://www.yggtorrent.org/torrent/film/{torrent_id}-test",
        category_id=2183,
        size_bytes=1024 * 1024 * 700,
        seeders=10,
        leechers=2,
        grabs=500,
        publish_date=datetime(2024, 1, 1, tzinfo=UTC),
        comments=3,
        download_url=f"https://www.yggtorrent.org/engine/download_torrent?id={torrent_id}",
    )


def test_caps(client: TestClient) -> None:
    response = client.get("/api?t=caps&apikey=testkey")
    assert response.status_code == 200
    root = ET.fromstring(response.text)
    assert root.tag == "caps"


def test_caps_no_api_key_required(client: TestClient) -> None:
    app.state.settings.api_key = ""
    response = client.get("/api?t=caps")
    assert response.status_code == 200


def test_wrong_api_key(client: TestClient) -> None:
    response = client.get("/api?t=search&q=test&apikey=wrong")
    assert response.status_code == 401


def test_missing_api_key_blocks_search(client: TestClient) -> None:
    """When API_KEY is configured, requests without key are rejected."""
    response = client.get("/api?t=search&q=test")
    assert response.status_code == 401


def test_no_api_key_configured_blocks_search(client: TestClient) -> None:
    """When API_KEY is empty, all non-caps requests are rejected."""
    app.state.settings.api_key = ""
    response = client.get("/api?t=search&q=test")
    assert response.status_code == 401


def test_search(client: TestClient, mock_ygg_client: AsyncMock) -> None:
    mock_ygg_client.search.return_value = SearchResponse(
        results=[_make_result()], total=1, offset=0
    )
    response = client.get("/api?t=search&q=test&apikey=testkey")
    assert response.status_code == 200
    root = ET.fromstring(response.text)
    items = root.findall("channel/item")
    assert len(items) == 1
    assert items[0].findtext("title") == "Test Torrent"


def test_search_rate_limited(client: TestClient, mock_ygg_client: AsyncMock) -> None:
    mock_ygg_client.search.side_effect = RateLimitError(60.0)
    response = client.get("/api?t=search&q=test&apikey=testkey")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


def test_search_error(client: TestClient, mock_ygg_client: AsyncMock) -> None:
    mock_ygg_client.search.side_effect = RuntimeError("Connection failed")
    response = client.get("/api?t=search&q=test&apikey=testkey")
    assert response.status_code == 500


def test_download(client: TestClient, mock_ygg_client: AsyncMock) -> None:
    mock_ygg_client.download_torrent.return_value = b"torrent data"
    response = client.get("/api?t=download&id=12345&apikey=testkey")
    assert response.status_code == 200
    assert response.content == b"torrent data"
    assert response.headers["content-type"] == "application/x-bittorrent"


def test_download_missing_id(client: TestClient) -> None:
    response = client.get("/api?t=download&apikey=testkey")
    assert response.status_code == 400


def test_download_rate_limited(client: TestClient, mock_ygg_client: AsyncMock) -> None:
    mock_ygg_client.download_torrent.side_effect = RateLimitError(30.0)
    response = client.get("/api?t=download&id=12345&apikey=testkey")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_unknown_function(client: TestClient) -> None:
    response = client.get("/api?t=unknown&apikey=testkey")
    assert response.status_code == 400


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_degraded(client: TestClient) -> None:
    type(app.state.ygg_client).is_healthy = PropertyMock(return_value=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_security_headers(client: TestClient) -> None:
    response = client.get("/api?t=caps&apikey=testkey")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
