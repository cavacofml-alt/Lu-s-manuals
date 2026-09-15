"""Data classification and the policy governing which providers may see a document.

See docs/ARCHITECTURE.md §8.1.1. The rule this module exists to enforce: a document
must never reach a cloud provider merely because that provider is configured. Every
routing decision passes through `EmbeddingPolicy.provider_for`, and the default
answer is no.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    HIGHLY_CONFIDENTIAL = "highly_confidential"


class Locality(StrEnum):
    """Where a provider runs, and therefore whether using it discloses content."""

    CLOUD = "cloud"
    LOCAL = "local"


class PolicyMode(StrEnum):
    STRICT_LOCAL = "strict_local"
    MIXED = "mixed"
    PERMISSIVE = "permissive"


class PolicyViolation(Exception):
    """Raised when no configured provider may handle a document's classification."""


DEFAULT_MATRIX: dict[Classification, frozenset[Locality]] = {
    Classification.PUBLIC: frozenset({Locality.CLOUD, Locality.LOCAL}),
    Classification.INTERNAL: frozenset({Locality.CLOUD, Locality.LOCAL}),
    Classification.CONFIDENTIAL: frozenset({Locality.LOCAL}),
    Classification.HIGHLY_CONFIDENTIAL: frozenset({Locality.LOCAL}),
}


@dataclass(frozen=True)
class EmbeddingPolicy:
    mode: PolicyMode = PolicyMode.MIXED
    matrix: dict[Classification, frozenset[Locality]] | None = None

    def allowed(self, classification: Classification) -> frozenset[Locality]:
        if self.mode is PolicyMode.STRICT_LOCAL:
            return frozenset({Locality.LOCAL})
        # `is None`, not truthiness: an explicitly empty matrix must deny everything,
        # not silently fall back to the permissive default.
        matrix = DEFAULT_MATRIX if self.matrix is None else self.matrix
        if self.mode is PolicyMode.PERMISSIVE:
            # Permissive widens `internal`; it never widens confidential tiers.
            widened = dict(matrix)
            widened[Classification.INTERNAL] = frozenset({Locality.CLOUD, Locality.LOCAL})
            return widened.get(classification, frozenset({Locality.LOCAL}))
        # An unlisted classification is treated as the most restrictive, not the most
        # permissive: a gap in configuration must fail closed.
        return matrix.get(classification, frozenset({Locality.LOCAL}))

    def permits(self, classification: Classification, locality: Locality) -> bool:
        return locality in self.allowed(classification)

    def provider_for(
        self,
        classification: Classification,
        available: dict[Locality, object],
    ) -> object:
        """Resolve a provider from the document's classification.

        `available` maps locality to a constructed provider. There is deliberately no
        fallback to a global default: if the policy permits nothing that is configured,
        this raises rather than choosing something.
        """
        for locality in self.allowed(classification):
            provider = available.get(locality)
            if provider is not None:
                return provider
        raise PolicyViolation(
            f"No configured provider may process a {classification!s} document "
            f"(policy allows {sorted(self.allowed(classification))}, "
            f"configured: {sorted(available)})"
        )
