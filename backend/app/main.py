from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.factory import build_providers
from app.api.v1.routes import health
from app.api.v1.routes import router as v1_router
from app.config import get_settings
from app.services.egress_guard import EgressGuard

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    guard = EgressGuard(settings.egress_policy, build_providers(settings))
    guard.validate_startup(settings.handles_classification)
    app.state.egress_guard = guard
    logger.info(
        "started: policy=%s handles=%s embedding=%s llm=%s",
        settings.egress_policy_mode,
        settings.handles_classification,
        settings.embedding_provider,
        settings.llm_provider,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(v1_router, prefix="/api/v1")
    app.add_api_route("/health", health, methods=["GET"])  # unprefixed, for probes
    return app


app = create_app()
