"""Provider stubs for every capability that can receive document content.

STEP 1 ships stubs: the wiring, the policy and the tests are what must be right before
any of these does real work. Each one declares its locality, which is the only property
the egress policy reads — so a new provider cannot be added without stating whether
using it discloses content.
"""

from __future__ import annotations

from typing import Any

from app.domain.egress import Capability, EgressViolation, Locality, Released


class Provider:
    """Base. Subclasses are stubs until the step that implements them.

    The public entry point is `submit`, and it accepts only a `Released` — an object
    that only `EgressGuard.release` can construct. This is what makes the guard
    unavoidable at runtime: a direct call with a raw string, a `Classified`, or a
    hand-built `Released` is refused here, before any provider code runs.

    Subclasses implement `_process`, which is private. Calling `_process` directly still
    works, as it must in Python — but that is a deliberate act against a named private
    method, not an ordinary call to a public API. See docs/ARCHITECTURE.md §8.1.2 for
    what this does and does not guarantee.
    """

    name: str
    locality: Locality
    capability: Capability
    lands_in_step: str = "a later step"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} {self.locality}/{self.capability}>"

    def submit(self, released: Released[Any]) -> Any:
        """The only public way to hand content to a provider."""
        if not isinstance(released, Released):
            raise EgressViolation(
                f"{self.name} accepts only content cleared by EgressGuard.release(). "
                f"Got {type(released).__name__}. Route it through the guard."
            )
        if released.provider_name != self.name:
            raise EgressViolation(
                f"Clearance was issued for {released.provider_name!r}, not {self.name!r}. "
                "A clearance for one provider cannot be replayed against another."
            )
        return self._process(released.value)

    def _process(self, payload: Any) -> Any:
        raise NotImplementedError(f"{self.name} lands in {self.lands_in_step}")


# ── embeddings ────────────────────────────────────────────────────────────────
class VoyageEmbeddings(Provider):
    name = "voyage-3"
    locality = Locality.CLOUD
    capability = Capability.EMBEDDING
    lands_in_step = "STEP 3"


class LocalEmbeddings(Provider):
    name = "bge-m3"
    locality = Locality.LOCAL
    capability = Capability.EMBEDDING
    lands_in_step = "STEP 3"


# ── answering ─────────────────────────────────────────────────────────────────
class ClaudeLLM(Provider):
    name = "claude-opus-5"
    locality = Locality.CLOUD
    capability = Capability.LLM
    lands_in_step = "STEP 5"


class LocalLLM(Provider):
    name = "local-llm"
    locality = Locality.LOCAL
    capability = Capability.LLM
    lands_in_step = "STEP 5 (only needed for a no-egress deployment)"


# ── reranking ─────────────────────────────────────────────────────────────────
class LocalReranker(Provider):
    name = "bge-reranker-v2-m3"
    locality = Locality.LOCAL
    capability = Capability.RERANK
    lands_in_step = "STEP 4"


class CloudReranker(Provider):
    """Not used by default. Present because the review asked what happens when someone
    adds one — the answer is that the policy covers it like any other sink."""

    name = "cloud-reranker"
    locality = Locality.CLOUD
    capability = Capability.RERANK
    lands_in_step = "not planned"


# ── vision (screenshot description, §7.2) ─────────────────────────────────────
class ClaudeVision(Provider):
    name = "claude-vision"
    locality = Locality.CLOUD
    capability = Capability.VISION
    lands_in_step = "STEP 7"


class LocalVision(Provider):
    name = "local-vlm"
    locality = Locality.LOCAL
    capability = Capability.VISION
    lands_in_step = "STEP 7 (only needed for a no-egress deployment)"


# ── OCR ───────────────────────────────────────────────────────────────────────
class TesseractOcr(Provider):
    name = "tesseract"
    locality = Locality.LOCAL
    capability = Capability.OCR
    lands_in_step = "STEP 3"


class CloudOcr(Provider):
    name = "cloud-ocr"
    locality = Locality.CLOUD
    capability = Capability.OCR
    lands_in_step = "not planned"


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
