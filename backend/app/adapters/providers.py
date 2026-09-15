"""Provider stubs for every capability that can receive document content.

STEP 1 ships stubs: the wiring, the policy and the tests are what must be right before
any of these does real work. Each one declares its locality, which is the only property
the egress policy reads — so a new provider cannot be added without stating whether
using it discloses content.
"""

from __future__ import annotations

from typing import Any

from app.domain.egress import Capability, Classified, Locality


class Provider:
    """Base. Subclasses are stubs until the step that implements them."""

    name: str
    locality: Locality
    capability: Capability
    lands_in_step: str = "a later step"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} {self.locality}/{self.capability}>"

    def _unimplemented(self) -> NotImplementedError:
        return NotImplementedError(f"{self.name} lands in {self.lands_in_step}")


# ── embeddings ────────────────────────────────────────────────────────────────
class VoyageEmbeddings(Provider):
    name = "voyage-3"
    locality = Locality.CLOUD
    capability = Capability.EMBEDDING
    lands_in_step = "STEP 3"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise self._unimplemented()


class LocalEmbeddings(Provider):
    name = "bge-m3"
    locality = Locality.LOCAL
    capability = Capability.EMBEDDING
    lands_in_step = "STEP 3"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise self._unimplemented()


# ── answering ─────────────────────────────────────────────────────────────────
class ClaudeLLM(Provider):
    name = "claude-opus-5"
    locality = Locality.CLOUD
    capability = Capability.LLM
    lands_in_step = "STEP 5"

    def answer(self, prompt: Classified[Any]) -> Any:
        raise self._unimplemented()


class LocalLLM(Provider):
    name = "local-llm"
    locality = Locality.LOCAL
    capability = Capability.LLM
    lands_in_step = "STEP 5 (only needed for a no-egress deployment)"

    def answer(self, prompt: Classified[Any]) -> Any:
        raise self._unimplemented()


# ── reranking ─────────────────────────────────────────────────────────────────
class LocalReranker(Provider):
    name = "bge-reranker-v2-m3"
    locality = Locality.LOCAL
    capability = Capability.RERANK
    lands_in_step = "STEP 4"

    def rerank(self, query: str, candidates: list[Classified[str]]) -> list[Any]:
        raise self._unimplemented()


class CloudReranker(Provider):
    """Not used by default. Present because the review asked what happens when someone
    adds one — the answer is that the policy covers it like any other sink."""

    name = "cloud-reranker"
    locality = Locality.CLOUD
    capability = Capability.RERANK
    lands_in_step = "not planned"

    def rerank(self, query: str, candidates: list[Classified[str]]) -> list[Any]:
        raise self._unimplemented()


# ── vision (screenshot description, §7.2) ─────────────────────────────────────
class ClaudeVision(Provider):
    name = "claude-vision"
    locality = Locality.CLOUD
    capability = Capability.VISION
    lands_in_step = "STEP 7"

    def describe(self, image: Classified[bytes]) -> str:
        raise self._unimplemented()


class LocalVision(Provider):
    name = "local-vlm"
    locality = Locality.LOCAL
    capability = Capability.VISION
    lands_in_step = "STEP 7 (only needed for a no-egress deployment)"

    def describe(self, image: Classified[bytes]) -> str:
        raise self._unimplemented()


# ── OCR ───────────────────────────────────────────────────────────────────────
class TesseractOcr(Provider):
    name = "tesseract"
    locality = Locality.LOCAL
    capability = Capability.OCR
    lands_in_step = "STEP 3"

    def ocr_page(self, image: Classified[bytes]) -> str:
        raise self._unimplemented()


class CloudOcr(Provider):
    name = "cloud-ocr"
    locality = Locality.CLOUD
    capability = Capability.OCR
    lands_in_step = "not planned"

    def ocr_page(self, image: Classified[bytes]) -> str:
        raise self._unimplemented()


REGISTRY: dict[str, type[Provider]] = {
    "voyage": VoyageEmbeddings,
    "local_embeddings": LocalEmbeddings,
    "claude": ClaudeLLM,
    "local_llm": LocalLLM,
    "local_reranker": LocalReranker,
    "cloud_reranker": CloudReranker,
    "claude_vision": ClaudeVision,
    "local_vision": LocalVision,
    "tesseract": TesseractOcr,
    "cloud_ocr": CloudOcr,
}
