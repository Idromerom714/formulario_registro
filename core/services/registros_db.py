from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from .registros import (
    AltaPersona,
    Consentimiento,
    RegistroOrganizacion,
    RegistroPersona,
)


class BackendRecordsRepository:
    """Repositorio para usar únicamente dentro de backend_transaction."""

    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def has_valid_consent(self, subject_type: str, subject_id: str, purpose: str) -> bool:
        self.cursor.execute(
            """
            SELECT 1 FROM consentimientos
            WHERE sujeto_tipo = %s AND sujeto_id = %s AND finalidad = %s
              AND revocado_en IS NULL
            LIMIT 1
            """,
            (subject_type, subject_id, purpose),
        )
        return self.cursor.fetchone() is not None

    def create_person(self, data: RegistroPersona, auth_user_id: str) -> dict[str, Any]:
        table = {"piloto": "pilotos", "tecnico": "tecnicos"}[data.tipo]
        columns = (
            "auth_user_id, documento_tipo, documento_numero, nombres, apellidos, "
            "correo_contacto, licencia_numero, licencia_vence, observaciones, estado_verificacion"
        )
        values: tuple[Any, ...] = (
            auth_user_id,
            data.documento_tipo,
            data.documento_numero,
            data.nombres,
            data.apellidos,
            data.correo,
            data.licencia_numero,
            data.licencia_vence,
            data.observaciones,
            "verificado" if data.tipo == "piloto" else "pendiente",
        )
        if data.tipo == "tecnico":
            columns += ", organizacion_id"
            values += (None,)
        self.cursor.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({', '.join(['%s'] * len(values))}) RETURNING *",
            values,
        )
        return self.cursor.fetchone()

    def create_organization(self, data: RegistroOrganizacion) -> dict[str, Any]:
        self.cursor.execute(
            """
            INSERT INTO organizaciones (tipo, razon_social, nit, correo_contacto)
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (data.tipo, data.razon_social, data.nit, data.correo),
        )
        return self.cursor.fetchone()

    def create_verification(
        self,
        verification_id: UUID,
        entity_type: str,
        entity_id: str | None,
        image_path: str,
        data: AltaPersona,
        raw_output: dict[str, Any],
    ) -> dict[str, Any]:
        result = data.resultado
        self.cursor.execute(
            """
            INSERT INTO verificaciones
                (id, entidad_tipo, entidad_id, tipo_documento, imagen_path, imagen_sha256,
                 valor_ingresado, valor_extraido, nombres_extraidos, apellidos_extraidos,
                 metodo, modelo_vlm, coincide, confianza, estado, salida_cruda)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'vlm', %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                str(verification_id),
                entity_type,
                entity_id,
                data.persona.documento_tipo,
                image_path,
                result.imagen_sha256,
                result.valor_ingresado,
                result.valor_extraido,
                result.nombres_extraidos,
                result.apellidos_extraidos,
                result.modelo_vlm,
                result.coincide,
                result.confianza,
                result.estado,
                raw_output,
            ),
        )
        return self.cursor.fetchone()

    def attach_verification(self, verification_id: UUID, entity_id: str) -> None:
        self.cursor.execute(
            "UPDATE verificaciones SET entidad_id = %s WHERE id = %s",
            (entity_id, str(verification_id)),
        )

    def create_legal_verification(
        self,
        verification_id: UUID,
        organization_id: str,
        image_path: str,
        image_sha256: str,
        consent: Consentimiento,
    ) -> None:
        self.cursor.execute(
            """
            INSERT INTO verificaciones
                (id, entidad_tipo, entidad_id, tipo_documento, imagen_path,
                 imagen_sha256, valor_ingresado, metodo, estado, salida_cruda)
            VALUES (%s, 'organizacion', %s, 'documento_legal', %s, %s, %s,
                    'manual', 'en_revision', %s)
            """,
            (
                str(verification_id),
                organization_id,
                image_path,
                image_sha256,
                consent.version,
                {"consentimiento_version": consent.version},
            ),
        )

    def create_consent(self, subject_type: str, subject_id: str, consent: Consentimiento, actor_id: str) -> None:
        self.cursor.execute(
            """
            INSERT INTO consentimientos
                (sujeto_tipo, sujeto_id, finalidad, texto_version, medio, registrado_por)
            VALUES (%s, %s, 'verificacion_identidad', %s, 'app', %s)
            """,
            (subject_type, subject_id, consent.version, actor_id),
        )

    def revoke_consent(self, subject_type: str, subject_id: str, consent_id: str) -> None:
        self.cursor.execute(
            """
            UPDATE consentimientos
            SET revocado_en = now()
            WHERE id = %s AND sujeto_tipo = %s AND sujeto_id = %s
              AND revocado_en IS NULL
            """,
            (consent_id, subject_type, subject_id),
        )

    def create_link(
        self,
        piloto_id: str,
        organization_id: str,
        link_type: str,
        starts: date,
    ) -> dict[str, Any]:
        self.cursor.execute(
            """
            INSERT INTO vinculos_piloto_org
                (piloto_id, organizacion_id, tipo, vigente_desde, estado)
            VALUES (%s, %s, %s, %s, 'pendiente')
            RETURNING *
            """,
            (piloto_id, organization_id, link_type, starts),
        )
        return self.cursor.fetchone()

    def update_link_status(self, link_id: str, status: str) -> None:
        self.cursor.execute(
            """
            UPDATE vinculos_piloto_org
            SET estado = %s
            WHERE id = %s
              AND estado IN ('pendiente', 'confirmado')
            """,
            (status, link_id),
        )

    def terminate_link(self, link_id: str, ends: date) -> None:
        self.cursor.execute(
            """
            UPDATE vinculos_piloto_org
            SET estado = 'terminado', vigente_hasta = %s
            WHERE id = %s AND estado IN ('pendiente', 'confirmado')
            """,
            (ends, link_id),
        )
