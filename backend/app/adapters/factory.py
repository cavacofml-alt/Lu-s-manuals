"""Provider construction and startup validation.

Two rules, both from docs/ARCHITECTURE.md §8.1.1:

- providers are resolved per document classification, never from a global default;
- if the policy permits a provider that is not configured, the application refuses to
  start rather than degrading to whatever happens to be available.
"""

from __future__ import annotations

from app.adapters.embeddings import LocalEmbeddingProvider, VoyageEmbeddingProvider
from app.adapters.ports import EmbeddingProvider
from app.config import Settings
from app.domain.classification import (
    Classification,
    EmbeddingPolicy,
    Locality,
    PolicyViolation,
)


def build_embedding_providers(settings: Settings) -> dict[Locality, EmbeddingProvider]:
    providers: dict[Locality, EmbeddingProvider] = {}
    if settings.embedding_provider == "voyage":
        providers[Locality.CLOUD] = VoyageEmbeddingProvider(
            model_id=settings.embedding_model_id,
            dimensions=settings.embedding_dimensions,
        )
    elif settings.embedding_provider == "local":
        providers[Locality.LOCAL] = LocalEmbeddingProvider(
            model_id=settings.embedding_model_id,
            dimensions=settings.embedding_dimensions,
        )
    elif settings.embedding_provider != "none":
        raise ValueError(f"Unknown embedding_provider: {settings.embedding_provider!r}")
    return providers


class EmbeddingRouter:
    """The only path from a document to an embedding provider."""

    def __init__(
        self,
        policy: EmbeddingPolicy,
        providers: dict[Locality, EmbeddingProvider],
    ) -> None:
        self._policy = policy
        self._providers = providers

    def for_document(self, classification: Classification) -> EmbeddingProvider:
        provider = self._policy.provider_for(classification, dict(self._providers))
        assert isinstance(provider, EmbeddingProvider)
        return provider

    def validate_startup(self, handles: Classification) -> None:
        """Fail fast if the deployment cannot serve the classification it declares.

        `handles` is the most sensitive tier this deployment is permitted to hold. A
        cloud-only deployment must lower it explicitly, which is the act that records
        "this installation does not hold confidential documents".
        """
        try:
            self.for_document(handles)
        except PolicyViolation as exc:
            raise RuntimeError(
                f"This deployment declares handles_classification={handles!s}, but no "
                f"configured embedding provider may process it. {exc} — either configure "
                "a local provider, or lower handles_classification deliberately."
            ) from exc
