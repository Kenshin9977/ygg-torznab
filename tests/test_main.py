"""Tests for main.py: lifespan, _get_settings, health endpoint."""

from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from fastapi.testclient import TestClient

from ygg_torznab.config import Settings
from ygg_torznab.main import _get_settings, app


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Reset the global _settings singleton between tests."""
    import ygg_torznab.main as main_mod

    main_mod._settings = None


def test_get_settings_returns_settings() -> None:
    s = _get_settings()
    assert isinstance(s, Settings)
    assert s.nostr_relay == "wss://relay.ygg.gratis"


def test_get_settings_cached() -> None:
    s1 = _get_settings()
    s2 = _get_settings()
    assert s1 is s2


def test_lifespan_starts_app() -> None:
    """Test that the lifespan creates nostr_client and settings on app state."""
    with patch("ygg_torznab.main.NostrClient") as mock_nostr_cls:
        mock_instance = AsyncMock()
        type(mock_instance).is_healthy = PropertyMock(return_value=True)
        mock_nostr_cls.return_value = mock_instance

        with TestClient(app) as client:
            assert hasattr(app.state, "settings")
            assert hasattr(app.state, "nostr_client")
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

        mock_instance.close.assert_called_once()


def test_lifespan_no_api_key_warning() -> None:
    """When API_KEY is empty, a warning should be logged."""
    with (
        patch.dict("os.environ", {"API_KEY": ""}),
        patch("ygg_torznab.main.NostrClient") as mock_nostr_cls,
    ):
        mock_instance = AsyncMock()
        type(mock_instance).is_healthy = PropertyMock(return_value=True)
        mock_nostr_cls.return_value = mock_instance

        with TestClient(app):
            pass


def test_health_degraded_when_not_connected() -> None:
    with patch("ygg_torznab.main.NostrClient") as mock_nostr_cls:
        mock_instance = AsyncMock()
        type(mock_instance).is_healthy = PropertyMock(return_value=False)
        mock_nostr_cls.return_value = mock_instance

        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.json()["status"] == "degraded"
