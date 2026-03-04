import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ygg_torznab.adapters.nostr.client import NostrClient
from ygg_torznab.config import Settings
from ygg_torznab.domain.models import SearchQuery


def _settings() -> Settings:
    return Settings(
        nostr_relay="wss://test.relay",
        ws_connect_timeout=2.0,
        ws_response_timeout=5.0,
        ws_reconnect_delay=0.01,
        ws_max_reconnect_attempts=2,
    )


def _sample_event() -> dict:
    return {
        "id": "evt1",
        "kind": 2003,
        "created_at": 1704067200,
        "tags": [
            ["title", "Test.Movie.2024"],
            ["x", "a" * 40],
            ["size", "1000000"],
            ["published_at", "1704067200"],
            ["l", "u2p.cat:2183"],
            ["l", "u2p.seed:10"],
            ["l", "u2p.leech:2"],
            ["l", "u2p.completed:100"],
        ],
    }


def _make_mock_ws(events: list[dict], sub_id_ref: list[str]) -> MagicMock:
    """Create a mock WebSocket that returns events then EOSE."""
    ws = MagicMock()

    # Track sent messages to capture sub_id
    async def mock_send(msg: str) -> None:
        data = json.loads(msg)
        if data[0] == "REQ":
            sub_id_ref.clear()
            sub_id_ref.append(data[1])

    ws.send = AsyncMock(side_effect=mock_send)

    # Ping returns a future
    pong_future: asyncio.Future[None] = asyncio.get_event_loop().create_future()
    pong_future.set_result(None)
    ws.ping = AsyncMock(return_value=pong_future)

    # recv returns events then EOSE
    call_count = 0

    async def mock_recv() -> str:
        nonlocal call_count
        sid = sub_id_ref[0] if sub_id_ref else "unknown"
        if call_count < len(events):
            evt = events[call_count]
            call_count += 1
            return json.dumps(["EVENT", sid, evt])
        return json.dumps(["EOSE", sid])

    ws.recv = AsyncMock(side_effect=mock_recv)
    ws.close = AsyncMock()
    return ws


async def test_search_returns_results() -> None:
    client = NostrClient(_settings())
    sub_id_ref: list[str] = []
    mock_ws = _make_mock_ws([_sample_event()], sub_id_ref)
    client._ws = mock_ws

    result = await client.search(SearchQuery(query="test"))

    assert len(result.results) == 1
    assert result.results[0].title == "Test.Movie.2024"
    assert result.results[0].infohash == "a" * 40
    assert result.total == 1


async def test_search_empty_results() -> None:
    client = NostrClient(_settings())
    sub_id_ref: list[str] = []
    mock_ws = _make_mock_ws([], sub_id_ref)
    client._ws = mock_ws

    result = await client.search(SearchQuery(query="nonexistent"))

    assert len(result.results) == 0
    assert result.total == 0


async def test_search_multiple_results() -> None:
    evt1 = _sample_event()
    evt2 = _sample_event()
    evt2["tags"][0] = ["title", "Another.Movie"]
    evt2["tags"][1] = ["x", "b" * 40]

    client = NostrClient(_settings())
    sub_id_ref: list[str] = []
    mock_ws = _make_mock_ws([evt1, evt2], sub_id_ref)
    client._ws = mock_ws

    result = await client.search(SearchQuery(query="movie"))

    assert len(result.results) == 2


async def test_search_with_categories() -> None:
    client = NostrClient(_settings())
    sub_id_ref: list[str] = []
    mock_ws = _make_mock_ws([_sample_event()], sub_id_ref)
    client._ws = mock_ws

    await client.search(SearchQuery(query="test", categories=[2000]))

    # Verify the REQ message includes #t filter
    sent = mock_ws.send.call_args_list[0][0][0]
    req = json.loads(sent)
    assert req[0] == "REQ"
    assert "#t" in req[2]
    assert "film" in req[2]["#t"]


async def test_search_sends_close_after_eose() -> None:
    client = NostrClient(_settings())
    sub_id_ref: list[str] = []
    mock_ws = _make_mock_ws([], sub_id_ref)
    client._ws = mock_ws

    await client.search(SearchQuery(query="test"))

    # Last send should be CLOSE
    last_send = mock_ws.send.call_args_list[-1][0][0]
    close_msg = json.loads(last_send)
    assert close_msg[0] == "CLOSE"


async def test_connection_failure_marks_unhealthy() -> None:
    client = NostrClient(_settings())
    client._ws = None

    with (
        patch(
            "ygg_torznab.adapters.nostr.client.websockets.connect",
            side_effect=ConnectionError("refused"),
        ),
        pytest.raises(RuntimeError, match="Failed to connect"),
    ):
        await client.search(SearchQuery(query="test"))

    assert client.is_healthy is False


async def test_reconnects_on_send_failure() -> None:
    settings = _settings()
    client = NostrClient(settings)

    sub_id_ref: list[str] = []
    good_ws = _make_mock_ws([_sample_event()], sub_id_ref)

    # First ws fails on send, second works
    bad_ws = MagicMock()
    pong_future: asyncio.Future[None] = asyncio.get_event_loop().create_future()
    pong_future.set_result(None)
    bad_ws.ping = AsyncMock(return_value=pong_future)
    bad_ws.send = AsyncMock(side_effect=ConnectionError("broken"))
    bad_ws.close = AsyncMock()

    client._ws = bad_ws

    # websockets.connect returns a coroutine, so the mock must be awaitable
    connect_coro = AsyncMock(return_value=good_ws)
    with patch(
        "ygg_torznab.adapters.nostr.client.websockets.connect",
        side_effect=lambda *a, **kw: connect_coro(),
    ):
        result = await client.search(SearchQuery(query="test"))

    assert len(result.results) == 1


async def test_close_cleans_up() -> None:
    client = NostrClient(_settings())
    mock_ws = MagicMock()
    mock_ws.close = AsyncMock()
    client._ws = mock_ws
    client._healthy = True

    await client.close()

    assert client._ws is None
    assert client.is_healthy is False
    mock_ws.close.assert_awaited_once()


async def test_is_healthy_default_false() -> None:
    client = NostrClient(_settings())
    assert client.is_healthy is False
