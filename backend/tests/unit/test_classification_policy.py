"""The policy from docs/ARCHITECTURE.md §8.1.1.

These tests encode a security property, not a preference: no configuration may route a
confidential document to a cloud provider.
"""

from __future__ import annotations

import pytest

from app.adapters.embeddings import LocalEmbeddingProvider, VoyageEmbeddingProvider
from app.adapters.factory import EmbeddingRouter
from app.domain.classification import (
    Classification,
    EmbeddingPolicy,
    Locality,
    PolicyMode,
    PolicyViolation,
)

CLOUD = VoyageEmbeddingProvider()
LOCAL = LocalEmbeddingProvider()
BOTH = {Locality.CLOUD: CLOUD, Locality.LOCAL: LOCAL}


@pytest.mark.parametrize("mode", list(PolicyMode))
@pytest.mark.parametrize(
    "classification",
    [Classification.CONFIDENTIAL, Classification.HIGHLY_CONFIDENTIAL],
)
def test_confidential_never_reaches_cloud(mode: PolicyMode, classification: Classification) -> None:
    """Under every mode, with both providers available, confidential stays local."""
    policy = EmbeddingPolicy(mode=mode)
    assert not policy.permits(classification, Locality.CLOUD)
    assert EmbeddingRouter(policy, BOTH).for_document(classification) is LOCAL


def test_confidential_with_only_cloud_configured_raises_rather_than_falling_back() -> None:
    policy = EmbeddingPolicy(mode=PolicyMode.MIXED)
    router = EmbeddingRouter(policy, {Locality.CLOUD: CLOUD})
    with pytest.raises(PolicyViolation):
        router.for_document(Classification.CONFIDENTIAL)


def test_strict_local_forces_local_even_for_public() -> None:
    policy = EmbeddingPolicy(mode=PolicyMode.STRICT_LOCAL)
    assert policy.allowed(Classification.PUBLIC) == frozenset({Locality.LOCAL})
    with pytest.raises(PolicyViolation):
        EmbeddingRouter(policy, {Locality.CLOUD: CLOUD}).for_document(Classification.PUBLIC)


def test_unknown_classification_fails_closed() -> None:
    """A gap in the matrix must deny, not permit."""
    policy = EmbeddingPolicy(mode=PolicyMode.MIXED, matrix={})
    assert policy.allowed(Classification.INTERNAL) == frozenset({Locality.LOCAL})


def test_public_may_use_cloud() -> None:
    policy = EmbeddingPolicy(mode=PolicyMode.MIXED)
    assert EmbeddingRouter(policy, BOTH).for_document(Classification.PUBLIC) is CLOUD


def test_cloud_only_deployment_cannot_claim_to_handle_confidential() -> None:
    router = EmbeddingRouter(EmbeddingPolicy(mode=PolicyMode.MIXED), {Locality.CLOUD: CLOUD})
    with pytest.raises(RuntimeError, match="handles_classification"):
        router.validate_startup(Classification.CONFIDENTIAL)


def test_cloud_only_deployment_may_declare_a_lower_ceiling() -> None:
    """Explicitly stating "this installation holds nothing above internal" is allowed."""
    router = EmbeddingRouter(EmbeddingPolicy(mode=PolicyMode.MIXED), {Locality.CLOUD: CLOUD})
    router.validate_startup(Classification.INTERNAL)


def test_strict_local_rejects_cloud_provider_at_startup() -> None:
    router = EmbeddingRouter(EmbeddingPolicy(mode=PolicyMode.STRICT_LOCAL), {Locality.CLOUD: CLOUD})
    with pytest.raises(RuntimeError):
        router.validate_startup(Classification.PUBLIC)


def test_startup_validation_accepts_local_deployment() -> None:
    router = EmbeddingRouter(EmbeddingPolicy(mode=PolicyMode.STRICT_LOCAL), {Locality.LOCAL: LOCAL})
    router.validate_startup(Classification.HIGHLY_CONFIDENTIAL)
