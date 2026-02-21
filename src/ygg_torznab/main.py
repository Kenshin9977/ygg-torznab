import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from ygg_torznab.adapters.cloudflare.cf_clearance import CfClearanceAdapter
from ygg_torznab.adapters.torznab.router import router
from ygg_torznab.adapters.ygg.client import YggClient
from ygg_torznab.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()  # type: ignore[call-arg]

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cf_adapter = CfClearanceAdapter(settings)
    ygg_client = YggClient(settings, cf_adapter)

    app.state.settings = settings
    app.state.ygg_client = ygg_client

    logging.getLogger(__name__).info("ygg-torznab starting on port %d", settings.port)
    yield

    await ygg_client.close()


app = FastAPI(title="ygg-torznab", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(
        "ygg_torznab.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
