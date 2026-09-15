"""Document data egress policy.

See docs/ARCHITECTURE.md §8.1.1.

This module was originally scoped to embeddings. The architecture review was right that
the scope was wrong: the property we actually want is not "embeddings stay local" but
"document content does not leave the network unless policy permits it", and document
content reaches *many* providers — the answering model, the reranker, the vision model
that describes screenshots, OCR, and any future translation or summarisation step.

Naming it `EmbeddingPolicy` would have guaranteed that the next provider added would not
be covered by it.

Two mechanisms, because a policy that must be *remembered* is not a control:

1. `EgressPolicy` decides, per classification, which localities may receive content.
2. `Classified[T]` makes document content un-passable to a provider without going
   through that decision. A provider cannot receive a bare `str` of document text; it
   receives a `Classified[str]` that only `EgressGuard.release` can open.

Bypassing this requires calling `unwrap_unchecked`, which names itself, demands a
reason, and is greppable in review and in CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    HIGHLY_CONFIDENTIAL = "highly_confidential"


class Locality(StrEnum):
    """Where a provider runs, and therefore whether sending it content discloses it."""

    CLOUD = "cloud"
    LOCAL = "local"


class Capability(StrEnum):
    """Every provider role that can receive document content.

    Adding a member here without a corresponding provider is harmless. Adding a provider
    that receives content *without* adding it here is the mistake this enum exists to
    make visible — `ContentSink` requires a capability, so a new provider cannot be
    wired in without declaring one.
    """

    EMBEDDING = "embedding"
    LLM = "llm"
    RERANK = "rerank"
    VISION = "vision"
    OCR = "ocr"
    TRANSLATION = "translation"
    SUMMARISATION = "summarisation"


REQUIRED_CAPABILITIES = frozenset({Capability.EMBEDDING, Capability.LLM})
"""Without these the system cannot index or answer; startup validates them."""


class PolicyMode(StrEnum):
    STRICT_LOCAL = "strict_local"
    MIXED = "mixed"
    PERMISSIVE = "permissive"


class EgressViolation(Exception):
    """Raised when policy forbids sending content to a provider."""


@runtime_checkable
class ContentSink(Protocol):
    """Anything that can receive document content. Every provider is one."""

    name: str
    locality: Locality
    capability: Capability


DEFAULT_MATRIX: dict[Classification, frozenset[Locality]] = {
    Classification.PUBLIC: frozenset({Locality.CLOUD, Locality.LOCAL}),
    Classification.INTERNAL: frozenset({Locality.CLOUD, Locality.LOCAL}),
    Classification.CONFIDENTIAL: frozenset({Locality.LOCAL}),
    Classification.HIGHLY_CONFIDENTIAL: frozenset({Locality.LOCAL}),
}


@dataclass(frozen=True)
class EgressPolicy:
    mode: PolicyMode = PolicyMode.MIXED
    matrix: dict[Classification, frozenset[Locality]] | None = None

    def allowed(self, classification: Classification) -> frozenset[Locality]:
        if self.mode is PolicyMode.STRICT_LOCAL:
            return frozenset({Locality.LOCAL})
        # `is None`, not truthiness: an explicitly empty matrix must deny everything
        # rather than silently reverting to the permissive default.
        matrix = DEFAULT_MATRIX if self.matrix is None else self.matrix
        if self.mode is PolicyMode.PERMISSIVE:
            widened = dict(matrix)
            widened[Classification.INTERNAL] = frozenset({Locality.CLOUD, Locality.LOCAL})
            return widened.get(classification, frozenset({Locality.LOCAL}))
        # An unlisted classification is treated as the most restrictive: a gap in
        # configuration must fail closed.
        return matrix.get(classification, frozenset({Locality.LOCAL}))

    def permits(self, classification: Classification, locality: Locality) -> bool:
        return locality in self.allowed(classification)


@dataclass(frozen=True)
class Classified(Generic[T]):
    """Document content tagged with its classification.

    Adapters take this rather than a bare value, so the question "may this provider see
    this?" cannot be skipped by forgetting to ask it.
    """

    value: T
    classification: Classification

    def unwrap_unchecked(self, reason: str) -> T:
        """Escape hatch, deliberately conspicuous.

        Legitimate uses are paths where no egress occurs: writing to our own database,
        rendering a PDF locally, returning content to an already-authorised user. It
        requires a reason so the justification sits at the call site, and CI greps for
        it so each use is a review decision rather than a habit.
        """
        if not reason:
            raise ValueError("unwrap_unchecked requires a stated reason")
        return self.value
