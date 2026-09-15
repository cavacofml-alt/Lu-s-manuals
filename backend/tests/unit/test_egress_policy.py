"""Egress policy — the security property, stated as tests.

docs/ARCHITECTURE.md §8.1.1. The claim under test is:

    Document content classified `confidential` or above never reaches a cloud provider,
    through ANY capability, under ANY configuration.

The architecture review was right that asserting "there is no code path" proves nothing.
These tests are the closest thing to a proof available: they enumerate every capability
that can receive content, every policy mode, and the bypass routes.
"""

from __future__ import annotations

import pytest

from app.adapters.factory import build_providers
from app.adapters.providers import (
    ClaudeLLM,
    ClaudeVision,
    CloudOcr,
    CloudReranker,
    LocalEmbeddings,
    LocalLLM,
    LocalReranker,
    LocalVision,
    TesseractOcr,
    VoyageEmbeddings,
)
from app.config import Settings
from app.domain.egress import (
    Capability,
    Classification,
    Classified,
    EgressPolicy,
    EgressViolation,
    Locality,
    PolicyMode,
)
from app.services.egress_guard import EgressGuard

SENSITIVE = [Classification.CONFIDENTIAL, Classification.HIGHLY_CONFIDENTIAL]

ALL_CLOUD_PROVIDERS = [
    VoyageEmbeddings(),
    ClaudeLLM(),
    CloudReranker(),
    ClaudeVision(),
    CloudOcr(),
]
ALL_LOCAL_PROVIDERS = [
    LocalEmbeddings(),
    LocalLLM(),
    LocalReranker(),
    LocalVision(),
    TesseractOcr(),
]


def guard(policy: EgressPolicy, *providers) -> EgressGuard:
    by_cap: dict[Capability, list] = {}
    for p in providers:
        by_cap.setdefault(p.capability, []).append(p)
    return EgressGuard(policy, by_cap)


# ── the core matrix: every capability, every mode ─────────────────────────────


@pytest.mark.parametrize("provider", ALL_CLOUD_PROVIDERS, ids=lambda p: p.name)
@pytest.mark.parametrize("classification", SENSITIVE)
@pytest.mark.parametrize("mode", list(PolicyMode))
def test_sensitive_content_is_refused_by_every_cloud_provider(
    provider, classification: Classification, mode: PolicyMode
) -> None:
    """The headline property: confidential content, every cloud channel, every mode."""
    g = guard(EgressPolicy(mode=mode), provider)
    payload = Classified("ADL check-in procedure, step 3…", classification)
    with pytest.raises(EgressViolation):
        g.release(payload, provider)


@pytest.mark.parametrize("provider", ALL_LOCAL_PROVIDERS, ids=lambda p: p.name)
@pytest.mark.parametrize("classification", list(Classification))
def test_local_providers_accept_every_classification(provider, classification) -> None:
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), provider)
    payload = Classified("content", classification)
    assert g.release(payload, provider) == "content"


@pytest.mark.parametrize("provider", ALL_CLOUD_PROVIDERS, ids=lambda p: p.name)
def test_public_content_may_use_cloud_providers(provider) -> None:
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), provider)
    assert g.release(Classified("public", Classification.PUBLIC), provider) == "public"


# ── resolution cannot pick a forbidden provider ───────────────────────────────


@pytest.mark.parametrize("capability", list(Capability))
def test_resolution_refuses_when_only_cloud_is_configured(capability: Capability) -> None:
    cloud = [p for p in ALL_CLOUD_PROVIDERS if p.capability is capability]
    if not cloud:
        pytest.skip(f"no cloud provider defined for {capability}")
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), *cloud)
    with pytest.raises(EgressViolation):
        g.provider_for(capability, Classification.CONFIDENTIAL)


def test_resolution_prefers_a_permitted_provider_when_both_exist() -> None:
    local, cloud = LocalEmbeddings(), VoyageEmbeddings()
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), cloud, local)
    assert g.provider_for(Capability.EMBEDDING, Classification.CONFIDENTIAL) is local
    assert g.provider_for(Capability.EMBEDDING, Classification.PUBLIC) is cloud


# ── bypass attempts ───────────────────────────────────────────────────────────


