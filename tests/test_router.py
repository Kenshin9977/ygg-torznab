import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from unittest.mock import AsyncMock, PropertyMock

import pytest
from fastapi.testclient import TestClient

from ygg_torznab.config import Settings
from ygg_torznab.domain.models import SearchResponse, TorrentResult
from ygg_torznab.main import app


@pytest.fixture
def client() -> TestClient:
    settings = Settings(api_key="testkey")
    mock_nostr = AsyncMock()
    type(mock_nostr).is_healthy = PropertyMock(return_value=True)

    app.state.settings = settings
    app.state.nostr_client = mock_nostr
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_nostr_client(client: TestClient) -> AsyncMock:
    return client.app.state.nostr_client  # type: ignore[union-attr, return-value]


def _make_result(title: str = "Test Torrent") -> TorrentResult:
    return TorrentResult(
        infohash="a" * 40,
        title=title,
        category_id=2183,
        size_bytes=1024 * 1024 * 700,
        seeders=10,
        leechers=2,
        grabs=500,
        publish_date=datetime(2024, 1, 1, tzinfo=UTC),
        magnet_uri="magnet:?xt=urn:btih:" + "a" * 40,
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
    response = client.get("/api?t=search&q=test")
    assert response.status_code == 401


def test_no_api_key_configured_allows_search(
    client: TestClient, mock_nostr_client: AsyncMock
) -> None:
    """When API_KEY is empty, requests pass through without auth."""
    app.state.settings.api_key = ""
    mock_nostr_client.search.return_value = SearchResponse(results=[], total=0)
    response = client.get("/api?t=search&q=test")
    assert response.status_code == 200


def test_search(client: TestClient, mock_nostr_client: AsyncMock) -> None:
    mock_nostr_client.search.return_value = SearchResponse(
        results=[_make_result()], total=1, offset=0
    )
    response = client.get("/api?t=search&q=test&apikey=testkey")
    assert response.status_code == 200
    root = ET.fromstring(response.text)
    items = root.findall("channel/item")
    assert len(items) == 1
    assert items[0].findtext("title") == "Test Torrent"


def test_search_error(client: TestClient, mock_nostr_client: AsyncMock) -> None:
    mock_nostr_client.search.side_effect = RuntimeError("Connection failed")
    response = client.get("/api?t=search&q=test&apikey=testkey")
    assert response.status_code == 500


def test_download_redirect_to_magnet(client: TestClient) -> None:
    response = client.get(
        "/api?t=download&id=" + "a" * 40 + "&apikey=testkey",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("magnet:?xt=urn:btih:" + "a" * 40)


def test_download_missing_id(client: TestClient) -> None:
    response = client.get("/api?t=download&apikey=testkey")
    assert response.status_code == 400


def test_download_invalid_id(client: TestClient) -> None:
    response = client.get("/api?t=download&id=tooshort&apikey=testkey")
    assert response.status_code == 400


def test_unknown_function(client: TestClient) -> None:
    response = client.get("/api?t=unknown&apikey=testkey")
    assert response.status_code == 400


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_degraded(client: TestClient) -> None:
    type(app.state.nostr_client).is_healthy = PropertyMock(return_value=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_search_limit_zero_uses_default(
    client: TestClient, mock_nostr_client: AsyncMock
) -> None:
    """Prowlarr sends limit=0 meaning 'no limit'; should use default (50)."""
    mock_nostr_client.search.return_value = SearchResponse(results=[], total=0)
    response = client.get("/api?t=search&q=test&limit=0&apikey=testkey")
    assert response.status_code == 200
    call_args = mock_nostr_client.search.call_args[0][0]
    assert call_args.limit == 50


def test_security_headers(client: TestClient) -> None:
    response = client.get("/api?t=caps&apikey=testkey")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
