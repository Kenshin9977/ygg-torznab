"""YGG HTTP client: login, search, download using Cloudflare bypass cookies."""

import logging
import ssl

import httpx

from ygg_torznab.adapters.cloudflare.cf_clearance import CfClearanceAdapter
from ygg_torznab.adapters.ygg.categories import torznab_cats_to_ygg_subcats
from ygg_torznab.adapters.ygg.scraper import parse_search_results
from ygg_torznab.config import Settings
from ygg_torznab.domain.models import SearchQuery, SearchResponse

logger = logging.getLogger(__name__)


class _DnsOverrideTransport(httpx.AsyncHTTPTransport):
    """Transport that overrides DNS resolution for specific domains."""

    def __init__(self, domain: str, ip: str, **kwargs: object) -> None:
        self._domain = domain
        self._ip = ip
        super().__init__(**kwargs)  # type: ignore[arg-type]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == self._domain:
            # Rewrite the URL to use the IP, but keep the Host header
            request = httpx.Request(
                method=request.method,
                url=request.url.copy_with(host=self._ip),
                headers=[(b"host", self._domain.encode()), *[
                    (k, v) for k, v in request.headers.raw if k.lower() != b"host"
                ]],
                content=request.content,
                extensions={
                    **request.extensions,
                    "sni_hostname": self._domain,
                },
            )
        return await super().handle_async_request(request)


class YggClient:
    def __init__(self, settings: Settings, cf_adapter: CfClearanceAdapter) -> None:
        self._domain = settings.ygg_domain
        self._ip = settings.ygg_ip
        self._username = settings.ygg_username
        self._password = settings.ygg_password
        self._cf = cf_adapter
        self._client: httpx.AsyncClient | None = None
        self._logged_in = False

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None and self._logged_in:
            return self._client

        if self._client is not None:
            await self._client.aclose()

        cookies = await self._cf.get_cookies()
        headers = await self._cf.get_headers()

        ssl_ctx = ssl.create_default_context()
        transport = _DnsOverrideTransport(
            domain=self._domain,
            ip=self._ip,
            verify=ssl_ctx,
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

        logger.info("Logging in to YGG as %s", self._username)
        response = await self._client.get(f"{base}/auth/login")
        if response.status_code != 200:
            logger.warning("Login page returned %d", response.status_code)

        response = await self._client.post(
            f"{base}/auth/process_login",
            data={"id": self._username, "pass": self._password},
        )

        if response.status_code != 200:
            raise RuntimeError(f"Login failed with status {response.status_code}")

        logger.info("Successfully logged in to YGG")
        self._logged_in = True

    async def search(self, query: SearchQuery) -> SearchResponse:
        client = await self._ensure_client()

        params: dict[str, str | int] = {
            "name": query.query,
            "do": "search",
        }

        if query.categories:
            ygg_subcats = torznab_cats_to_ygg_subcats(query.categories)
            if len(ygg_subcats) == 1:
                params["sub_category"] = ygg_subcats[0]

        if query.offset > 0:
            params["page"] = query.offset

        url = f"https://{self._domain}/engine/search"
        response = await client.get(url, params=params)

        if response.status_code == 302:
            logger.warning("Redirected during search, re-authenticating")
            self._logged_in = False
            client = await self._ensure_client()
            response = await client.get(url, params=params)

        if response.status_code != 200:
            raise RuntimeError(f"Search failed with status {response.status_code}")

        results, total = parse_search_results(response.text, self._domain)

        if query.limit < len(results):
            results = results[: query.limit]

        return SearchResponse(results=results, total=total, offset=query.offset)

    async def download_torrent(self, torrent_id: int) -> bytes:
        client = await self._ensure_client()
        url = f"https://{self._domain}/engine/download_torrent?id={torrent_id}"
        response = await client.get(url)

        if response.status_code != 200:
            raise RuntimeError(f"Download failed with status {response.status_code}")

        return response.content

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._logged_in = False
