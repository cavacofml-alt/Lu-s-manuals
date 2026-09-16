"""Bypass attempts — Property 3 from the third architecture review.

The review's challenge was exact and correct: `Classified[T]` alone is a type contract,
not a runtime barrier, and tests that only prove `guard.release()` refuses sensitive
content prove nothing about a developer who never calls the guard.

Before `Released` existed, all three of these bypasses worked:

    VoyageEmbeddings().embed_documents(["CONFIDENTIAL"])   # reached provider code
    payload.unwrap_unchecked("any reason")                 # returned raw content
    ClaudeVision().describe(classified_payload)            # accepted by signature

Each test below performs a bypass against the current code and asserts it is refused.
They exist to fail loudly if the barrier is ever weakened back to a convention.
"""

from __future__ import annotations

import pytest

from app.adapters.providers import ClaudeVision, LocalEmbeddings, VoyageEmbeddings
from app.domain.egress import (
    Capability,
    Classification,
    Classified,
    EgressPolicy,
    EgressViolation,
    PolicyMode,
    Released,
)
from app.services.egress_guard import EgressGuard

SECRET = Classified("PNL NOT PROCESSED — internal procedure", Classification.HIGHLY_CONFIDENTIAL)


def _guard(*providers) -> EgressGuard:
    by_cap: dict[Capability, list] = {}
    for p in providers:
        by_cap.setdefault(p.capability, []).append(p)
    return EgressGuard(EgressPolicy(mode=PolicyMode.MIXED), by_cap)


# ── Property 3: the public adapter API cannot be used without the guard ───────


@pytest.mark.parametrize("raw", ["CONFIDENTIAL CONTENT", ["a", "b"], b"bytes", 42])
def test_direct_call_with_raw_content_is_refused(raw: object) -> None:
    """The bypass the review named: call the cloud adapter directly, no guard."""
    with pytest.raises(EgressViolation, match="only content cleared by EgressGuard"):
        VoyageEmbeddings().submit(raw)  # type: ignore[arg-type]


def test_direct_call_with_a_classified_payload_is_refused() -> None:
    """Passing `Classified` straight to a provider used to be accepted by the signature."""
    with pytest.raises(EgressViolation, match="only content cleared by EgressGuard"):
        ClaudeVision().submit(SECRET)  # type: ignore[arg-type]


def test_unwrap_unchecked_does_not_produce_something_a_provider_accepts() -> None:
    """`unwrap_unchecked` still returns the value — but it is not a clearance.

    This is the honest shape of the control: the escape hatch exists for local, no-egress
    paths, and using it does not get you past a provider's door.
    """
    raw = SECRET.unwrap_unchecked("rendering a PDF locally, no egress")
    assert raw == SECRET.value
    with pytest.raises(EgressViolation):
        VoyageEmbeddings().submit(raw)  # type: ignore[arg-type]


def test_a_hand_built_clearance_is_refused() -> None:
    """Forging the clearance object directly, without the guard's sentinel."""
    with pytest.raises(EgressViolation, match="only be constructed by EgressGuard"):
        Released("secret", Classification.HIGHLY_CONFIDENTIAL, "voyage-3")


def test_a_clearance_cannot_be_replayed_against_a_different_provider() -> None:
    """Obtain a legitimate clearance for a local provider, then aim it at a cloud one."""
    local, cloud = LocalEmbeddings(), VoyageEmbeddings()
    guard = _guard(local, cloud)

    clearance = guard.release(SECRET, local)  # legitimate: local may see it
    assert clearance.provider_name == local.name

    with pytest.raises(EgressViolation, match="cannot be replayed"):
        cloud.submit(clearance)


def test_the_guard_refuses_to_issue_a_clearance_for_a_cloud_provider() -> None:
    guard = _guard(VoyageEmbeddings())
    with pytest.raises(EgressViolation):
        guard.release(SECRET, VoyageEmbeddings())


def test_the_sanctioned_path_works_end_to_end() -> None:
    """A permitted provider, reached properly, reaches its implementation."""
    local = LocalEmbeddings()
    clearance = _guard(local).release(SECRET, local)
    with pytest.raises(NotImplementedError, match="STEP 3"):
        local.submit(clearance)


# ── Property 7: a new capability cannot silently escape the policy ────────────


def test_a_new_provider_must_declare_a_locality_to_be_usable() -> None:
    """A provider without a declared locality fails at the guard, not silently."""
    from app.adapters.providers import Provider

    class UndeclaredProvider(Provider):
        name = "sloppy-new-provider"
        capability = Capability.SUMMARISATION
        # locality deliberately not declared

    guard = _guard()
    with pytest.raises((EgressViolation, AttributeError)):
        guard.release(SECRET, UndeclaredProvider())  # type: ignore[arg-type]


def test_every_registered_provider_declares_locality_and_capability() -> None:
    """Property 7, enforced across the whole registry rather than per provider."""
    from app.adapters.providers import REGISTRY

    for name, cls in REGISTRY.items():
        assert hasattr(cls, "locality"), f"{name} does not declare a locality"
        assert hasattr(cls, "capability"), f"{name} does not declare a capability"
        assert cls.capability in Capability, f"{name} has an unknown capability"


# ── §8.1.3 C: content must never enter logs ──────────────────────────────────


def test_audit_record_carries_metadata_but_never_content(caplog) -> None:
    """The audit trail must answer "did anything leave?" without itself disclosing."""
    import logging

    local = LocalEmbeddings()
    with caplog.at_level(logging.INFO, logger="egress.audit"):
        _guard(local).release(SECRET, local)

    assert caplog.records, "the release was not audited"
    record = caplog.records[0]
    assert record.provider == local.name  # type: ignore[attr-defined]
    assert record.classification == str(SECRET.classification)  # type: ignore[attr-defined]

    everything_logged = " ".join(str(v) for v in record.__dict__.values())
    assert SECRET.value not in everything_logged, "document content reached the log record"


def test_reserved_capabilities_exist_so_new_channels_cannot_slip_past(caplog) -> None:
    """§8.1.3 A and B: storage and cloud parsing are inside the boundary."""
    assert Capability.STORAGE in Capability
    assert Capability.DOCUMENT_PROCESSING in Capability
