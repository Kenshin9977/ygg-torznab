from unittest.mock import AsyncMock

from ygg_torznab.adapters.ygg.client import _RATE_LIMIT_WAIT, RateLimitError, YggClient


def test_rate_limit_error_default() -> None:
    err = RateLimitError()
    assert err.retry_after == _RATE_LIMIT_WAIT


def test_rate_limit_error_custom() -> None:
    err = RateLimitError(120.0)
    assert err.retry_after == 120.0


def test_parse_retry_after_valid() -> None:
    assert YggClient._parse_retry_after(_mock_response({"retry-after": "60"})) == 60.0


def test_parse_retry_after_small() -> None:
    # Should clamp to _RATE_LIMIT_WAIT minimum
    assert YggClient._parse_retry_after(_mock_response({"retry-after": "5"})) == _RATE_LIMIT_WAIT


def test_parse_retry_after_invalid() -> None:
    result = YggClient._parse_retry_after(_mock_response({"retry-after": "invalid"}))
    assert result == _RATE_LIMIT_WAIT


def test_parse_retry_after_missing() -> None:
    assert YggClient._parse_retry_after(_mock_response({})) == _RATE_LIMIT_WAIT


def _mock_response(headers: dict[str, str]) -> object:
    """Create a minimal mock response with headers."""
    mock = AsyncMock()
    mock.headers = headers
    return mock
