import asyncio
import logging
import time

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

    async def get_cookies(self) -> dict[str, str]:
        await self._ensure_fresh()
        return self._cookies

    async def get_headers(self) -> dict[str, str]:
        await self._ensure_fresh()
        return self._headers

    async def _ensure_fresh(self) -> None:
        if not self._is_expired():
            return
        async with self._lock:
            if not self._is_expired():
                return
            await self._refresh_with_retry()

    def _is_expired(self) -> bool:
        return time.monotonic() >= self._expires_at

    async def _refresh_with_retry(self) -> None:
        last_error: Exception | None = None
        for attempt in range(_MAX_REFRESH_RETRIES):
            try:
                await self._refresh()
                return
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < _MAX_REFRESH_RETRIES - 1:
                    logger.warning(
                        "cf-clearance-scraper failed (attempt %d/%d): %s",
                        attempt + 1,
                        _MAX_REFRESH_RETRIES,
                        e,
                    )
                    await asyncio.sleep(_REFRESH_RETRY_DELAY)
        raise RuntimeError(
            f"cf-clearance-scraper unavailable after {_MAX_REFRESH_RETRIES} attempts"
        ) from last_error

    async def _refresh(self) -> None:
        logger.info("Refreshing Cloudflare cookies via cf-clearance-scraper")
        async with httpx.AsyncClient(timeout=120.0) as client:
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
            self._expires_at = time.monotonic() + max(ttl - _REFRESH_MARGIN_S, 60.0)
        else:
            self._expires_at = time.monotonic() + 3600.0

        logger.info(
            "Got %d cookies, TTL %.0fs",
            len(self._cookies),
            self._expires_at - time.monotonic(),
        )
