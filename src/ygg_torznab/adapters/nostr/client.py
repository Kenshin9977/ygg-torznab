"""Nostr WebSocket client for ygg.gratis relay."""

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any

import websockets

from ygg_torznab.adapters.nostr.categories import torznab_cats_to_tags
from ygg_torznab.adapters.nostr.parser import parse_event
from ygg_torznab.config import Settings
from ygg_torznab.domain.models import SearchQuery, SearchResponse, TorrentResult

logger = logging.getLogger(__name__)


class NostrClient:
    """Client for querying NIP-35 torrent events from a Nostr relay."""

    def __init__(self, settings: Settings) -> None:
        self._relay_url = settings.nostr_relay
        self._connect_timeout = settings.ws_connect_timeout
        self._response_timeout = settings.ws_response_timeout
        self._reconnect_delay = settings.ws_reconnect_delay
        self._max_reconnect_attempts = settings.ws_max_reconnect_attempts
        self._ws: Any = None
        self._lock = asyncio.Lock()
        self._healthy = False

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Search the Nostr relay for NIP-35 Kind 2003 events."""
        ws = await self._ensure_connection()
        sub_id = uuid.uuid4().hex[:8]

        nostr_filter: dict[str, Any] = {
            "kinds": [2003],
            "limit": query.limit,
        }

        if query.query:
            nostr_filter["search"] = query.query

        if query.categories:
            tags = torznab_cats_to_tags(query.categories)
            if tags:
                nostr_filter["#t"] = tags

        if query.until is not None:
            nostr_filter["until"] = query.until

        req_msg = json.dumps(["REQ", sub_id, nostr_filter])
        logger.debug("Sending Nostr REQ: %s", req_msg)

        try:
            await ws.send(req_msg)
        except Exception:
            await self._close_ws()
            ws = await self._ensure_connection()
            await ws.send(req_msg)

        results, got_eose = await self._collect_events(ws, sub_id)

        if got_eose:
            with contextlib.suppress(Exception):
                await ws.send(json.dumps(["CLOSE", sub_id]))
        else:
            # Timeout or error — connection is in an unknown state, close it
            logger.info("Closing stale WebSocket after incomplete response")
            await self._close_ws()

        return SearchResponse(results=results, total=len(results))

    async def close(self) -> None:
        """Close the WebSocket connection."""
        await self._close_ws()
        self._healthy = False

    async def _ensure_connection(self) -> Any:
        """Get or create a WebSocket connection to the relay."""
        if self._ws is not None:
            try:
                pong = await self._ws.ping()
                await asyncio.wait_for(pong, timeout=5.0)
                return self._ws
            except Exception:
                logger.debug("WebSocket ping failed, reconnecting")
                await self._close_ws()

        async with self._lock:
            if self._ws is not None:
                return self._ws

            for attempt in range(self._max_reconnect_attempts):
                try:
                    self._ws = await asyncio.wait_for(
                        websockets.connect(self._relay_url),
                        timeout=self._connect_timeout,
                    )
                    self._healthy = True
                    logger.info("Connected to Nostr relay %s", self._relay_url)
                    return self._ws
                except Exception:
                    if attempt < self._max_reconnect_attempts - 1:
                        logger.warning(
                            "Failed to connect to relay (attempt %d/%d), retrying in %.0fs",
                            attempt + 1,
                            self._max_reconnect_attempts,
                            self._reconnect_delay,
                        )
                        await asyncio.sleep(self._reconnect_delay)
                    else:
                        self._healthy = False
                        raise RuntimeError(
                            f"Failed to connect to relay after"
                            f" {self._max_reconnect_attempts} attempts"
                        ) from None

        raise RuntimeError("Unreachable")  # pragma: no cover

    async def _collect_events(
        self, ws: Any, sub_id: str
    ) -> tuple[list[TorrentResult], bool]:
        """Collect EVENT messages until EOSE is received.

        Returns (results, got_eose) where got_eose indicates clean completion.
        """
        results: list[TorrentResult] = []
        deadline = asyncio.get_event_loop().time() + self._response_timeout

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                logger.warning("Timeout waiting for EOSE from relay")
                return results, False

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except TimeoutError:
                logger.warning("Timeout waiting for relay message")
                return results, False
            except Exception:
                logger.exception("Error receiving from relay")
                return results, False

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(msg, list) or len(msg) < 2:
                continue

            msg_type = msg[0]

            if msg_type == "EOSE" and msg[1] == sub_id:
                return results, True

            if msg_type == "EVENT" and msg[1] == sub_id and len(msg) >= 3:
                result = parse_event(msg[2])
                if result is not None:
                    results.append(result)

            if msg_type == "NOTICE":
                logger.info("Relay NOTICE: %s", msg[1] if len(msg) > 1 else "?")

        return results, False  # pragma: no cover

    async def _close_ws(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
