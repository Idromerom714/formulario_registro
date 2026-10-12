"""Verificacion documental con proveedores VLM."""

from .schemas import ResultadoVerificacion
from .service import verificar_documento, verificar_serial

__all__ = ["ResultadoVerificacion", "verificar_documento", "verificar_serial"]