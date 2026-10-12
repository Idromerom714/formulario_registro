import logging
from hashlib import sha256
from typing import Any, Literal

from pydantic import ValidationError

from .config import get_settings
from .imagen import ImageValidationError, sanear_imagen
from .rules import decidir_documento, decidir_serial, normalizar_nombre
from .schemas import ExtraccionDocumento, ExtraccionSerial, ResultadoVerificacion
from .vlm import ErrorProveedor, JSONInvalidoError, LectorDeterminista, VLMProvider

logger = logging.getLogger(__name__)


def _resultado_base(imagen: bytes, valor: str, modelo: str, motivo: str, **kwargs: Any) -> ResultadoVerificacion:
    digest = sha256(imagen).hexdigest()
    logger.info("verificacion sha256=%s valor_final=%s motivo=%s", digest, (valor or "")[-3:], motivo)
    return ResultadoVerificacion(
        imagen_sha256=digest, valor_ingresado=valor, modelo_vlm=modelo,
        estado="en_revision", motivo=motivo, salida_cruda={}, **kwargs,
    )


def _lector_resultado(lector: LectorDeterminista | None, imagen: bytes) -> dict[str, Any] | None:
    if lector is None:
        return None
    return lector.leer(imagen)


def verificar_documento(imagen: bytes, mime: str, tipo_documento: str, numero_ingresado: str,
                        proveedor: VLMProvider | None = None, lector: LectorDeterminista | None = None) -> ResultadoVerificacion:
    settings = get_settings()
    try:
        saneada = sanear_imagen(imagen, mime, settings.max_image_mb)
    except ImageValidationError:
        return _resultado_base(imagen, numero_ingresado, settings.vlm_model, "imagen_invalida")
    lector_payload = _lector_resultado(lector, saneada.datos)
    if lector_payload is not None:
        try:
            extraction = ExtraccionDocumento.model_validate(lector_payload)
        except ValidationError:
            return _resultado_base(imagen, numero_ingresado, settings.vlm_model, "json_invalido")
    else:
        try:
            extraction = proveedor.extraer_documento(saneada.datos, saneada.mime, tipo_documento) if proveedor else _default_provider(settings).extraer_documento(saneada.datos, saneada.mime, tipo_documento)
        except ValidationError:
            return _resultado_base(imagen, numero_ingresado, settings.vlm_model, "json_invalido")
        except JSONInvalidoError:
            return _resultado_base(imagen, numero_ingresado, settings.vlm_model, "json_invalido")
        except Exception:  # noqa: BLE001 - el contrato convierte cualquier fallo del proveedor
            return _resultado_base(imagen, numero_ingresado, settings.vlm_model, "error_proveedor")
    coincide, motivo, _ = decidir_documento(numero_ingresado, extraction, settings.umbral_confianza)
    estado: Literal["verificado", "en_revision"] = "verificado" if motivo == "" else "en_revision"
    return ResultadoVerificacion(imagen_sha256=saneada.sha256_original, valor_ingresado=numero_ingresado,
        valor_extraido=extraction.numero_documento, nombres_extraidos=normalizar_nombre(extraction.nombres),
        apellidos_extraidos=normalizar_nombre(extraction.apellidos), modelo_vlm=settings.vlm_model,
        coincide=coincide, confianza=extraction.confianza, estado=estado, salida_cruda=extraction.model_dump(), motivo=motivo)


def verificar_serial(imagen: bytes, mime: str, serial_ingresado: str,
                     proveedor: VLMProvider | None = None, lector: LectorDeterminista | None = None) -> ResultadoVerificacion:
    settings = get_settings()
    try:
        saneada = sanear_imagen(imagen, mime, settings.max_image_mb)
    except ImageValidationError:
        return _resultado_base(imagen, serial_ingresado, settings.vlm_model, "imagen_invalida")
    lector_payload = _lector_resultado(lector, saneada.datos)
    if lector_payload is not None:
        try:
            extraction = ExtraccionSerial.model_validate(lector_payload)
        except ValidationError:
            return _resultado_base(imagen, serial_ingresado, settings.vlm_model, "json_invalido")
    else:
        try:
            extraction = proveedor.extraer_serial(saneada.datos, saneada.mime) if proveedor else _default_provider(settings).extraer_serial(saneada.datos, saneada.mime)
        except ValidationError:
            return _resultado_base(imagen, serial_ingresado, settings.vlm_model, "json_invalido")
        except JSONInvalidoError:
            return _resultado_base(imagen, serial_ingresado, settings.vlm_model, "json_invalido")
        except Exception:  # noqa: BLE001 - el contrato convierte cualquier fallo del proveedor
            return _resultado_base(imagen, serial_ingresado, settings.vlm_model, "error_proveedor")
    coincide, motivo = decidir_serial(serial_ingresado, extraction, settings.umbral_confianza)
    estado: Literal["verificado", "en_revision"] = "verificado" if not motivo else "en_revision"
    return ResultadoVerificacion(imagen_sha256=saneada.sha256_original, valor_ingresado=serial_ingresado,
        valor_extraido=extraction.serial, modelo_vlm=settings.vlm_model, coincide=coincide,
        confianza=extraction.confianza, estado=estado,
        salida_cruda=extraction.model_dump(), motivo=motivo)


def _default_provider(settings: Any) -> VLMProvider:
    from .vlm import AnthropicVLM
    if not settings.vlm_api_key:
        raise ErrorProveedor("API key no configurada")
    return AnthropicVLM(settings.vlm_model, settings.vlm_api_key, settings.vlm_timeout_s, settings.vlm_max_reintentos)