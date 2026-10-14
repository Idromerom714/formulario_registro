from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RegistroCuenta:
    tipo: str
    documento_tipo: str
    documento_numero: str
    nombres: str
    apellidos: str
    correo: str
    organizacion: str | None
    consentimiento_version: str
    consentimiento_texto: str
    verificacion: dict[str, Any] | None = None


class AccountRepository(Protocol):
    def find_profile(self, auth_user_id: str, tipo: str) -> dict[str, Any] | None: ...
    def create_profile(self, auth_user_id: str, data: RegistroCuenta, *, organization_id: str | None) -> dict[str, Any]: ...


def validar_consentimiento(data: RegistroCuenta) -> None:
    if not data.consentimiento_version.strip() or "proveedor externo" not in data.consentimiento_texto.lower():
        raise ValueError("El consentimiento debe indicar el procesamiento de la imagen por un proveedor externo.")


def completar_registro(
    auth_user_id: str,
    data: RegistroCuenta,
    repository: AccountRepository,
    *,
    organization_id: str | None = None,
) -> dict[str, Any]:
    if not auth_user_id:
        raise ValueError("La sesión autenticada es obligatoria.")
    if data.tipo not in {"piloto", "tecnico"}:
        raise ValueError("Tipo de cuenta no permitido.")
    validar_consentimiento(data)
    existing = repository.find_profile(auth_user_id, data.tipo)
    if existing:
        return existing
    return repository.create_profile(auth_user_id, data, organization_id=organization_id)


class BackendAccountRepository:
    """Persistencia C1. Se usa dentro de una transacción ya fijada al actor."""

    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def find_profile(self, auth_user_id: str, tipo: str) -> dict[str, Any] | None:
        table = {"piloto": "pilotos", "tecnico": "tecnicos"}[tipo]
        self.cursor.execute(f"SELECT * FROM {table} WHERE auth_user_id = %s", (auth_user_id,))
        return self.cursor.fetchone()

    def create_profile(self, auth_user_id: str, data: RegistroCuenta, *, organization_id: str | None) -> dict[str, Any]:
        now = datetime.now(UTC)
        if data.tipo == "piloto":
            self.cursor.execute(
                """
                INSERT INTO pilotos
                    (auth_user_id, documento_tipo, documento_numero, nombres, apellidos,
                     correo_contacto, estado_verificacion)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (auth_user_id, data.documento_tipo, data.documento_numero, data.nombres,
                 data.apellidos, data.correo, "pendiente"),
            )
            profile = self.cursor.fetchone()
            self.cursor.execute(
                """
                INSERT INTO organizaciones (tipo, razon_social, correo_contacto)
                VALUES ('persona_natural', %s, %s)
                RETURNING id
                """,
                (f"{data.nombres} {data.apellidos}".strip(), data.correo),
            )
            organization_id = self.cursor.fetchone()["id"]
            self.cursor.execute(
                """
                INSERT INTO miembros_organizacion (auth_user_id, organizacion_id, rol)
                VALUES (%s, %s, 'admin_org')
                """,
                (auth_user_id, organization_id),
            )
            self.cursor.execute(
                """
                INSERT INTO vinculos_piloto_org
                    (piloto_id, organizacion_id, tipo, vigente_desde, estado)
                VALUES (%s, %s, 'freelance', %s, 'pendiente')
                """,
                (profile["id"], organization_id, now.date()),
            )
            subject_type, subject_id = "piloto", profile["id"]
        else:
            self.cursor.execute(
                """
                INSERT INTO tecnicos
                    (auth_user_id, documento_tipo, documento_numero, nombres, apellidos,
                     organizacion_id, estado_verificacion)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (auth_user_id, data.documento_tipo, data.documento_numero, data.nombres,
                 data.apellidos, organization_id, "pendiente"),
            )
            profile = self.cursor.fetchone()
            subject_type, subject_id = "tecnico", profile["id"]
        self.cursor.execute(
            """
            INSERT INTO consentimientos
                (sujeto_tipo, sujeto_id, finalidad, texto_version, medio, registrado_por)
            VALUES (%s, %s, 'verificacion_identidad', %s, 'app', %s)
            """,
            (subject_type, subject_id, data.consentimiento_version, auth_user_id),
        )
        return profile


def default_start_date() -> date:
    return date.today()
