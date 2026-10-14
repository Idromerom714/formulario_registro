from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID, uuid4

from core.verification.schemas import ResultadoVerificacion


@dataclass(frozen=True)
class RegistroPersona:
    tipo: str
    documento_tipo: str
    documento_numero: str
    nombres: str
    apellidos: str
    correo: str
    licencia_numero: str | None
    licencia_vence: date | None
    observaciones: str | None


@dataclass(frozen=True)
class RegistroOrganizacion:
    tipo: str
    razon_social: str
    nit: str
    correo: str | None
    observaciones: str | None


@dataclass(frozen=True)
class Consentimiento:
    version: str
    texto: str


@dataclass(frozen=True)
class AltaPersona:
    persona: RegistroPersona
    consentimiento: Consentimiento
    valor_ingresado: str
    imagen: bytes
    mime: str
    resultado: ResultadoVerificacion


def enmascarar_documento(documento: str) -> str:
    limpio = documento.strip()
    if len(limpio) <= 3:
        return "*" * len(limpio)
    return "*" * (len(limpio) - 3) + limpio[-3:]


def motivo_en_espanol(motivo: str) -> str:
    return {
        "": "Verificación exitosa.",
        "imagen_invalida": "La imagen no es válida o supera el tamaño permitido.",
        "ilegible": "El documento no es legible.",
        "confianza_baja": "La confianza de la lectura es insuficiente.",
        "campo_dudoso": "Hay campos del documento que requieren revisión.",
        "no_coincide": "El número detectado no coincide con el ingresado.",
        "serial_ambiguo": "El identificador contiene caracteres ambiguos.",
        "json_invalido": "El proveedor devolvió una respuesta no válida.",
        "error_proveedor": "No fue posible completar la verificación automática.",
    }.get(motivo, "La verificación requiere revisión humana.")


def salida_con_edicion(
    resultado: ResultadoVerificacion,
    nombres: str,
    apellidos: str,
) -> dict[str, Any]:
    salida = dict(resultado.salida_cruda)
    salida["nombres_extraidos_original"] = resultado.nombres_extraidos
    salida["apellidos_extraidos_original"] = resultado.apellidos_extraidos
    salida["nombres_finales"] = nombres
    salida["apellidos_finales"] = apellidos
    return salida


class RecordsRepository(Protocol):
    def has_valid_consent(self, subject_type: str, subject_id: str, purpose: str) -> bool: ...
    def create_person(self, data: RegistroPersona, auth_user_id: str) -> dict[str, Any]: ...
    def create_organization(self, data: RegistroOrganizacion) -> dict[str, Any]: ...
    def create_verification(
        self,
        verification_id: UUID,
        entity_type: str,
        entity_id: str | None,
        image_path: str,
        data: AltaPersona,
        raw_output: dict[str, Any],
    ) -> dict[str, Any]: ...
    def attach_verification(self, verification_id: UUID, entity_id: str) -> None: ...
    def create_legal_verification(
        self,
        verification_id: UUID,
        organization_id: str,
        image_path: str,
        image_sha256: str,
        consent: Consentimiento,
    ) -> None: ...
    def create_consent(self, subject_type: str, subject_id: str, consent: Consentimiento, actor_id: str) -> None: ...


class StorageUploader(Protocol):
    def upload(self, path: str, content: bytes, mime: str) -> None: ...
    def remove(self, path: str) -> None: ...


def validar_cambio_vinculo(estado_actual: str, nuevo_estado: str, actor_tipo: str) -> None:
    if nuevo_estado not in {"confirmado", "rechazado"}:
        raise ValueError("Estado de vínculo no permitido.")
    if estado_actual != "pendiente":
        raise ValueError("Solo se puede responder un vínculo pendiente.")
    if actor_tipo != "piloto":
        raise ValueError("Solo el piloto puede confirmar o rechazar el vínculo.")


def validar_revocacion_consentimiento(estado_actual: str | None) -> None:
    if estado_actual is not None:
        raise ValueError("El consentimiento ya fue revocado.")


def alta_persona(
    auth_user_id: str,
    data: AltaPersona,
    repository: RecordsRepository,
    storage: StorageUploader,
) -> dict[str, Any]:
    if not auth_user_id:
        raise ValueError("La sesión autenticada es obligatoria.")
    if not data.consentimiento.version.strip() or not data.consentimiento.texto.strip():
        raise ValueError("Se requiere un consentimiento vigente antes de subir el documento.")
    verification_id = uuid4()
    image_path = f"{auth_user_id}/{verification_id}"
    storage.upload(image_path, data.imagen, data.mime)
    try:
        profile = repository.create_person(data.persona, auth_user_id)
        repository.create_verification(
            verification_id,
            "piloto" if data.persona.tipo == "piloto" else "tecnico",
            str(profile["id"]),
            image_path,
            data,
            salida_con_edicion(
                data.resultado,
                data.persona.nombres,
                data.persona.apellidos,
            ),
        )
        repository.create_consent(
            "piloto" if data.persona.tipo == "piloto" else "tecnico",
            str(profile["id"]),
            data.consentimiento,
            auth_user_id,
        )
        return profile
    except Exception:
        storage.remove(image_path)
        raise


def alta_organizacion(
    data: RegistroOrganizacion,
    repository: RecordsRepository,
    *,
    actor_id: str,
    storage: StorageUploader | None = None,
    legal_document: bytes | None = None,
    legal_mime: str | None = None,
    consent: Consentimiento | None = None,
) -> dict[str, Any]:
    if legal_document is not None and (storage is None or not legal_mime or consent is None):
        raise ValueError("El documento legal requiere consentimiento y almacenamiento configurado.")
    organization = repository.create_organization(data)
    if legal_document is None:
        return organization
    verification_id = uuid4()
    path = f"{actor_id}/{verification_id}"
    if storage is None:
        raise ValueError("El documento legal requiere almacenamiento configurado.")
    storage.upload(path, legal_document, legal_mime or "application/octet-stream")
    try:
        repository.create_legal_verification(
            verification_id,
            str(organization["id"]),
            path,
            sha256(legal_document).hexdigest(),
            consent or Consentimiento("", ""),
        )
    except Exception:
        storage.remove(path)
        raise
    return organization
