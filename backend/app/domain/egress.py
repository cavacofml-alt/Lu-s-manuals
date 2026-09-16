"""Document data egress policy.

See docs/ARCHITECTURE.md §8.1.1.

This module was originally scoped to embeddings. The architecture review was right that
the scope was wrong: the property we actually want is not "embeddings stay local" but
"document content does not leave the network unless policy permits it", and document
content reaches *many* providers — the answering model, the reranker, the vision model
that describes screenshots, OCR, and any future translation or summarisation step.

Naming it `EmbeddingPolicy` would have guaranteed that the next provider added would not
be covered by it.

Three mechanisms, at three different strengths. Do not confuse them — the third review
challenged exactly this, and was right to:

1. `EgressPolicy` decides, per classification, which localities may receive content.
2. `Classified[T]` is a **type contract**. It carries the classification with the
   content and makes an unclassified call site visible to a reader and to mypy. It is
   not a runtime barrier and cannot stop a direct call to an adapter.
3. `Released[T]` is the **runtime barrier**. A provider's public API accepts only a
   `Released`, and it cannot be constructed without a sentinel held privately by
   `EgressGuard`. That is what makes the guard unavoidable rather than customary.

What this does not do: prevent someone calling a provider's private `_process`, forging
an object through `__new__`, or monkeypatching the policy. A closed public API is the
limit of what is achievable in-process. The real guarantee for a confidential deployment
is having no cloud credentials and no outbound route — see docs/ARCHITECTURE.md §8.1.2.
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

    # Reserved (§8.1.3). No cloud implementation is planned for either, but reserving
    # them means such a provider cannot be added without declaring a locality and
    # falling under the policy.
    DOCUMENT_PROCESSING = "document_processing"  # cloud parsing / layout / tables
    STORAGE = "storage"  # an S3 bucket is egress even though no model sees it


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

    NOTE: this type is a *contract*, not a runtime barrier. It makes the classification
    travel with the content and makes an unclassified call site visible to a reader and
    to mypy. It cannot stop anyone calling an adapter directly. `Released` below is what
    provides the runtime enforcement.
    """

    value: T
    classification: Classification

    def unwrap_unchecked(self, reason: str) -> T:
        """Escape hatch, deliberately conspicuous.

        Legitimate uses are paths where no egress occurs: writing to our own database,
        rendering a PDF locally, returning content to an already-authorised user. It
        requires a reason so the justification sits at the call site, and CI greps for
        it so each use is a review decision rather than a habit.

        It is a convention, not a control. The control is that `Released` cannot be
        constructed here, so unwrapping does not produce something an adapter accepts.
        """
        if not reason:
            raise ValueError("unwrap_unchecked requires a stated reason")
        return self.value


_GUARD_ONLY = object()
"""Sentinel proving a `Released` was constructed by the guard and not by a caller."""


@dataclass(frozen=True)
class Released(Generic[T]):
    """Content the policy has cleared for one specific provider.

    This is the runtime barrier. A provider's public API accepts only `Released`, and
    `Released` cannot be constructed without the sentinel held privately by
    `EgressGuard`. A developer calling an adapter directly with a raw string, or with a
    `Classified`, or with a hand-built `Released`, is refused at runtime — not by a type
    checker, and not by review.

    `provider_name` records which provider the clearance was issued for, so a clearance
    obtained for a local provider cannot be replayed against a cloud one.
    """

    value: T
    classification: Classification
    provider_name: str

    def __init__(
        self,
        value: T,
        classification: Classification,
        provider_name: str,
        _key: object = None,
    ) -> None:
        if _key is not _GUARD_ONLY:
            raise EgressViolation(
                "Released may only be constructed by EgressGuard.release(). "
                "Content reaches a provider through the guard or not at all."
            )
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "classification", classification)
        object.__setattr__(self, "provider_name", provider_name)
