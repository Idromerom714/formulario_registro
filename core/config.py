from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str = Field(..., min_length=1)
    supabase_anon_key: str = Field(..., min_length=1)
    database_url: str = Field(..., min_length=1)
    app_env: Literal["desarrollo", "pruebas", "produccion"] = "desarrollo"
    supabase_jwt_audience: str = "authenticated"
    session_refresh_margin_s: int = Field(default=60, ge=0)
    documentos_bucket: str = "documentos-id"
    prototype_badge: str = "PROTOTIPO - DATOS SIMULADOS"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
