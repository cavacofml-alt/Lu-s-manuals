from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.factory import EmbeddingRouter, build_embedding_providers
from app.api.v1.routes import health
from app.api.v1.routes import router as v1_router
from app.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    router = EmbeddingRouter(settings.embedding_policy, build_embedding_providers(settings))
    router.validate_startup(settings.handles_classification)
    app.state.embedding_router = router
    logger.info(
        "started: embedding=%s policy=%s pdf=%s",
        settings.embedding_provider,
        settings.embedding_policy_mode,
        settings.pdf_processor,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(v1_router, prefix="/api/v1")
    app.add_api_route("/health", health, methods=["GET"])  # unprefixed, for probes
    return app


app = create_app()
