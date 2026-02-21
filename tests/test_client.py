from unittest.mock import AsyncMock

from ygg_torznab.adapters.ygg.client import YggClient
from ygg_torznab.domain.models import RateLimitError


def test_rate_limit_error_default() -> None:
    err = RateLimitError()
    assert err.retry_after == 30.0


def test_rate_limit_error_custom() -> None:
    err = RateLimitError(120.0)
    assert err.retry_after == 120.0


def test_parse_retry_after_valid() -> None:
    assert YggClient._parse_retry_after(_mock_response({"retry-after": "60"})) == 60.0


def test_parse_retry_after_small() -> None:
    # Should clamp to 30.0 minimum
    assert YggClient._parse_retry_after(_mock_response({"retry-after": "5"})) == 30.0


def test_parse_retry_after_invalid() -> None:
    result = YggClient._parse_retry_after(_mock_response({"retry-after": "invalid"}))
    assert result == 30.0


def test_parse_retry_after_missing() -> None:
    assert YggClient._parse_retry_after(_mock_response({})) == 30.0


def _mock_response(headers: dict[str, str]) -> object:
    """Create a minimal mock response with headers."""
    mock = AsyncMock()
    mock.headers = headers
    return mock
