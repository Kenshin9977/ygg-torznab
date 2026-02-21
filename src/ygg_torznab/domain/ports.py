from typing import Protocol

import httpx

from ygg_torznab.domain.models import SearchQuery, SearchResponse


class CloudflareBypassPort(Protocol):
    async def get_cookies(self, url: str) -> dict[str, str]: ...

    async def get_headers(self, url: str) -> dict[str, str]: ...


class YggAuthPort(Protocol):
    async def login(self) -> httpx.AsyncClient: ...

    async def get_client(self) -> httpx.AsyncClient: ...


class YggSearchPort(Protocol):
    async def search(self, query: SearchQuery) -> SearchResponse: ...

    async def download_torrent(self, torrent_id: int) -> bytes: ...
