from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAGDESK_", env_file=".env", extra="ignore")

    store: Literal["postgres", "memory"] = "postgres"
    database_url: str | None = None

    embedder: Literal["hashing", "voyage"] = "hashing"
    embedding_dimensions: int = Field(384, ge=64, le=4096)
    voyage_api_key: SecretStr | None = None
    voyage_model: str = "voyage-3.5"

    generator: Literal["extractive", "claude"] = "extractive"
    claude_model: str = "claude-opus-5-5"
    claude_effort: Literal["low", "medium", "high"] = "low"

    retrieval_candidates: int = Field(20, ge=5, le=200)
    min_similarity: float = Field(0.15, ge=0.0, le=1.0)

    # Dev only: "tenant:scope1,scope2:key_id:secret" entries for the memory key store.
    bootstrap_keys: list[str] = []

    log_level: str = "INFO"

    @model_validator(mode="after")
    def _check(self) -> Settings:
        if self.store == "postgres" and not self.database_url:
            raise ValueError("RAGDESK_DATABASE_URL is required when RAGDESK_STORE=postgres")
        if self.embedder == "voyage" and not self.voyage_api_key:
            raise ValueError("RAGDESK_VOYAGE_API_KEY is required when RAGDESK_EMBEDDER=voyage")
        return self
