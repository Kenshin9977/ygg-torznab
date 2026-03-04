"""FastAPI router implementing the Torznab API."""

import hmac
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from ygg_torznab.adapters.nostr.magnet import build_magnet_uri
from ygg_torznab.adapters.torznab.xml_builder import (
    build_caps_xml,
    build_error_xml,
    build_search_xml,
)
from ygg_torznab.domain.models import SearchQuery

_MAX_LIMIT = 500

if TYPE_CHECKING:
    from ygg_torznab.adapters.nostr.client import NostrClient
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
    t: str = Query("", max_length=20, description="Torznab function"),
    q: str = Query("", max_length=200, description="Search query"),
    cat: str = Query("", max_length=100, description="Comma-separated category IDs"),
    limit: int = Query(50, ge=0, le=_MAX_LIMIT, description="Max results (0=default)"),
    offset: int = Query(0, ge=0, description="Result offset"),
    apikey: str = Query("", max_length=256, description="API key"),
    id: str | None = Query(None, max_length=40, description="Infohash for magnet link"),
) -> Response:
    settings: Settings = request.app.state.settings
    nostr_client: NostrClient = request.app.state.nostr_client

    if t == "caps":
        return _xml_response(build_caps_xml())

    if settings.api_key and not hmac.compare_digest(apikey, settings.api_key):
        return _xml_response(build_error_xml(100, "Incorrect API key"), 401)

    api_url = _get_api_url(request)

    if t in ("search", "tvsearch", "movie"):
        return await _handle_search(nostr_client, q, cat, limit, api_url)

    if t == "download":
        return _handle_download(id)

    return _xml_response(build_error_xml(202, f"Unknown function: {t}"), 400)


async def _handle_search(
    nostr_client: "NostrClient",
    q: str,
    cat: str,
    limit: int,
    api_url: str,
) -> Response:
    categories = [int(c) for c in cat.split(",") if c.strip().isdigit()]
    effective_limit = limit if limit > 0 else 50
    search_query = SearchQuery(
        query=q,
        categories=categories,
        limit=effective_limit,
    )

    try:
        search_response = await nostr_client.search(search_query)
    except Exception:
        logger.exception("Search failed")
        return _xml_response(build_error_xml(900, "Search failed"), 500)

    return _xml_response(build_search_xml(search_response, api_url))


def _handle_download(infohash: str | None) -> Response:
    if not infohash or len(infohash) != 40:
        return _xml_response(build_error_xml(200, "Missing or invalid infohash"), 400)
    magnet = build_magnet_uri(infohash, "", include_ygg_extra=True)
    return RedirectResponse(url=magnet, status_code=302)
