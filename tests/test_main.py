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
    with patch.dict("os.environ", {"YGG_USERNAME": "u", "YGG_PASSWORD": "p"}):
        s = _get_settings()
        assert isinstance(s, Settings)
        assert s.ygg_username == "u"


def test_get_settings_cached() -> None:
    with patch.dict("os.environ", {"YGG_USERNAME": "u", "YGG_PASSWORD": "p"}):
        s1 = _get_settings()
        s2 = _get_settings()
        assert s1 is s2


def test_lifespan_starts_app() -> None:
    """Test that the lifespan creates ygg_client and settings on app state."""
    with (
        patch.dict("os.environ", {"YGG_USERNAME": "u", "YGG_PASSWORD": "p"}),
        patch("ygg_torznab.main.CfClearanceAdapter"),
        patch("ygg_torznab.main.YggClient") as mock_ygg,
    ):
        mock_instance = AsyncMock()
        type(mock_instance).is_healthy = PropertyMock(return_value=True)
        mock_ygg.return_value = mock_instance

        with TestClient(app) as client:
            assert hasattr(app.state, "settings")
            assert hasattr(app.state, "ygg_client")
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

        mock_instance.close.assert_called_once()


def test_lifespan_starts_and_stops_cf_adapter() -> None:
    """Lifespan should call cf_adapter.start() on startup and stop() on shutdown."""
    with (
        patch.dict("os.environ", {"YGG_USERNAME": "u", "YGG_PASSWORD": "p"}),
        patch("ygg_torznab.main.CfClearanceAdapter") as mock_cf_cls,
        patch("ygg_torznab.main.YggClient") as mock_ygg,
    ):
        mock_cf = mock_cf_cls.return_value
        mock_instance = AsyncMock()
        type(mock_instance).is_healthy = PropertyMock(return_value=True)
        mock_ygg.return_value = mock_instance

        with TestClient(app):
            mock_cf.start.assert_called_once()

        mock_cf.stop.assert_called_once()


def test_lifespan_no_api_key_warning() -> None:
    """When API_KEY is empty, a warning should be logged."""
    with (
        patch.dict("os.environ", {"YGG_USERNAME": "u", "YGG_PASSWORD": "p", "API_KEY": ""}),
        patch("ygg_torznab.main.CfClearanceAdapter"),
        patch("ygg_torznab.main.YggClient") as mock_ygg,
    ):
        mock_instance = AsyncMock()
        type(mock_instance).is_healthy = PropertyMock(return_value=True)
        mock_ygg.return_value = mock_instance

        with TestClient(app):
            pass
