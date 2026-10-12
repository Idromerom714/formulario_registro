from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtraccionDocumento(_StrictModel):
    numero_documento: str | None = None
    nombres: str | None = None
    apellidos: str | None = None
    tipo_documento_detectado: str | None = None
    legible: bool
    campos_dudosos: list[str] = Field(default_factory=list)
    confianza: float = Field(ge=0, le=1)


class ExtraccionSerial(_StrictModel):
    serial: str | None = None
    legible: bool
    caracteres_ambiguos: list[str] = Field(default_factory=list)
    confianza: float = Field(ge=0, le=1)


class ResultadoVerificacion(_StrictModel):
    imagen_sha256: str
    valor_ingresado: str
    valor_extraido: str | None = None
    nombres_extraidos: str | None = None
    apellidos_extraidos: str | None = None
    metodo: Literal["vlm"] = "vlm"
    modelo_vlm: str
    coincide: bool | None = None
    confianza: float | None = Field(default=None, ge=0, le=1)
    estado: Literal["verificado", "en_revision"]
    salida_cruda: dict[str, Any]
    motivo: str