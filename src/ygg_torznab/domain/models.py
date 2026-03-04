from datetime import datetime

from pydantic import BaseModel


class TorrentResult(BaseModel):
    infohash: str
    title: str
    category_id: int
    size_bytes: int
    seeders: int
    leechers: int
    grabs: int
    publish_date: datetime
    magnet_uri: str
    has_ygg_tag: bool = False


class SearchQuery(BaseModel):
    query: str = ""
    categories: list[int] = []
    limit: int = 50
    until: int | None = None


class SearchResponse(BaseModel):
    results: list[TorrentResult]
    total: int
    offset: int = 0
