from __future__ import annotations

from typing import Any

from core.verification.schemas import ResultadoVerificacion

from .uas import NuevaAsignacion, NuevaInstalacion, NuevoUAS


class BackendUASRepository:
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def create_uas(self, data: NuevoUAS) -> dict[str, Any]:
        self.cursor.execute(
            """
            INSERT INTO uas
                (matricula, numero_serie, fabricante, modelo, propietario_id,
                 estado, observaciones)
            VALUES (%s, %s, %s, %s, %s, 'en_revision', %s)
            RETURNING *
            """,
            (
                data.matricula,
                data.numero_serie,
                data.fabricante,
                data.modelo,
                data.propietario_id,
                data.observaciones,
            ),
        )
        return self.cursor.fetchone()

    def create_serial_verification(
        self,
        uas_id: str,
        image_path: str,
        resultado: ResultadoVerificacion,
    ) -> None:
        self.cursor.execute(
            """
            INSERT INTO verificaciones
                (entidad_tipo, entidad_id, tipo_documento, imagen_path, imagen_sha256,
                 valor_ingresado, valor_extraido, metodo, modelo_vlm, coincide,
                 confianza, estado, salida_cruda)
            VALUES ('uas', %s, 'serial', %s, %s, %s, %s, 'vlm', %s, %s, %s, %s, %s)
            """,
            (
                uas_id,
                image_path,
                resultado.imagen_sha256,
                resultado.valor_ingresado,
                resultado.valor_extraido,
                resultado.modelo_vlm,
                resultado.coincide,
                resultado.confianza,
                resultado.estado,
                resultado.salida_cruda,
            ),
        )

    def create_assignment(self, data: NuevaAsignacion) -> dict[str, Any]:
        self.cursor.execute(
            """
            INSERT INTO asignaciones_uas
                (uas_id, organizacion_id, tipo, vigente_desde, vigente_hasta, estado)
            VALUES (%s, %s, %s, %s, %s, 'pendiente')
            RETURNING *
            """,
            (
                data.uas_id,
                data.organizacion_id,
                data.tipo,
                data.vigente_desde,
                data.vigente_hasta,
            ),
        )
        return self.cursor.fetchone()

    def update_assignment(self, assignment_id: str, state: str, actor_id: str) -> None:
        self.cursor.execute(
            """
            UPDATE asignaciones_uas
            SET estado = %s, confirmada_por = %s, confirmada_en = now()
            WHERE id = %s AND estado = 'pendiente'
            """,
            (state, actor_id, assignment_id),
        )

    def install_component(self, data: NuevaInstalacion) -> dict[str, Any]:
        self.cursor.execute(
            """
            INSERT INTO instalaciones
                (componente_id, uas_id, instalado_en, motivo_retiro)
            VALUES (%s, %s, %s, NULL)
            RETURNING *
            """,
            (data.componente_id, data.uas_id, data.instalado_en),
        )
        return self.cursor.fetchone()

    def remove_component(self, installation_id: str, removed_at: str, reason: str) -> None:
        self.cursor.execute(
            """
            UPDATE instalaciones
            SET retirado_en = %s, motivo_retiro = %s
            WHERE id = %s AND retirado_en IS NULL
            """,
            (removed_at, reason, installation_id),
        )

    def create_component(self, serial: str, component_type: str, organization_id: str) -> dict[str, Any]:
        self.cursor.execute(
            """
            INSERT INTO componentes (tipo, numero_serie, propietario_id)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (component_type, serial, organization_id),
        )
        return self.cursor.fetchone()
