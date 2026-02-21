"""Port interfaces — used for type hints and test mocking."""

from typing import Protocol

from ygg_torznab.domain.models import SearchQuery, SearchResponse


class CloudflareBypassPort(Protocol):
    async def get_cookies(self, url: str = "") -> dict[str, str]: ...

    async def get_headers(self, url: str = "") -> dict[str, str]: ...


class YggSearchPort(Protocol):
    @property
    def is_healthy(self) -> bool: ...

    async def search(self, query: SearchQuery) -> SearchResponse: ...

    async def download_torrent(self, torrent_id: int) -> bytes: ...

    async def close(self) -> None: ...
