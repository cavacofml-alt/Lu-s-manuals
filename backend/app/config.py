"""Application settings.

Every open architectural decision from docs/ARCHITECTURE.md §21 surfaces here as a
setting, so that changing one is a configuration change rather than a code change.
No provider is constructed at import time.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.classification import Classification, EmbeddingPolicy, PolicyMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Documentation Intelligence AI"
    debug: bool = False

    database_url: str = "postgresql+psycopg://docintel:docintel@localhost:5432/docintel"

    # §21 D1/D2 — embeddings.
    # The shipped default is the *safe* one, not the recommended one. Using a cloud
    # provider is an opt-in that also requires declaring `handles_classification`
    # below, so disclosure is always a deliberate act rather than an inherited default.
    embedding_provider: str = "local"  # local | voyage | none
    embedding_model_id: str = "bge-m3"
    embedding_dimensions: int = 1024

    # §8.1.1 — classification policy
    embedding_policy_mode: PolicyMode = PolicyMode.MIXED

    # The most sensitive classification this deployment is permitted to hold. Startup
    # fails unless the configured providers can serve it, so a cloud-only deployment
    # must explicitly lower this — and in doing so states that it will not hold
    # confidential documents.
    handles_classification: Classification = Classification.CONFIDENTIAL

    # §21 D3/D4 — document processing
    pdf_processor: str = "pdfium"  # pdfium | pymupdf

    # §21 D6 — storage
    storage_backend: str = "local_fs"  # local_fs | s3
    storage_root: str = "./var/storage"

    # §21 D7/D8 — answering
    llm_provider: str = "claude"
    llm_model_id: str = "claude-opus-5"
    reranker: str = "cross_encoder"

    @property
    def embedding_policy(self) -> EmbeddingPolicy:
        return EmbeddingPolicy(mode=self.embedding_policy_mode)


@lru_cache
def get_settings() -> Settings:
    return Settings()
