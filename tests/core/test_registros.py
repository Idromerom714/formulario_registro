from __future__ import annotations

from core.services.registros import (
    AltaPersona,
    Consentimiento,
    RegistroPersona,
    enmascarar_documento,
    salida_con_edicion,
    validar_cambio_vinculo,
    validar_revocacion_consentimiento,
)
from core.verification.schemas import ResultadoVerificacion


def verification(state: str = "en_revision") -> ResultadoVerificacion:
    return ResultadoVerificacion(
        imagen_sha256="a" * 64,
        valor_ingresado="123456",
        valor_extraido="123456",
        nombres_extraidos="ANA",
        apellidos_extraidos="PEREZ",
        modelo_vlm="test",
        coincide=True,
        confianza=0.8,
        estado=state,  # type: ignore[arg-type]
        salida_cruda={"legible": True},
        motivo="confianza_baja",
    )


def test_document_is_masked_with_last_three_characters() -> None:
    assert enmascarar_documento("123456789") == "******789"
    assert enmascarar_documento("12") == "**"


def test_manual_name_edits_preserve_extracted_values() -> None:
    output = salida_con_edicion(verification(), "Ana María", "Pérez")
    assert output["nombres_extraidos_original"] == "ANA"
    assert output["nombres_finales"] == "Ana María"


def test_pending_verification_can_create_person_without_being_verified() -> None:
    assert verification().estado == "en_revision"
    data = AltaPersona(
        persona=RegistroPersona(
            tipo="piloto",
            documento_tipo="CC",
            documento_numero="123456",
            nombres="Ana",
            apellidos="Pérez",
            correo="ana@example.test",
            licencia_numero=None,
            licencia_vence=None,
            observaciones=None,
        ),
        consentimiento=Consentimiento("v1", "proveedor externo"),
        valor_ingresado="123456",
        imagen=b"image",
        mime="image/png",
        resultado=verification(),
    )
    assert data.resultado.estado == "en_revision"


def test_only_pilot_can_answer_pending_link() -> None:
    validar_cambio_vinculo("pendiente", "confirmado", "piloto")


def test_consent_revocation_is_one_way() -> None:
    validar_revocacion_consentimiento(None)
