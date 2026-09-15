"""Provider construction from configuration."""

from __future__ import annotations

from app.adapters.providers import REGISTRY, Provider
from app.config import Settings
from app.domain.egress import Capability, ContentSink


def build_providers(settings: Settings) -> dict[Capability, list[ContentSink]]:
    """Construct exactly what configuration names — no implicit fallbacks.

    An unknown provider name is an error rather than a silent "use the default"; the
    whole point of the policy is that nothing is selected by accident.
    """
    configured = {
        Capability.EMBEDDING: settings.embedding_provider,
        Capability.LLM: settings.llm_provider,
        Capability.RERANK: settings.rerank_provider,
        Capability.VISION: settings.vision_provider,
        Capability.OCR: settings.ocr_provider,
    }

    providers: dict[Capability, list[ContentSink]] = {}
    for capability, name in configured.items():
        if name == "none":
            continue
        cls: type[Provider] | None = REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"Unknown provider {name!r} configured for {capability!s}")
        if cls.capability is not capability:
            raise ValueError(
                f"Provider {name!r} declares capability {cls.capability!s}, "
                f"but is configured as the {capability!s} provider"
            )
        providers[capability] = [cls()]
    return providers
