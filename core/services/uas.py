from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from core.verification.schemas import ResultadoVerificacion


@dataclass(frozen=True)
class NuevoUAS:
    matricula: str
    numero_serie: str
    fabricante: str | None
    modelo: str | None
    propietario_id: str
    observaciones: str | None


@dataclass(frozen=True)
class NuevaAsignacion:
    uas_id: str
    organizacion_id: str
    tipo: str
    vigente_desde: date
    vigente_hasta: date | None


@dataclass(frozen=True)
class NuevaInstalacion:
    componente_id: str
    uas_id: str
    instalado_en: str
    motivo: str | None


def validar_nuevo_uas(data: NuevoUAS) -> None:
    if not data.matricula.strip() or not data.numero_serie.strip() or not data.propietario_id:
        raise ValueError("La matrícula, el número de serie y la organización propietaria son obligatorios.")


def estado_para_verificacion(resultado: ResultadoVerificacion | None) -> str:
    if resultado is None or resultado.estado == "verificado":
        return "en_revision"
    return "en_revision"


def validar_asignacion(data: NuevaAsignacion) -> None:
    if data.tipo not in {"propio", "alquiler", "prestamo"}:
        raise ValueError("Tipo de asignación no permitido.")
    if data.vigente_hasta is not None and data.vigente_hasta <= data.vigente_desde:
        raise ValueError("La fecha final debe ser posterior a la fecha inicial.")


def validar_confirmacion_asignacion(
    asignacion: dict[str, Any],
    uas: dict[str, Any],
    actor_organizacion_id: str,
) -> None:
    if asignacion.get("estado") != "pendiente":
        raise ValueError("Solo se puede confirmar una asignación pendiente.")
    if uas.get("propietario_id") != actor_organizacion_id:
        raise ValueError("Solo la organización propietaria puede confirmar o rechazar la asignación.")


def validar_instalacion(
    componente: dict[str, Any],
    uas_id: str,
    actor_organizacion_id: str,
) -> None:
    if componente.get("uas_id") not in (None, uas_id):
        raise ValueError("El componente ya está instalado en otro dron.")
    if componente.get("propietario_id") not in (None, actor_organizacion_id):
        raise ValueError("La organización no puede instalar este componente.")


class UASRepository(Protocol):
    def create_uas(self, data: NuevoUAS) -> dict[str, Any]: ...
    def create_serial_verification(
        self,
        uas_id: str,
        image_path: str,
        resultado: ResultadoVerificacion,
    ) -> None: ...
    def create_assignment(self, data: NuevaAsignacion) -> dict[str, Any]: ...
    def update_assignment(self, assignment_id: str, state: str, actor_id: str) -> None: ...
    def install_component(self, data: NuevaInstalacion) -> dict[str, Any]: ...
    def remove_component(self, installation_id: str, removed_at: str, reason: str) -> None: ...
    def create_component(self, serial: str, component_type: str, organization_id: str) -> dict[str, Any]: ...


def crear_uas(data: NuevoUAS, repository: UASRepository) -> dict[str, Any]:
    validar_nuevo_uas(data)
    return repository.create_uas(data)


def crear_asignacion(data: NuevaAsignacion, repository: UASRepository) -> dict[str, Any]:
    validar_asignacion(data)
    return repository.create_assignment(data)


def responder_asignacion(
    assignment_id: str,
    assignment: dict[str, Any],
    uas: dict[str, Any],
    state: str,
    actor_organizacion_id: str,
    repository: UASRepository,
    *,
    actor_id: str | None = None,
) -> None:
    if state not in {"confirmada", "rechazada"}:
        raise ValueError("Respuesta de asignación no permitida.")
    validar_confirmacion_asignacion(assignment, uas, actor_organizacion_id)
    repository.update_assignment(assignment_id, state, actor_id or actor_organizacion_id)


def instalar_componente(
    data: NuevaInstalacion,
    componente: dict[str, Any],
    actor_organizacion_id: str,
    repository: UASRepository,
) -> dict[str, Any]:
    validar_instalacion(componente, data.uas_id, actor_organizacion_id)
    return repository.install_component(data)
