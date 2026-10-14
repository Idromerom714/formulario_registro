from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from supabase import Client  # type: ignore[import-not-found]

from .registros import StorageUploader


class SupabaseStorageUploader(StorageUploader):
    def __init__(self, client: Client, bucket: str) -> None:
        self.bucket = client.storage.from_(bucket)

    def upload(self, path: str, content: bytes, mime: str) -> None:
        self.bucket.upload(
            path,
            content,
            {"content-type": mime, "upsert": "false"},
        )

    def remove(self, path: str) -> None:
        self.bucket.remove([path])


class SupabaseRecordsReader:
    def __init__(self, client: Client) -> None:
        self.client: Any = client

    def list_people(self, kind: str) -> list[dict[str, Any]]:
        table = {"pilotos": "pilotos", "tecnicos": "tecnicos"}[kind]
        return list(
            self.client.table(table)
            .select(
                "id,documento_tipo,documento_numero,nombres,apellidos,"
                "correo_contacto,estado,estado_verificacion"
            )
            .order("apellidos")
            .execute()
            .data
            or []
        )

    def list_organizations(self, kind: str) -> list[dict[str, Any]]:
        return list(
            self.client.table("organizaciones")
            .select("id,tipo,razon_social,nit,correo_contacto,estado")
            .eq("tipo", kind)
            .order("razon_social")
            .execute()
            .data
            or []
        )

    def get_person(self, kind: str, record_id: str) -> dict[str, Any] | None:
        table = {"pilotos": "pilotos", "tecnicos": "tecnicos"}[kind]
        response = self.client.table(table).select("*").eq("id", record_id).maybe_single().execute()
        return response.data

    def get_organization(self, record_id: str) -> dict[str, Any] | None:
        response = self.client.table("organizaciones").select("*").eq("id", record_id).maybe_single().execute()
        return response.data

    def links_for_pilot(self, pilot_id: str) -> list[dict[str, Any]]:
        return list(
            self.client.table("vinculos_piloto_org")
            .select("*,organizaciones(razon_social,tipo)")
            .eq("piloto_id", pilot_id)
            .execute()
            .data
            or []
        )

    def verifications_for(self, kind: str, record_id: str) -> list[dict[str, Any]]:
        return list(
            self.client.table("verificaciones")
            .select(
                "id,tipo_documento,imagen_sha256,valor_ingresado,valor_extraido,"
                "nombres_extraidos,apellidos_extraidos,metodo,modelo_vlm,"
                "coincide,confianza,estado,creado_en"
            )
            .eq("entidad_tipo", kind)
            .eq("entidad_id", record_id)
            .order("creado_en", desc=True)
            .execute()
            .data
            or []
        )

    def consents_for(self, kind: str, record_id: str) -> list[dict[str, Any]]:
        return list(
            self.client.table("consentimientos")
            .select("id,finalidad,texto_version,medio,aceptado_en,revocado_en")
            .eq("sujeto_tipo", kind)
            .eq("sujeto_id", record_id)
            .order("aceptado_en", desc=True)
            .execute()
            .data
            or []
        )

    def revoke_consent(self, subject_type: str, subject_id: str, consent_id: str) -> None:
        self.client.table("consentimientos").update(
            {"revocado_en": datetime.now(UTC).isoformat()}
        ).eq("id", consent_id).eq("sujeto_tipo", subject_type).eq("sujeto_id", subject_id).execute()


class SupabaseUASReader:
    def __init__(self, client: Client) -> None:
        self.client: Any = client

    def list_uas(self) -> list[dict[str, Any]]:
        return list(
            self.client.table("uas")
            .select("id,matricula,numero_serie,fabricante,modelo,propietario_id,estado,observaciones")
            .order("matricula")
            .execute()
            .data
            or []
        )

    def get_uas(self, uas_id: str) -> dict[str, Any] | None:
        return self.client.table("uas").select("*").eq("id", uas_id).maybe_single().execute().data

    def organizations(self) -> list[dict[str, Any]]:
        return list(
            self.client.table("organizaciones")
            .select("id,razon_social,tipo,estado")
            .order("razon_social")
            .execute()
            .data
            or []
        )

    def assignments(self, uas_id: str) -> list[dict[str, Any]]:
        return list(
            self.client.table("asignaciones_uas")
            .select("*,organizaciones(razon_social)")
            .eq("uas_id", uas_id)
            .order("vigente_desde", desc=True)
            .execute()
            .data
            or []
        )

    def assignment(self, assignment_id: str) -> dict[str, Any] | None:
        return (
            self.client.table("asignaciones_uas")
            .select("*")
            .eq("id", assignment_id)
            .maybe_single()
            .execute()
            .data
        )

    def components(self, uas_id: str) -> list[dict[str, Any]]:
        return list(
            self.client.table("instalaciones")
            .select("id,componente_id,uas_id,instalado_en,retirado_en,motivo_retiro,componentes(*)")
            .eq("uas_id", uas_id)
            .order("instalado_en", desc=True)
            .execute()
            .data
            or []
        )

    def component(self, component_id: str) -> dict[str, Any] | None:
        return self.client.table("componentes").select("*").eq("id", component_id).maybe_single().execute().data

    def components_catalog(self) -> list[dict[str, Any]]:
        return list(
            self.client.table("componentes")
            .select("id,tipo,numero_serie,propietario_id,estado")
            .order("numero_serie")
            .execute()
            .data
            or []
        )

    def metrics(self, uas_id: str) -> dict[str, Any] | None:
        return self.client.table("v_metricas_uas").select("*").eq("uas_id", uas_id).maybe_single().execute().data