def test_resolving_correctly_then_sending_elsewhere_is_still_refused() -> None:
    """The bypass the review asked about: resolve local, then hand it to a cloud sink."""
    local, cloud = LocalEmbeddings(), VoyageEmbeddings()
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), cloud, local)

    resolved = g.provider_for(Capability.EMBEDDING, Classification.CONFIDENTIAL)
    assert resolved is local

    payload = Classified("secret procedure", Classification.CONFIDENTIAL)
    with pytest.raises(EgressViolation):
        g.release(payload, cloud)


def test_unwrap_unchecked_demands_a_reason() -> None:
    payload = Classified("secret", Classification.HIGHLY_CONFIDENTIAL)
    with pytest.raises(ValueError):
        payload.unwrap_unchecked("")
    assert payload.unwrap_unchecked("rendering a PDF locally, no egress") == "secret"


# ── policy edge cases, all failing closed ─────────────────────────────────────


def test_empty_matrix_denies_rather_than_reverting_to_default() -> None:
    """Regression: `self.matrix or DEFAULT` treated {} as falsy and failed open."""
    policy = EgressPolicy(mode=PolicyMode.MIXED, matrix={})
    assert policy.allowed(Classification.PUBLIC) == frozenset({Locality.LOCAL})


def test_permissive_widens_internal_but_never_confidential() -> None:
    policy = EgressPolicy(mode=PolicyMode.PERMISSIVE)
    assert policy.permits(Classification.INTERNAL, Locality.CLOUD)
    assert not policy.permits(Classification.CONFIDENTIAL, Locality.CLOUD)


def test_strict_local_denies_cloud_even_for_public() -> None:
    policy = EgressPolicy(mode=PolicyMode.STRICT_LOCAL)
    assert not policy.permits(Classification.PUBLIC, Locality.CLOUD)


# ── startup validation ────────────────────────────────────────────────────────


def test_strict_local_rejects_any_cloud_provider_in_any_capability() -> None:
    """Not just embeddings — the review's point 4."""
    for cloud in ALL_CLOUD_PROVIDERS:
        g = guard(EgressPolicy(mode=PolicyMode.STRICT_LOCAL), *ALL_LOCAL_PROVIDERS, cloud)
        with pytest.raises(RuntimeError, match="strict_local forbids any cloud provider"):
            g.validate_startup(Classification.PUBLIC)


def test_strict_local_accepts_an_all_local_deployment() -> None:
    g = guard(EgressPolicy(mode=PolicyMode.STRICT_LOCAL), *ALL_LOCAL_PROVIDERS)
    g.validate_startup(Classification.HIGHLY_CONFIDENTIAL)


def test_local_embeddings_with_cloud_llm_cannot_claim_confidential() -> None:
    """The trap the review identified: private indexing, public answering."""
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), LocalEmbeddings(), ClaudeLLM())
    with pytest.raises(RuntimeError, match="handles_classification"):
        g.validate_startup(Classification.CONFIDENTIAL)


def test_local_embeddings_with_cloud_llm_may_declare_internal() -> None:
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), LocalEmbeddings(), ClaudeLLM())
    g.validate_startup(Classification.INTERNAL)


def test_missing_required_capability_fails_startup() -> None:
    g = guard(EgressPolicy(mode=PolicyMode.MIXED), LocalEmbeddings())  # no LLM
    with pytest.raises(RuntimeError, match="llm"):
        g.validate_startup(Classification.INTERNAL)


# ── configuration wiring ──────────────────────────────────────────────────────


def test_unknown_provider_name_is_an_error_not_a_default() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        build_providers(Settings(embedding_provider="nonexistent"))


def test_provider_configured_under_the_wrong_capability_is_rejected() -> None:
    with pytest.raises(ValueError, match="declares capability"):
        build_providers(Settings(llm_provider="voyage"))


def test_shipped_defaults_cannot_serve_confidential() -> None:
    """Documents the reference deployment's honest limitation (see config.py)."""
    settings = Settings()
    g = EgressGuard(settings.egress_policy, build_providers(settings))
    g.validate_startup(settings.handles_classification)  # internal: fine
    with pytest.raises(RuntimeError):
        g.validate_startup(Classification.CONFIDENTIAL)
