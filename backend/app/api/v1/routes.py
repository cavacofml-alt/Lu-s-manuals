from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.session import installed_extensions

router = APIRouter()

REQUIRED_EXTENSIONS = ("vector", "pg_trgm")


@router.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    database: dict[str, Any] = {"connected": False, "extensions": [], "missing": []}
    try:
        present = installed_extensions()
        database = {
            "connected": True,
            "extensions": present,
            "missing": [e for e in REQUIRED_EXTENSIONS if e not in present],
        }
    except SQLAlchemyError as exc:
        database["error"] = type(exc).__name__

    return {
        "status": "ok" if database["connected"] and not database["missing"] else "degraded",
        "database": database,
        "config": {
            "egress_policy_mode": settings.egress_policy_mode,
            "handles_classification": settings.handles_classification,
            "embedding_provider": settings.embedding_provider,
            "llm_provider": settings.llm_provider,
            "vision_provider": settings.vision_provider,
            "pdf_processor": settings.pdf_processor,
        },
    }


@router.get("/releases")
def list_releases() -> list[dict[str, Any]]:
    """Empty until STEP 2 creates the schema — one real path end-to-end."""
    return []
