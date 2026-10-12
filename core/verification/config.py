from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VerificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    vlm_provider: str = "anthropic"
    vlm_model: str = Field(..., min_length=1)
    vlm_api_key: str | None = None
    umbral_confianza: float = Field(default=0.90, ge=0, le=1)
    max_image_mb: float = Field(default=5, gt=0)
    vlm_timeout_s: float = Field(default=30, gt=0)
    vlm_max_reintentos: int = Field(default=1, ge=0)


@lru_cache(maxsize=1)
def get_settings() -> VerificationSettings:
    return VerificationSettings()  # type: ignore[call-arg]