import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ygg_torznab.adapters.cloudflare.cf_clearance import CfClearanceAdapter
from ygg_torznab.adapters.torznab.router import router
from ygg_torznab.adapters.ygg.client import YggClient
from ygg_torznab.config import Settings

_settings: Settings | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = _get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cf_adapter = CfClearanceAdapter(settings)
    ygg_client = YggClient(settings, cf_adapter)

    app.state.settings = settings
    app.state.ygg_client = ygg_client

    log = logging.getLogger(__name__)
    if not settings.api_key:
        log.warning("API_KEY is not set — API is accessible without authentication")
    log.info("ygg-torznab starting on port %d", settings.port)
    cf_adapter.start()
    yield

    cf_adapter.stop()
    await ygg_client.close()


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
    ygg_client: YggClient = request.app.state.ygg_client
    if ygg_client.is_healthy:
        return {"status": "ok"}
    return {"status": "degraded", "reason": "not authenticated"}


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
