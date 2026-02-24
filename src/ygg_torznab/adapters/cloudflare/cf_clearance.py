import asyncio
import logging
import time
from collections.abc import Callable

import httpx

from ygg_torznab.config import Settings

logger = logging.getLogger(__name__)

_REFRESH_MARGIN_S = 300
_MAX_REFRESH_RETRIES = 3
_REFRESH_RETRY_DELAY = 5.0


class CfClearanceAdapter:
    def __init__(self, settings: Settings) -> None:
        self._cf_url = settings.cf_clearance_url
        self._ygg_url = f"https://{settings.ygg_domain}/"
        self._cookies: dict[str, str] = {}
        self._headers: dict[str, str] = {}
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._ready.set()
        self._refresh_interval = settings.cf_refresh_interval
        self._refresh_task: asyncio.Task[None] | None = None
        self._on_refresh: Callable[[], None] | None = None
        self._max_retries = settings.max_retries
        self._retry_delay = settings.cf_refresh_retry_delay
        self._request_timeout = settings.cf_request_timeout
        self._refresh_margin = settings.cf_refresh_margin
        self._last_refresh_ok: bool | None = None

    def set_on_refresh(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked after each proactive refresh."""
        self._on_refresh = callback

    def invalidate(self) -> None:
        """Force re-fetch of CF cookies on next request."""
        self._expires_at = 0.0

    def start(self) -> None:
        """Start the background proactive refresh task."""
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._refresh_task = asyncio.get_running_loop().create_task(
            self._proactive_refresh_loop()
        )

    def stop(self) -> None:
        """Stop the background proactive refresh task."""
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            self._refresh_task = None

    async def _proactive_refresh_loop(self) -> None:
        """Periodically refresh CF cookies before they expire."""
        while True:
            try:
                async with self._lock:
                    self._ready.clear()
                    try:
                        await self._refresh_with_retry()
                        if self._on_refresh is not None:
                            self._on_refresh()
                    finally:
                        self._ready.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Proactive CF refresh failed")
            await asyncio.sleep(self._refresh_interval)

    async def get_cookies(self) -> dict[str, str]:
        await self._ensure_fresh()
        await self._ready.wait()
        return self._cookies

    async def get_headers(self) -> dict[str, str]:
        await self._ensure_fresh()
        await self._ready.wait()
        return self._headers

    async def _ensure_fresh(self) -> None:
        if not self._is_expired():
            return
        async with self._lock:
            if not self._is_expired():
                return
            self._ready.clear()
            try:
                await self._refresh_with_retry()
            finally:
                self._ready.set()

    def _is_expired(self) -> bool:
        return time.monotonic() >= self._expires_at

    async def _refresh_with_retry(self) -> None:
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                await self._refresh()
                self._last_refresh_ok = True
                return
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    logger.warning(
                        "cf-clearance-scraper failed (attempt %d/%d): %s",
                        attempt + 1,
                        self._max_retries,
                        e,
                    )
                    await asyncio.sleep(self._retry_delay)
        self._last_refresh_ok = False
        raise RuntimeError(
            f"cf-clearance-scraper unavailable after {self._max_retries} attempts"
        ) from last_error

    @property
    def is_healthy(self) -> bool:
        """True if the last CF refresh succeeded (or hasn't run yet)."""
        return self._last_refresh_ok is not False

    async def _refresh(self) -> None:
        logger.info("Refreshing Cloudflare cookies via cf-clearance-scraper")
        async with httpx.AsyncClient(timeout=self._request_timeout) as client:
            response = await client.post(
                f"{self._cf_url}/cf-clearance-scraper",
                json={"url": self._ygg_url, "mode": "waf-session"},
            )
            response.raise_for_status()
            data = response.json()

        cookies_data = data.get("cookies", [])
        if not isinstance(cookies_data, list):
            raise RuntimeError("cf-clearance-scraper returned invalid cookies format")

        self._cookies = {}
        min_expires = float("inf")
        for cookie in cookies_data:
            if "name" not in cookie or "value" not in cookie:
                logger.warning("Skipping malformed cookie: %s", cookie)
                continue
            self._cookies[cookie["name"]] = cookie["value"]
            if "expires" in cookie:
                min_expires = min(min_expires, cookie["expires"])

        self._headers = {}
        for key, value in data.get("headers", {}).items():
            if key.lower() == "user-agent":
                self._headers[key] = value

        if min_expires < float("inf"):
            ttl = min_expires - time.time()
            self._expires_at = time.monotonic() + max(ttl - self._refresh_margin, 60.0)
        else:
            self._expires_at = time.monotonic() + 3600.0

        logger.info(
            "Got %d cookies, TTL %.0fs",
            len(self._cookies),
            self._expires_at - time.monotonic(),
        )
