"""FastAPI router implementing the Torznab API."""

import hmac
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, Request, Response

from ygg_torznab.adapters.torznab.xml_builder import (
    build_caps_xml,
    build_error_xml,
    build_search_xml,
)
from ygg_torznab.adapters.ygg.client import RateLimitError
from ygg_torznab.domain.models import SearchQuery

_MAX_LIMIT = 500

if TYPE_CHECKING:
    from ygg_torznab.adapters.ygg.client import YggClient
    from ygg_torznab.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter()

XML_CONTENT_TYPE = "application/xml; charset=utf-8"


def _xml_response(content: str, status_code: int = 200) -> Response:
    return Response(content=content, media_type=XML_CONTENT_TYPE, status_code=status_code)


def _get_api_url(request: Request) -> str:
    return str(request.url_for("torznab_api"))


@router.get("/api", name="torznab_api")
async def torznab_api(
    request: Request,
    t: str = Query("", description="Torznab function"),
    q: str = Query("", description="Search query"),
    cat: str = Query("", description="Comma-separated category IDs"),
    season: int | None = Query(None, description="Season number"),
    ep: int | None = Query(None, description="Episode number"),
    imdbid: str | None = Query(None, description="IMDB ID"),
    tvdbid: int | None = Query(None, description="TVDB ID"),
    limit: int = Query(50, description="Max results"),
    offset: int = Query(0, description="Result offset"),
    apikey: str = Query("", description="API key"),
    id: int | None = Query(None, description="Torrent ID for download"),
) -> Response:
    settings: Settings = request.app.state.settings
    ygg_client: YggClient = request.app.state.ygg_client

    if settings.api_key and not hmac.compare_digest(apikey, settings.api_key):
        return _xml_response(build_error_xml(100, "Incorrect API key"), 401)

    api_url = _get_api_url(request)

    if t == "caps":
        return _xml_response(build_caps_xml(api_url))

    if t in ("search", "tvsearch", "movie"):
        categories = [int(c) for c in cat.split(",") if c.strip().isdigit()]
        clamped_limit = max(1, min(limit, _MAX_LIMIT))
        clamped_offset = max(0, offset)
        search_query = SearchQuery(
            query=q,
            categories=categories,
            season=season,
            episode=ep,
            imdb_id=imdbid,
            tvdb_id=tvdbid,
            limit=clamped_limit,
            offset=clamped_offset,
        )

        try:
            search_response = await ygg_client.search(search_query)
        except RateLimitError as e:
            logger.warning("Rate limited by YGG: %s", e)
            return _xml_response(
                build_error_xml(900, f"Rate limited, retry after {e.retry_after:.0f}s"),
                429,
            )
        except Exception:
            logger.exception("Search failed")
            return _xml_response(build_error_xml(900, "Search failed"), 500)

        return _xml_response(build_search_xml(search_response, api_url))

    if t == "download":
        if id is None:
            return _xml_response(build_error_xml(200, "Missing torrent ID"), 400)

        try:
            torrent_data = await ygg_client.download_torrent(id)
        except RateLimitError as e:
            logger.warning("Rate limited by YGG on download: %s", e)
            return _xml_response(
                build_error_xml(900, f"Rate limited, retry after {e.retry_after:.0f}s"),
                429,
            )
        except Exception:
            logger.exception("Download failed for torrent %d", id)
            return _xml_response(build_error_xml(900, "Download failed"), 500)

        return Response(
            content=torrent_data,
            media_type="application/x-bittorrent",
            headers={"Content-Disposition": f"attachment; filename={id}.torrent"},
        )

    return _xml_response(build_error_xml(202, f"Unknown function: {t}"), 400)
