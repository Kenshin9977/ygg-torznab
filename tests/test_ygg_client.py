"""Tests for YggClient: login, search, download, retry logic, DNS override."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ygg_torznab.adapters.ygg.client import YggClient, _DnsOverrideTransport
from ygg_torznab.config import Settings
from ygg_torznab.domain.models import RateLimitError, SearchQuery


def _settings(*, turbo_user: bool = True) -> Settings:
    return Settings(
        ygg_username="testuser",
        ygg_password="testpass",
        ygg_domain="www.yggtorrent.org",
        ygg_ip="1.2.3.4",
        turbo_user=turbo_user,
    )


def _make_client(*, turbo_user: bool = True) -> tuple[YggClient, AsyncMock]:
    """Create a YggClient with a mocked CfClearanceAdapter."""
    cf = AsyncMock()
    cf.get_cookies.return_value = {"cf_clearance": "test"}
    cf.get_headers.return_value = {"User-Agent": "TestBot"}
    client = YggClient(_settings(turbo_user=turbo_user), cf)
    return client, cf


@asynccontextmanager
async def _patched_login(
    client: YggClient,
    login_page: httpx.Response,
    login_result: httpx.Response | None = None,
) -> AsyncIterator[AsyncMock]:
    """Patch CF adapter, DnsOverride transport, and httpx.AsyncClient for login tests."""
    with (
        patch.object(client, "_cf", new_callable=AsyncMock) as mock_cf,
        patch("ygg_torznab.adapters.ygg.client._DnsOverrideTransport"),
        patch("ygg_torznab.adapters.ygg.client.httpx.AsyncClient") as mock_aclient,
    ):
        mock_cf.get_cookies.return_value = {"cf_clearance": "test"}
        mock_cf.get_headers.return_value = {}
        mock_instance = AsyncMock()
        mock_instance.get.return_value = login_page
        if login_result is not None:
            mock_instance.post.return_value = login_result
        mock_aclient.return_value = mock_instance
        yield mock_aclient


# --- DnsOverrideTransport ---


async def test_dns_override_rewrites_host() -> None:
    transport = _DnsOverrideTransport(domain="www.yggtorrent.org", ip="1.2.3.4")
    original_request = httpx.Request("GET", "https://www.yggtorrent.org/search")

    with patch.object(
        httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value = httpx.Response(200)
        await transport.handle_async_request(original_request)

        sent_request = mock_super.call_args[0][0]
        assert sent_request.url.host == "1.2.3.4"
        assert sent_request.headers["host"] == "www.yggtorrent.org"
        assert sent_request.extensions["sni_hostname"] == "www.yggtorrent.org"


async def test_dns_override_ignores_other_domains() -> None:
    transport = _DnsOverrideTransport(domain="www.yggtorrent.org", ip="1.2.3.4")
    original_request = httpx.Request("GET", "https://other.com/path")

    with patch.object(
        httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
    ) as mock_super:
        mock_super.return_value = httpx.Response(200)
        await transport.handle_async_request(original_request)

        sent_request = mock_super.call_args[0][0]
        assert sent_request.url.host == "other.com"


# --- YggClient properties ---


def test_is_healthy_default_false() -> None:
    client, _ = _make_client()
    assert client.is_healthy is False


# --- Login ---


async def test_login_success() -> None:
    client, _ = _make_client()
    login_page = httpx.Response(200, text="<html>login form</html>")
    login_result = httpx.Response(200, text="redirect to /user/account ok")

    async with _patched_login(client, login_page, login_result):
        await client._ensure_client()

    assert client._logged_in is True
    assert client.is_healthy is True


async def test_login_bad_credentials() -> None:
    client, _ = _make_client()
    login_page = httpx.Response(200, text="<html>login form</html>")
    login_result = httpx.Response(200, text="<html>bad credentials try again</html>")

    async with _patched_login(client, login_page, login_result):
        with pytest.raises(RuntimeError, match="credentials rejected"):
            await client._ensure_client()

    assert client._logged_in is False
    assert client.is_healthy is False


async def test_login_http_error() -> None:
    client, _ = _make_client()
    login_page = httpx.Response(200, text="<html>form</html>")
    login_result = httpx.Response(503, text="Service Unavailable")

    async with _patched_login(client, login_page, login_result):
        with pytest.raises(RuntimeError, match="Login failed with status 503"):
            await client._ensure_client()


async def test_login_rate_limited() -> None:
    client, _ = _make_client()
    login_page = httpx.Response(429, headers={"retry-after": "60"}, text="")

    async with _patched_login(client, login_page):
        with pytest.raises(RateLimitError):
            await client._ensure_client()


# --- _ensure_client caching ---


async def test_ensure_client_caches() -> None:
    """Second call should return cached client without re-login."""
    client, _ = _make_client()
    login_page = httpx.Response(200, text="<html>form</html>")
    login_result = httpx.Response(200, text="/user/account logged in")

    async with _patched_login(client, login_page, login_result) as mock_aclient:
        c1 = await client._ensure_client()
        c2 = await client._ensure_client()

    assert c1 is c2
    mock_aclient.assert_called_once()


# --- Request with retry ---


async def test_request_with_retry_success() -> None:
    client, _ = _make_client()
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, text="ok")
    client._client = mock_http
    client._logged_in = True

    response = await client._request_with_retry("GET", "https://example.com/test")
    assert response.status_code == 200


async def test_request_with_retry_429_then_success() -> None:
    client, _ = _make_client()
    mock_http = AsyncMock()
    mock_http.request.side_effect = [
        httpx.Response(429, headers={"retry-after": "30"}, text=""),
        httpx.Response(200, text="ok"),
    ]
    client._client = mock_http
    client._logged_in = True

    with patch("ygg_torznab.adapters.ygg.client.asyncio.sleep"):
        response = await client._request_with_retry("GET", "https://example.com")

    assert response.status_code == 200
    assert mock_http.request.call_count == 2


async def test_request_with_retry_429_exhausted() -> None:
    client, _ = _make_client()
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(429, headers={"retry-after": "30"}, text="")
    client._client = mock_http
    client._logged_in = True

    with patch("ygg_torznab.adapters.ygg.client.asyncio.sleep"), pytest.raises(RateLimitError):
        await client._request_with_retry("GET", "https://example.com")


async def test_request_with_retry_session_expired() -> None:
    """302 to /auth/login triggers re-auth."""
    client, _ = _make_client()

    expired_resp = httpx.Response(302, headers={"location": "/auth/login"}, text="")
    ok_resp = httpx.Response(200, text="ok")
    call_count = 0

    async def mock_request(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return expired_resp if call_count == 1 else ok_resp

    mock_http = AsyncMock()
    mock_http.request = mock_request
    client._client = mock_http
    client._logged_in = True
    client._healthy = True

    login_page = httpx.Response(200, text="<html>form</html>")
    login_result = httpx.Response(200, text="/user/account success")

    async with _patched_login(client, login_page, login_result) as mock_aclient:
        # Override the mock's request to return ok_resp after re-login
        mock_aclient.return_value.request = AsyncMock(return_value=ok_resp)
        response = await client._request_with_retry("GET", "https://example.com")

    assert response.status_code == 200
    assert client._logged_in is True


async def test_request_with_retry_login_rate_limited_then_success() -> None:
    """RateLimitError from login gets retried."""
    client, _ = _make_client()
    call_count = 0
    ok_resp = httpx.Response(200, text="ok")

    async def mock_ensure_client() -> httpx.AsyncClient:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RateLimitError(30.0)
        mock_http = AsyncMock()
        mock_http.request.return_value = ok_resp
        client._client = mock_http
        return mock_http

    client._ensure_client = mock_ensure_client  # type: ignore[assignment]

    with patch("ygg_torznab.adapters.ygg.client.asyncio.sleep"):
        response = await client._request_with_retry("GET", "https://example.com")

    assert response.status_code == 200


async def test_request_retries_exhausted() -> None:
    """All retries consumed on 302/session-expired -> RuntimeError."""
    client, _ = _make_client()
    expired_resp = httpx.Response(302, headers={"location": "/auth/login"}, text="")

    async def mock_ensure_client() -> httpx.AsyncClient:
        mock_http = AsyncMock()
        mock_http.request.return_value = expired_resp
        return mock_http

    client._ensure_client = mock_ensure_client  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="after 3 retries"):
        await client._request_with_retry("GET", "https://example.com")


# --- Search ---


async def test_search_success() -> None:
    client, _ = _make_client()
    html_content = """
    <html><body>
    <section class="content"><h2>Résultats: <font>5</font></h2></section>
    <div class="table-responsive results">
    <table class="table"><tbody>
    <tr>
        <td><div class="hidden">2183</div></td>
        <td><a href="https://www.yggtorrent.org/torrent/film/123-test">Test Torrent</a></td>
        <td>detail</td>
        <td>3</td>
        <td><div class="hidden">1704067200</div></td>
        <td>700Mo</td>
        <td>100</td>
        <td>10</td>
        <td>5</td>
    </tr>
    </tbody></table>
    </div>
    </body></html>
    """
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, text=html_content)
    client._client = mock_http
    client._logged_in = True

    result = await client.search(SearchQuery(query="test", limit=50))

    assert result.total == 5
    assert len(result.results) == 1
    assert result.results[0].title == "Test Torrent"


async def test_search_with_category() -> None:
    client, _ = _make_client()
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, text="<html></html>")
    client._client = mock_http
    client._logged_in = True

    await client.search(SearchQuery(query="test", categories=[2000]))

    call_kwargs = mock_http.request.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
    assert "sub_category" in params


async def test_search_with_offset() -> None:
    client, _ = _make_client()
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, text="<html></html>")
    client._client = mock_http
    client._logged_in = True

    await client.search(SearchQuery(query="test", offset=50))

    call_kwargs = mock_http.request.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
    assert params["page"] == 50


async def test_search_limits_results() -> None:
    client, _ = _make_client()
    html_content = """
    <html><body>
    <section class="content"><h2><font>10</font></h2></section>
    <div class="table-responsive results">
    <table class="table"><tbody>
    <tr>
        <td><div class="hidden">2183</div></td>
        <td><a href="https://www.yggtorrent.org/torrent/film/1-a">A</a></td>
        <td>-</td><td>0</td>
        <td><div class="hidden">1704067200</div></td>
        <td>100Mo</td><td>10</td><td>5</td><td>1</td>
    </tr>
    <tr>
        <td><div class="hidden">2183</div></td>
        <td><a href="https://www.yggtorrent.org/torrent/film/2-b">B</a></td>
        <td>-</td><td>0</td>
        <td><div class="hidden">1704067200</div></td>
        <td>200Mo</td><td>20</td><td>10</td><td>2</td>
    </tr>
    </tbody></table>
    </div>
    </body></html>
    """
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, text=html_content)
    client._client = mock_http
    client._logged_in = True

    result = await client.search(SearchQuery(query="test", limit=1))

    assert len(result.results) == 1
    assert result.total == 10


async def test_search_failure_status() -> None:
    client, _ = _make_client()
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(503, text="down")
    client._client = mock_http
    client._logged_in = True

    with pytest.raises(RuntimeError, match="Search failed with status 503"):
        await client.search(SearchQuery(query="test"))

    assert client.is_healthy is False


# --- Download (turbo) ---


async def test_download_turbo_success() -> None:
    client, _ = _make_client(turbo_user=True)
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, content=b"torrent-data")
    client._client = mock_http
    client._logged_in = True

    data = await client.download_torrent(12345)
    assert data == b"torrent-data"
    # Turbo: single GET, no timer POST
    mock_http.request.assert_called_once()
    call_args = mock_http.request.call_args
    assert call_args[0][1].endswith("id=12345")
    assert "token" not in call_args[0][1]


async def test_download_turbo_failure() -> None:
    client, _ = _make_client(turbo_user=True)
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(404, text="Not found")
    client._client = mock_http
    client._logged_in = True

    with pytest.raises(RuntimeError, match="Download failed with status 404"):
        await client.download_torrent(99999)


# --- Download (non-turbo) ---


async def test_download_non_turbo_success() -> None:
    client, _ = _make_client(turbo_user=False)
    mock_http = AsyncMock()

    timer_resp = httpx.Response(200, json={"token": "abc123"})
    torrent_resp = httpx.Response(200, content=b"torrent-data")
    # First call via _request_with_retry (POST timer), second is direct request (GET download)
    mock_http.request.side_effect = [timer_resp, torrent_resp]

    client._client = mock_http
    client._logged_in = True

    with patch("ygg_torznab.adapters.ygg.client.asyncio.sleep") as mock_sleep:
        data = await client.download_torrent(12345)

    assert data == b"torrent-data"
    # Should have waited 31s
    mock_sleep.assert_called_once_with(31.0)
    # Two requests: POST timer (via retry) + GET download (direct)
    assert mock_http.request.call_count == 2
    # First call: POST to start_download_timer
    first_call = mock_http.request.call_args_list[0]
    assert first_call[0][0] == "POST"
    assert "start_download_timer" in first_call[0][1]
    # Second call: direct GET with token (no retry wrapper)
    second_call = mock_http.request.call_args_list[1]
    assert second_call[0][0] == "GET"
    assert "token=abc123" in second_call[0][1]


async def test_download_non_turbo_timer_error() -> None:
    client, _ = _make_client(turbo_user=False)
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(500, text="error")
    client._client = mock_http
    client._logged_in = True

    with pytest.raises(RuntimeError, match="start_download_timer failed"):
        await client.download_torrent(12345)


async def test_download_non_turbo_invalid_json() -> None:
    client, _ = _make_client(turbo_user=False)
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, text="not json")
    client._client = mock_http
    client._logged_in = True

    with pytest.raises(RuntimeError, match="invalid JSON"):
        await client.download_torrent(12345)


async def test_download_non_turbo_missing_token() -> None:
    client, _ = _make_client(turbo_user=False)
    mock_http = AsyncMock()
    mock_http.request.return_value = httpx.Response(200, json={"error": "no token"})
    client._client = mock_http
    client._logged_in = True

    with pytest.raises(RuntimeError, match="missing token"):
        await client.download_torrent(12345)


# --- Close ---


async def test_close() -> None:
    client, _ = _make_client()
    mock_http = AsyncMock()
    client._client = mock_http
    client._logged_in = True
    client._healthy = True

    await client.close()

    assert client._client is None
    assert client._logged_in is False
    assert client.is_healthy is False
    mock_http.aclose.assert_called_once()


async def test_close_no_client() -> None:
    client, _ = _make_client()
    await client.close()
    assert client._client is None


# --- _check_rate_limit ---


def test_check_rate_limit_429() -> None:
    resp = httpx.Response(429, headers={"retry-after": "45"}, text="")
    with pytest.raises(RateLimitError) as exc_info:
        YggClient._check_rate_limit(resp)
    assert exc_info.value.retry_after == 45.0


def test_check_rate_limit_200_no_raise() -> None:
    resp = httpx.Response(200, text="ok")
    YggClient._check_rate_limit(resp)  # should not raise


# --- _login edge: client is None ---


async def test_login_without_client_raises() -> None:
    client, _ = _make_client()
    with pytest.raises(RuntimeError, match="Client not initialized"):
        await client._login()
