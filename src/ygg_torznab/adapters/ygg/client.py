"""YGG HTTP client: login, search, download using Cloudflare bypass cookies."""

import asyncio
import logging
import ssl
from typing import Any

import httpx

from ygg_torznab.adapters.cloudflare.cf_clearance import CfClearanceAdapter
from ygg_torznab.adapters.ygg.categories import torznab_cats_to_ygg_subcats
from ygg_torznab.adapters.ygg.scraper import parse_search_results
from ygg_torznab.config import Settings
from ygg_torznab.domain.models import (
    _DEFAULT_RATE_LIMIT_WAIT,
    RateLimitError,
    SearchQuery,
    SearchResponse,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_LOGIN_SUCCESS_MARKER = "/user/account"
_NON_TURBO_WAIT = 31.0  # 30s server-side + 1s margin (cf. Jackett)
_CF_CHALLENGE_MARKERS = ("just a moment", "_cf_chl_opt")


class _DnsOverrideTransport(httpx.AsyncHTTPTransport):
    """Transport that overrides DNS resolution for specific domains."""

    def __init__(self, domain: str, ip: str, **kwargs: object) -> None:
        self._domain = domain
        self._ip = ip
        super().__init__(**kwargs)  # type: ignore[arg-type]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == self._domain:
            request = httpx.Request(
                method=request.method,
                url=request.url.copy_with(host=self._ip),
                headers=[
                    (b"host", self._domain.encode()),
                    *[(k, v) for k, v in request.headers.raw if k.lower() != b"host"],
                ],
                content=request.content,
                extensions={**request.extensions, "sni_hostname": self._domain},
            )
        return await super().handle_async_request(request)


class YggClient:
    def __init__(self, settings: Settings, cf_adapter: CfClearanceAdapter) -> None:
        self._domain = settings.ygg_domain
        self._ip = settings.ygg_ip
        self._username = settings.ygg_username
        self._password = settings.ygg_password
        self._turbo = settings.turbo_user
        self._cf = cf_adapter
        self._ssl_ctx = ssl.create_default_context()
        self._client: httpx.AsyncClient | None = None
        self._logged_in = False
        self._healthy = False
        self._lock = asyncio.Lock()

    @property
    def is_healthy(self) -> bool:
        return self._logged_in and self._healthy

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None and self._logged_in:
            return self._client

        async with self._lock:
            # Double-check after acquiring lock
            if self._client is not None and self._logged_in:
                return self._client

            if self._client is not None:
                await self._client.aclose()

            cookies = await self._cf.get_cookies()
            headers = await self._cf.get_headers()

            transport = _DnsOverrideTransport(
                domain=self._domain,
                ip=self._ip,
                verify=self._ssl_ctx,
            )

            self._client = httpx.AsyncClient(
                cookies=cookies,
                headers=headers,
                transport=transport,
                follow_redirects=True,
                timeout=30.0,
            )
            await self._login()
            return self._client

    async def _login(self) -> None:
        if self._client is None:
            raise RuntimeError("Client not initialized")

        base = f"https://{self._domain}"

        # Required cookie for YGG login flow (cf. ygege)
        self._client.cookies.set("account_created", "true", domain=self._domain)

        logger.debug("Logging in to YGG as %s", self._username)
        response = await self._client.get(f"{base}/auth/login")
        self._check_rate_limit(response)
        if response.status_code != 200:
            logger.warning("Login page returned %d", response.status_code)

        response = await self._client.post(
            f"{base}/auth/process_login",
            data={"id": self._username, "pass": self._password},
        )
        self._check_rate_limit(response)

        if response.status_code == 401:
            self._healthy = False
            raise RuntimeError("Login failed: invalid credentials")
        if response.status_code != 200:
            self._healthy = False
            raise RuntimeError(f"Login failed with status {response.status_code}")

        # Fetch root page to finalize session cookies (cf. ygege)
        response = await self._client.get(f"{base}/")
        self._check_rate_limit(response)

        if _LOGIN_SUCCESS_MARKER not in response.text:
            self._healthy = False
            raise RuntimeError("Login failed: credentials rejected by YGG")

        logger.info("Successfully logged in to YGG")
        self._logged_in = True
        self._healthy = True

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with retry on 429 and session expiry."""
        for attempt in range(_MAX_RETRIES):
            try:
                client = await self._ensure_client()
            except RateLimitError:
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "Login rate limited, retrying (attempt %d/%d)",
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(_DEFAULT_RATE_LIMIT_WAIT)
                    continue
                raise

            response: httpx.Response = await client.request(method.upper(), url, **kwargs)

            if response.status_code == 429:
                retry_after = self._parse_retry_after(response)
                if attempt < _MAX_RETRIES - 1:
                    logger.warning(
                        "Rate limited (429), waiting %.0fs (attempt %d/%d)",
                        retry_after,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                raise RateLimitError(retry_after)

            if response.status_code == 302 and "/auth/login" in str(
                response.headers.get("location", "")
            ):
                logger.warning(
                    "Session expired (302 → /auth/login), "
                    "re-authenticating (attempt %d/%d)",
                    attempt + 1,
                    _MAX_RETRIES,
                )
                async with self._lock:
                    self._logged_in = False
                    self._healthy = False
                    self._cf.invalidate()
                continue

            if response.status_code == 403 and self._is_cf_challenge(response):
                logger.warning(
                    "Cloudflare challenge (403), "
                    "refreshing CF cookies (attempt %d/%d)",
                    attempt + 1,
                    _MAX_RETRIES,
                )
                async with self._lock:
                    self._logged_in = False
                    self._healthy = False
                    self._cf.invalidate()
                continue

            return response

        raise RuntimeError(f"Request failed after {_MAX_RETRIES} retries")

    async def search(self, query: SearchQuery) -> SearchResponse:
        params: dict[str, str | int] = {
            "name": query.query,
            "do": "search",
        }

        if query.categories:
            ygg_subcats = torznab_cats_to_ygg_subcats(query.categories)
            if len(ygg_subcats) == 1:
                params["sub_category"] = ygg_subcats[0]
            elif ygg_subcats:
                logger.debug(
                    "Multiple YGG subcats (%s) for query, skipping category filter",
                    ygg_subcats,
                )

        if query.offset > 0:
            params["page"] = query.offset

        url = f"https://{self._domain}/engine/search"
        response = await self._request_with_retry("get", url, params=params)

        if response.status_code != 200:
            self._healthy = False
            raise RuntimeError(f"Search failed with status {response.status_code}")

        results, total = parse_search_results(response.text, self._domain)

        if query.limit < len(results):
            results = results[: query.limit]

        return SearchResponse(results=results, total=total, offset=query.offset)

    async def download_torrent(self, torrent_id: int) -> bytes:
        base = f"https://{self._domain}"

        if self._turbo:
            url = f"{base}/engine/download_torrent?id={torrent_id}"
            response = await self._request_with_retry("get", url)
        else:
            token = await self._start_download_timer(torrent_id)
            logger.info(
                "Non-turbo: waiting %.0fs before downloading torrent %d",
                _NON_TURBO_WAIT,
                torrent_id,
            )
            await asyncio.sleep(_NON_TURBO_WAIT)
            url = f"{base}/engine/download_torrent?id={torrent_id}&token={token}"
            # Direct request without retry: the token is time-sensitive and
            # a retry delay would invalidate it.
            client = await self._ensure_client()
            response = await client.request("GET", url)

        if response.status_code != 200:
            raise RuntimeError(f"Download failed with status {response.status_code}")

        return response.content

    async def _start_download_timer(self, torrent_id: int) -> str:
        """POST to start_download_timer and return the server-issued token."""
        url = f"https://{self._domain}/engine/start_download_timer"
        response = await self._request_with_retry(
            "post", url, data={"torrent_id": torrent_id}
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"start_download_timer failed with status {response.status_code}"
            )

        try:
            data = response.json()
        except Exception as e:
            raise RuntimeError("start_download_timer returned invalid JSON") from e

        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise RuntimeError(
                f"start_download_timer response missing token: {data}"
            )
        if len(token) > 256 or not token.isascii():
            raise RuntimeError("start_download_timer returned suspicious token")

        return token

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._logged_in = False
            self._healthy = False

    @staticmethod
    def _is_cf_challenge(response: httpx.Response) -> bool:
        """Check if a 403 response is a Cloudflare challenge page."""
        body = response.text.lower()
        return any(marker in body for marker in _CF_CHALLENGE_MARKERS)

    @staticmethod
    def _check_rate_limit(response: httpx.Response) -> None:
        if response.status_code == 429:
            retry_after = YggClient._parse_retry_after(response)
            raise RateLimitError(retry_after)

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float:
        header = response.headers.get("retry-after", "")
        try:
            return max(float(header), _DEFAULT_RATE_LIMIT_WAIT)
        except ValueError:
            return _DEFAULT_RATE_LIMIT_WAIT
