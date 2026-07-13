"""Typed environment configuration with startup-safe validation."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(os.getenv("KARYA_ENV_FILE", Path(__file__).with_name(".env"))).expanduser()
load_dotenv(ENV_FILE)


class ConfigurationError(RuntimeError):
    """A user-actionable environment configuration error."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class LLMSettings(BaseModel):
    """Settings consumed exclusively by the LLM factory."""

    provider: str
    model: str
    api_key: SecretStr
    base_url: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=3000, ge=128, le=100_000)
    local_device: str = "auto"
    local_dtype: str = "auto"
    local_revision: str = "main"
    local_cache_dir: str | None = None
    local_context_window: int = Field(default=8192, ge=512, le=131_072)
    local_trust_remote_code: bool = False
    local_files_only: bool = False
    # Warm the model at API startup (background thread) so the first call is fast.
    # Disable for packaged/CI startups that must not touch multi-GB weights.
    local_preload: bool = True

    @field_validator("provider", "model")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("local_dtype")
    @classmethod
    def valid_local_dtype(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"auto", "float32", "float16", "bfloat16"}:
            raise ValueError("must be auto, float32, float16, or bfloat16")
        return value

    @field_validator("local_device")
    @classmethod
    def valid_local_device(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"auto", "cpu", "mps", "cuda"} and not value.startswith("cuda:"):
            raise ValueError("must be auto, cpu, mps, cuda, or cuda:<index>")
        return value


class JiraInstanceSettings(BaseModel):
    """Configuration for one named Jira installation."""

    name: str
    base_url: str
    auth_type: Literal["cloud", "server"]
    api_token: SecretStr
    email: str | None = None
    story_points_field: str | None = None
    ac_field: str | None = None

    @field_validator("base_url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        return value.strip().rstrip("/")


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str | None = None
    llm_temperature: float = 0.2
    llm_max_tokens: int = 3000
    llm_local_device: str = "auto"
    llm_local_dtype: str = "auto"
    llm_local_revision: str = "main"
    llm_local_cache_dir: str | None = None
    llm_local_context_window: int = 8192
    llm_local_trust_remote_code: bool = False
    llm_local_files_only: bool = False
    llm_local_preload: bool = True
    jira_instances: str = ""
    jira_write_enabled: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"

    @property
    def llm(self) -> LLMSettings:
        try:
            return LLMSettings(
                provider=self.llm_provider,
                model=self.llm_model,
                api_key=self.llm_api_key,
                base_url=self.llm_base_url or None,
                temperature=self.llm_temperature,
                max_tokens=self.llm_max_tokens,
                local_device=self.llm_local_device,
                local_dtype=self.llm_local_dtype,
                local_revision=self.llm_local_revision,
                local_cache_dir=self.llm_local_cache_dir or None,
                local_context_window=self.llm_local_context_window,
                local_trust_remote_code=self.llm_local_trust_remote_code,
                local_files_only=self.llm_local_files_only,
                local_preload=self.llm_local_preload,
            )
        except ValidationError as exc:
            raise ConfigurationError(
                [f"LLM_{'.'.join(map(str, error['loc'])).upper()}: {error['msg']}" for error in exc.errors()]
            ) from exc

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def jira_configs(self) -> dict[str, JiraInstanceSettings]:
        configs: dict[str, JiraInstanceSettings] = {}
        errors: list[str] = []
        for raw_name in self.jira_instances.split(","):
            name = raw_name.strip().lower()
            if not name:
                continue
            prefix = f"JIRA_{name.upper()}_"
            values = {
                "name": name,
                "base_url": os.getenv(prefix + "BASE_URL", ""),
                "auth_type": os.getenv(prefix + "AUTH_TYPE", "cloud").lower(),
                "email": os.getenv(prefix + "EMAIL") or None,
                "api_token": SecretStr(os.getenv(prefix + "API_TOKEN", "")),
                "story_points_field": os.getenv(prefix + "STORY_POINTS_FIELD") or None,
                "ac_field": os.getenv(prefix + "AC_FIELD") or None,
            }
            try:
                config = JiraInstanceSettings.model_validate(values)
                configs[name] = config
            except ValidationError as exc:
                errors.extend(f"{prefix}{error['loc'][0]}: {error['msg']}" for error in exc.errors())
        if errors:
            raise ConfigurationError(errors)
        return configs

    def validate_startup(self) -> None:
        errors: list[str] = []
        try:
            # Shape validation only; the API key requirement is provider-specific
            # and lives in the LLM factory (mock mode needs no key).
            self.llm
        except ConfigurationError as exc:
            errors.extend(exc.errors)
        try:
            self.jira_configs()  # Parse names and auth types; credentials validate lazily.
        except ConfigurationError as exc:
            errors.extend(exc.errors)
        if errors:
            raise ConfigurationError(errors)


@lru_cache
def get_settings() -> Settings:
    return Settings()
