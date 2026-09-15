"""The single authority that decides which provider may receive which content.

docs/ARCHITECTURE.md §8.1.1. There is one guard for every capability, rather than an
`if classification...` inside each adapter, because per-adapter checks drift apart and
the inconsistency is silent.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from app.domain.egress import (
    REQUIRED_CAPABILITIES,
    Capability,
    Classification,
    Classified,
    ContentSink,
    EgressPolicy,
    EgressViolation,
    Locality,
)

T = TypeVar("T")

logger = logging.getLogger("egress.audit")


class EgressGuard:
    def __init__(
        self,
        policy: EgressPolicy,
        providers: dict[Capability, list[ContentSink]],
    ) -> None:
        self._policy = policy
        self._providers = providers

    # ── resolution ────────────────────────────────────────────────────────────
    def provider_for(self, capability: Capability, classification: Classification) -> ContentSink:
        """Pick a provider from the classification, never from a global default."""
        allowed = self._policy.allowed(classification)
        for provider in self._providers.get(capability, []):
            if provider.locality in allowed:
                return provider
        configured = [p.name for p in self._providers.get(capability, [])]
        raise EgressViolation(
            f"No {capability!s} provider may process {classification!s} content "
            f"(policy allows {sorted(allowed)}; configured: {configured or 'none'})"
        )

    # ── release ───────────────────────────────────────────────────────────────
    def release(self, payload: Classified[T], provider: ContentSink) -> T:
        """Open classified content for one specific provider, or refuse.

        This is the only sanctioned way content reaches a provider. Passing a provider
        the guard did not select is still checked here, so resolving correctly and then
        sending elsewhere does not slip through.
        """
        if not self._policy.permits(payload.classification, provider.locality):
            raise EgressViolation(
                f"Refused: {payload.classification!s} content may not be sent to "
                f"{provider.name!r} ({provider.locality!s}, {provider.capability!s}). "
                f"Policy allows {sorted(self._policy.allowed(payload.classification))}."
            )
        # §30 audit: enough to answer "has confidential material ever left the network?"
        # without recording the content itself.
        logger.info(
            "egress_permitted",
            extra={
                "provider": provider.name,
                "locality": str(provider.locality),
                "capability": str(provider.capability),
                "classification": str(payload.classification),
            },
        )
        return payload.value

    # ── startup ───────────────────────────────────────────────────────────────
    def validate_startup(self, handles: Classification) -> None:
        """Refuse to start a deployment that cannot honour what it declares.

        Two independent checks, because they fail in opposite directions:

        1. Every *required* capability must have a provider permitted for `handles`.
           A deployment claiming to hold confidential documents with a cloud answering
           model is not a working configuration — it is a leak waiting for a question.
        2. Under `strict_local`, no configured provider of any capability may be cloud.
           Not merely "a local one exists" — a cloud provider that is present can be
           selected by a future code path, so its mere presence is the failure.
        """
        if self._policy.mode.value == "strict_local":
            offenders = [
                f"{p.name} ({p.capability!s})"
                for sinks in self._providers.values()
                for p in sinks
                if p.locality is Locality.CLOUD
            ]
            if offenders:
                raise RuntimeError(
                    "EGRESS_POLICY_MODE=strict_local forbids any cloud provider, but "
                    f"these are configured: {', '.join(sorted(offenders))}. "
                    "Remove them or change the policy mode deliberately."
                )

        missing: list[str] = []
        for capability in sorted(REQUIRED_CAPABILITIES):
            try:
                self.provider_for(capability, handles)
            except EgressViolation as exc:
                missing.append(str(exc))
        if missing:
            raise RuntimeError(
                f"This deployment declares handles_classification={handles!s}, but "
                "cannot serve it:\n  - " + "\n  - ".join(missing) + "\n"
                "Either configure local providers for these capabilities, or lower "
                "handles_classification deliberately — which records that this "
                "installation does not hold documents above that tier."
            )
