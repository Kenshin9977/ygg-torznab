import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ygg_torznab.adapters.cloudflare.cf_clearance import (
    _MAX_REFRESH_RETRIES,
    _REFRESH_MARGIN_S,
    CfClearanceAdapter,
)
from ygg_torznab.config import Settings

_DUMMY_REQUEST = httpx.Request("POST", "http://cf:3000/cf-clearance-scraper")


def _settings() -> Settings:
    return Settings(ygg_username="u", ygg_password="p", cf_clearance_url="http://cf:3000")


def _cf_response_data(
    cookies: list[dict[str, object]] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    """Build a typical cf-clearance-scraper JSON response body."""
    return {
        "cookies": cookies
        or [
            {"name": "cf_clearance", "value": "abc123", "expires": time.time() + 7200},
        ],
        "headers": headers or {"User-Agent": "Mozilla/5.0 test"},
    }


def _ok_response(data: dict[str, object] | None = None) -> httpx.Response:
    """Build an httpx.Response(200) with a request set (needed for raise_for_status)."""
    return httpx.Response(200, json=data or _cf_response_data(), request=_DUMMY_REQUEST)


def _mock_async_client(post_return: object = None, post_side_effect: object = None) -> AsyncMock:
    """Create a mock httpx.AsyncClient usable as async context manager."""
    mock = AsyncMock()
    if post_side_effect is not None:
        mock.post.side_effect = post_side_effect
    else:
        mock.post.return_value = post_return or _ok_response()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def adapter() -> CfClearanceAdapter:
    return CfClearanceAdapter(_settings())


async def test_get_cookies_refreshes_on_first_call(adapter: CfClearanceAdapter) -> None:
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client()
        cookies = await adapter.get_cookies()
    assert cookies == {"cf_clearance": "abc123"}


async def test_get_headers_returns_user_agent(adapter: CfClearanceAdapter) -> None:
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client()
        headers = await adapter.get_headers()
    assert headers == {"User-Agent": "Mozilla/5.0 test"}


async def test_ignores_non_user_agent_headers(adapter: CfClearanceAdapter) -> None:
    data = _cf_response_data(headers={"User-Agent": "Bot", "Accept": "text/html", "X-Custom": "v"})
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        headers = await adapter.get_headers()
    assert headers == {"User-Agent": "Bot"}


async def test_cached_cookies_no_extra_refresh(adapter: CfClearanceAdapter) -> None:
    mock = _mock_async_client()
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = mock
        await adapter.get_cookies()
        await adapter.get_cookies()  # should use cache
    mock.post.assert_called_once()


async def test_expired_cookies_trigger_refresh(adapter: CfClearanceAdapter) -> None:
    mock = _mock_async_client()
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = mock
        await adapter.get_cookies()
        adapter._expires_at = 0.0  # force expiry
        await adapter.get_cookies()
    assert mock.post.call_count == 2


async def test_no_expires_defaults_to_1h(adapter: CfClearanceAdapter) -> None:
    data = _cf_response_data(cookies=[{"name": "cf_clearance", "value": "v"}])
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        await adapter.get_cookies()
    # TTL should be ~3600s (1h) since no expires in cookie
    expected_min = time.monotonic() + 3500
    assert adapter._expires_at > expected_min


async def test_ttl_uses_margin(adapter: CfClearanceAdapter) -> None:
    future_expires = time.time() + 10000
    data = _cf_response_data(cookies=[{"name": "c", "value": "v", "expires": future_expires}])
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        before = time.monotonic()
        await adapter.get_cookies()
    expected_ttl = 10000 - _REFRESH_MARGIN_S
    assert adapter._expires_at - before == pytest.approx(expected_ttl, abs=5.0)


async def test_short_ttl_clamps_to_60s(adapter: CfClearanceAdapter) -> None:
    short_expires = time.time() + 100  # minus margin (300) → negative → clamp to 60
    data = _cf_response_data(cookies=[{"name": "c", "value": "v", "expires": short_expires}])
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        before = time.monotonic()
        await adapter.get_cookies()
    assert adapter._expires_at - before == pytest.approx(60.0, abs=5.0)


async def test_invalid_cookies_format_raises(adapter: CfClearanceAdapter) -> None:
    data = {"cookies": "not-a-list", "headers": {}}
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        with pytest.raises(RuntimeError, match="invalid cookies format"):
            await adapter.get_cookies()


async def test_malformed_cookie_skipped(adapter: CfClearanceAdapter) -> None:
    data = _cf_response_data(
        cookies=[
            {"name": "cf_clearance", "value": "good"},
            {"bad_key": "no name field"},
        ]
    )
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        cookies = await adapter.get_cookies()
    assert cookies == {"cf_clearance": "good"}


async def test_retry_on_http_error(adapter: CfClearanceAdapter) -> None:
    error_resp = httpx.Response(500, request=_DUMMY_REQUEST)
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        mock = _mock_async_client(
            post_side_effect=[
                httpx.HTTPStatusError("500", request=_DUMMY_REQUEST, response=error_resp),
                _ok_response(),
            ]
        )
        cls.return_value = mock
        with patch("ygg_torznab.adapters.cloudflare.cf_clearance.asyncio.sleep"):
            cookies = await adapter.get_cookies()
    assert cookies == {"cf_clearance": "abc123"}
    assert mock.post.call_count == 2


async def test_retry_on_connect_error(adapter: CfClearanceAdapter) -> None:
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(
            post_side_effect=[httpx.ConnectError("refused"), _ok_response()]
        )
        with patch("ygg_torznab.adapters.cloudflare.cf_clearance.asyncio.sleep"):
            cookies = await adapter.get_cookies()
    assert cookies == {"cf_clearance": "abc123"}


async def test_retry_on_timeout(adapter: CfClearanceAdapter) -> None:
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(
            post_side_effect=[httpx.TimeoutException("timed out"), _ok_response()]
        )
        with patch("ygg_torznab.adapters.cloudflare.cf_clearance.asyncio.sleep"):
            cookies = await adapter.get_cookies()
    assert cookies == {"cf_clearance": "abc123"}


async def test_all_retries_exhausted_raises(adapter: CfClearanceAdapter) -> None:
    mock = _mock_async_client(post_side_effect=httpx.ConnectError("down"))
    with (
        patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls,
        patch("ygg_torznab.adapters.cloudflare.cf_clearance.asyncio.sleep"),
        pytest.raises(RuntimeError, match=f"after {_MAX_REFRESH_RETRIES} attempts"),
    ):
        cls.return_value = mock
        await adapter.get_cookies()
    assert mock.post.call_count == _MAX_REFRESH_RETRIES


async def test_double_check_pattern_concurrent(adapter: CfClearanceAdapter) -> None:
    """Two concurrent get_cookies should only trigger one refresh."""
    call_count = 0

    async def slow_post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return _ok_response()

    mock = _mock_async_client()
    mock.post = slow_post
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = mock
        await asyncio.gather(adapter.get_cookies(), adapter.get_cookies())
    assert call_count == 1


async def test_multiple_cookies_tracked(adapter: CfClearanceAdapter) -> None:
    data = _cf_response_data(
        cookies=[
            {"name": "cf_clearance", "value": "abc", "expires": time.time() + 7200},
            {"name": "__cfduid", "value": "def", "expires": time.time() + 3600},
        ]
    )
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        cookies = await adapter.get_cookies()
    assert cookies == {"cf_clearance": "abc", "__cfduid": "def"}


async def test_min_expires_used_for_ttl(adapter: CfClearanceAdapter) -> None:
    """When multiple cookies, the earliest expiry should determine TTL."""
    short_exp = time.time() + 2000
    long_exp = time.time() + 8000
    data = _cf_response_data(
        cookies=[
            {"name": "a", "value": "1", "expires": long_exp},
            {"name": "b", "value": "2", "expires": short_exp},
        ]
    )
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        before = time.monotonic()
        await adapter.get_cookies()
    expected_ttl = 2000 - _REFRESH_MARGIN_S
    assert adapter._expires_at - before == pytest.approx(expected_ttl, abs=5.0)


async def test_missing_cookies_key_empty_dict(adapter: CfClearanceAdapter) -> None:
    data: dict[str, object] = {"headers": {}}
    with patch("ygg_torznab.adapters.cloudflare.cf_clearance.httpx.AsyncClient") as cls:
        cls.return_value = _mock_async_client(post_return=_ok_response(data))
        cookies = await adapter.get_cookies()
    assert cookies == {}


def test_invalidate_forces_refresh(adapter: CfClearanceAdapter) -> None:
    """invalidate() should reset expires_at so next call triggers refresh."""
    adapter._expires_at = time.monotonic() + 9999.0  # far future
    adapter.invalidate()
    assert adapter._is_expired() is True
