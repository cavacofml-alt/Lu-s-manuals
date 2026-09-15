"""Embedding providers.

STEP 1 ships stubs only: the point is that the wiring, the policy and the startup
validation are correct and tested before either provider does real work.
"""

from __future__ import annotations

from app.adapters.ports import Vector
from app.domain.classification import Locality


class NotImplementedProvider:
    """Base for STEP 1 stubs — present, constructible, and honest about doing nothing."""

    model_id: str
    dimensions: int
    locality: Locality

    async def embed_documents(self, texts: list[str]) -> list[Vector]:
        raise NotImplementedError(f"{type(self).__name__} lands in STEP 3")

    async def embed_query(self, text: str) -> Vector:
        raise NotImplementedError(f"{type(self).__name__} lands in STEP 3")


class VoyageEmbeddingProvider(NotImplementedProvider):
    """Hosted provider. Using this discloses chunk text to a third party (§8.1)."""

    locality = Locality.CLOUD

    def __init__(self, model_id: str = "voyage-3", dimensions: int = 1024) -> None:
        self.model_id = model_id
        self.dimensions = dimensions


class LocalEmbeddingProvider(NotImplementedProvider):
    """Self-hosted provider. No content leaves the network."""

    locality = Locality.LOCAL

    def __init__(self, model_id: str = "bge-m3", dimensions: int = 1024) -> None:
        self.model_id = model_id
        self.dimensions = dimensions
