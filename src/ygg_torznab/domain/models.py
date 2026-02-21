from datetime import datetime

from pydantic import BaseModel


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
    season: int | None = None
    episode: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    limit: int = 50
    offset: int = 0


class SearchResponse(BaseModel):
    results: list[TorrentResult]
    total: int
    offset: int
