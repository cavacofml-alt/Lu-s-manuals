"""Application settings.

Every open architectural decision from docs/ARCHITECTURE.md §21 surfaces here, so that
changing one is configuration rather than code. No provider is constructed at import
time; all resolve through `build_guard`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.egress import Classification, EgressPolicy, PolicyMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Documentation Intelligence AI"
    debug: bool = False

    database_url: str = "postgresql+psycopg://docintel:docintel@localhost:5432/docintel"

    # ── egress policy (§8.1.1) ────────────────────────────────────────────────
    egress_policy_mode: PolicyMode = PolicyMode.MIXED

    # The most sensitive tier this deployment may hold. Startup fails unless every
    # required capability has a provider permitted for it.
    #
    # The default is `internal`, not `confidential`, and the reason is worth stating:
    # the reference deployment answers with Claude, which is a cloud provider, so it
    # *cannot* honour confidential content. Defaulting to `confidential` here would
    # mean the default deployment never starts. Defaulting to `internal` instead makes
    # the limitation explicit and still fails closed, because documents default to
    # `confidential` (§3.3) and are therefore rejected at upload until someone either
    # classifies them down deliberately or configures local providers.
    handles_classification: Classification = Classification.INTERNAL

    # ── providers, one per capability (§21 D1/D2/D7/D8) ───────────────────────
    embedding_provider: str = "voyage"  # voyage | local_embeddings | none
    llm_provider: str = "claude"  # claude | local_llm | none
    rerank_provider: str = "local_reranker"  # local_reranker | cloud_reranker | none
    vision_provider: str = "claude_vision"  # claude_vision | local_vision | none
    ocr_provider: str = "tesseract"  # tesseract | cloud_ocr | none

    embedding_model_id: str = "voyage-3"
    embedding_dimensions: int = 1024

    # ── §21 D3/D6 ─────────────────────────────────────────────────────────────
    pdf_processor: str = "pdfium"  # pdfium | pymupdf
    storage_backend: str = "local_fs"  # local_fs | s3
    storage_root: str = "./var/storage"

    @property
    def egress_policy(self) -> EgressPolicy:
        return EgressPolicy(mode=self.egress_policy_mode)


@lru_cache
def get_settings() -> Settings:
    return Settings()
