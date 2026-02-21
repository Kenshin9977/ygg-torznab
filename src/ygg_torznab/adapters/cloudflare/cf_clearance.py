import logging
import time

import httpx

from ygg_torznab.config import Settings

logger = logging.getLogger(__name__)

_REFRESH_MARGIN_S = 300


class CfClearanceAdapter:
    def __init__(self, settings: Settings) -> None:
        self._cf_url = settings.cf_clearance_url
        self._ygg_url = f"https://{settings.ygg_domain}/"
        self._cookies: dict[str, str] = {}
        self._headers: dict[str, str] = {}
        self._expires_at: float = 0.0

    async def get_cookies(self, url: str = "") -> dict[str, str]:
        if self._is_expired():
            await self._refresh()
        return self._cookies

    async def get_headers(self, url: str = "") -> dict[str, str]:
        if self._is_expired():
            await self._refresh()
        return self._headers

    def _is_expired(self) -> bool:
        return time.monotonic() >= self._expires_at

    async def _refresh(self) -> None:
        logger.info("Refreshing Cloudflare cookies via cf-clearance-scraper")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._cf_url}/cf-clearance-scraper",
                json={"url": self._ygg_url, "mode": "waf-session"},
            )
            response.raise_for_status()
            data = response.json()

        self._cookies = {}
        min_expires = float("inf")
        for cookie in data.get("cookies", []):
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
