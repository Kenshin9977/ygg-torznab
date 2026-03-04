import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ygg_torznab.adapters.nostr.client import NostrClient
from ygg_torznab.adapters.torznab.router import router
from ygg_torznab.config import Settings

_settings: Settings | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = _get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    nostr_client = NostrClient(settings)

    app.state.settings = settings
    app.state.nostr_client = nostr_client

    log = logging.getLogger(__name__)
    if not settings.api_key:
        log.warning("API_KEY is not set — API is accessible without authentication")
    log.info(
        "ygg-torznab starting on port %d (relay: %s)", settings.port, settings.nostr_relay
    )

    # Pre-connect to the relay so the first search doesn't timeout
    try:
        await nostr_client._ensure_connection()
        log.info("Pre-connected to Nostr relay")
    except Exception:
        log.warning("Could not pre-connect to relay, will retry on first search")

    yield

    await nostr_client.close()


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response


app = FastAPI(title="ygg-torznab", lifespan=lifespan)
app.add_middleware(_SecurityHeadersMiddleware)
app.include_router(router)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    nostr_client: NostrClient = request.app.state.nostr_client

    if not nostr_client.is_healthy:
        return {"status": "degraded", "reason": "relay connection not established"}
    return {"status": "ok"}


def main() -> None:
    settings = _get_settings()
    uvicorn.run(
        "ygg_torznab.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
