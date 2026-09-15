"""Provider interfaces (docs/ARCHITECTURE.md §2.3).

These are fixed in STEP 1, before anything depends on them, so that later steps
implement against a stable contract rather than negotiating one mid-flight.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO, Protocol, runtime_checkable

from app.domain.egress import Locality

Vector = list[float]


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_id: str
    dimensions: int
    locality: Locality

    async def embed_documents(self, texts: list[str]) -> list[Vector]: ...
    async def embed_query(self, text: str) -> Vector: ...


@runtime_checkable
class LLMProvider(Protocol):
    model_id: str
    locality: Locality

    async def answer(self, prompt: Any) -> Any: ...


@runtime_checkable
class Reranker(Protocol):
    async def rerank(self, query: str, candidates: list[Any]) -> list[Any]: ...


@runtime_checkable
class DocumentProcessor(Protocol):
    def supports(self, mime_type: str) -> bool: ...
    def process(self, path: Path) -> Any: ...


@runtime_checkable
class OcrEngine(Protocol):
    def ocr_page(self, image: Any) -> Any: ...


@runtime_checkable
class StorageProvider(Protocol):
    def put(self, key: str, data: BinaryIO) -> str: ...
    def open(self, ref: str) -> BinaryIO: ...


@runtime_checkable
class AnswerRenderer(Protocol):
    def render(self, answer: Any) -> bytes: ...
