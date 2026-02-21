from datetime import datetime

from pydantic import BaseModel

_DEFAULT_RATE_LIMIT_WAIT = 30.0


class RateLimitError(Exception):
    """Raised when YGG returns 429 Too Many Requests."""

    def __init__(self, retry_after: float = _DEFAULT_RATE_LIMIT_WAIT) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


class TorrentResult(BaseModel):
    torrent_id: int
    title: str
    detail_url: str
    category_id: int
    size_bytes: int
    seeders: int
    leechers: int
    grabs: int
    publish_date: datetime
    comments: int
    download_url: str


class SearchQuery(BaseModel):
    query: str = ""
    categories: list[int] = []
    limit: int = 50
    offset: int = 0


class SearchResponse(BaseModel):
    results: list[TorrentResult]
    total: int
    offset: int
