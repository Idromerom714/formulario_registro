from __future__ import annotations

from typing import Any

import streamlit as st
from supabase import create_client  # type: ignore[import-not-found]

from core.auth import AuthService
from core.config import get_settings
from core.db import backend_transaction
from core.services.registro_cuenta import (
    BackendAccountRepository,
    RegistroCuenta,
    completar_registro,
)
from core.verification.schemas import ResultadoVerificacion
from core.verification.service import verificar_documento
from ui.layout import render_header

CONSENT_TEXT = (
    "Acepto el tratamiento de mis datos para verificar mi identidad y operar SUA. "
    "Entiendo que la imagen del documento se procesa con un proveedor externo."
)
DOCUMENT_TYPES = {
    "Cédula de ciudadanía": "CC",
    "Cédula de extranjería": "CE",
    "Pasaporte": "PA",
    "Tarjeta de identidad": "TI",
    "Otro": "OTRO",
}


def _clear_verification_if_identity_changes(document_type: str, document_number: str) -> None:
    identity = (document_type, document_number.strip())
    if st.session_state.get("registration_identity") != identity:
        st.session_state.pop("registration_verification", None)
        st.session_state.pop("registration_image", None)
        st.session_state.pop("registration_mime", None)
        st.session_state["registration_identity"] = identity


def _verification_message(result: ResultadoVerificacion) -> str:
    if result.estado == "verificado":
        return "Documento verificado correctamente."
    reasons = {
        "imagen_invalida": "La imagen no es válida.",
        "ilegible": "El documento no es legible.",
        "confianza_baja": "La lectura tiene confianza insuficiente.",
        "campo_dudoso": "El número del documento requiere revisión.",
        "no_coincide": "El número leído no coincide con el ingresado.",
        "json_invalido": "La respuesta del proveedor no fue válida.",
        "error_proveedor": "No fue posible contactar al proveedor de verificación.",
    }
    return reasons.get(result.motivo, "La verificación requiere revisión humana.")


def _verify_identity(document_type: str, document_number: str, image: Any) -> None:
    if not document_number.strip() or image is None:
        st.error("Ingresa el número y proporciona una foto del documento.")
        return
    image_bytes = image.getvalue()
    mime = image.type or "image/jpeg"
    with st.spinner("Verificando el documento..."):
        result = verificar_documento(
            image_bytes,
            mime,
            document_type,
            document_number.strip(),
        )
    st.session_state["registration_verification"] = result
    st.session_state["registration_image"] = image_bytes
    st.session_state["registration_mime"] = mime


def main() -> None:
    settings = get_settings()
    st.set_page_config(page_title="Registro de cuenta | SUA", page_icon="📝")
    render_header("Registro de cuenta")
    st.title("Crear cuenta")
    st.caption("Primero verificaremos tu documento; después podrás completar tus datos.")

    tipo = st.selectbox("Tipo de cuenta", ["piloto", "tecnico"], key="registration_type")
    documento_label = st.selectbox("Tipo de documento", list(DOCUMENT_TYPES))
    documento_tipo = DOCUMENT_TYPES[documento_label]
    documento_numero = st.text_input(
        "Número de documento",
        key="registration_document_number",
    )
    _clear_verification_if_identity_changes(documento_tipo, documento_numero)

    st.subheader("Verificación de identidad")
    st.caption("El número ingresado se compara después de que el VLM lea la imagen; no se envía al VLM.")
    acepto = st.checkbox(CONSENT_TEXT, key="registration_consent")
    camera_image = st.camera_input("Toma una foto del documento")
    uploaded_image = st.file_uploader(
        "O carga una foto del documento",
        type=["jpg", "jpeg", "png", "webp"],
    )
    image = camera_image or uploaded_image

    if st.button(
        "Verificar documento",
        type="primary",
        disabled=not acepto or not documento_numero.strip() or image is None,
    ):
        _verify_identity(documento_tipo, documento_numero, image)
        st.rerun()

    result = st.session_state.get("registration_verification")
    if not isinstance(result, ResultadoVerificacion):
        st.info("Completa el número, acepta el consentimiento y verifica una imagen para continuar.")
        return

    if result.estado == "verificado":
        st.success(_verification_message(result))
    else:
        st.warning(_verification_message(result))
        st.caption("No se habilita el alta hasta obtener una verificación correcta.")
        return

    st.subheader("Datos de la cuenta")
    with st.form("registro_cuenta"):
        nombres = st.text_input("Nombres", value=result.nombres_extraidos or "")
        apellidos = st.text_input("Apellidos", value=result.apellidos_extraidos or "")
        correo = st.text_input("Correo electrónico")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Crear cuenta", type="primary")

    if not submitted:
        return
    if not all((correo.strip(), password, nombres.strip(), apellidos.strip())):
        st.error("Completa nombres, apellidos, correo y contraseña.")
        return
    try:
        auth_client = create_client(settings.supabase_url, settings.supabase_anon_key)
        auth = AuthService(auth_client, settings=settings)
        session = auth.sign_up(correo, password)
        if session is None:
            st.success("Revisa tu correo para confirmar la cuenta y luego completar el registro.")
            return
        data = RegistroCuenta(
            tipo=tipo,
            documento_tipo=documento_tipo,
            documento_numero=documento_numero.strip(),
            nombres=nombres.strip(),
            apellidos=apellidos.strip(),
            correo=correo.strip(),
            organizacion=None,
            consentimiento_version="C1-2026-01",
            consentimiento_texto=CONSENT_TEXT,
            verificacion=result.model_dump(),
        )
        with backend_transaction(session.user_id, None, "registro_cuenta", settings) as cursor:
            profile = completar_registro(
                session.user_id,
                data,
                BackendAccountRepository(cursor),
            )
        st.success("Tu cuenta está en revisión.")
        st.session_state["profile_id"] = str(profile["id"])
    except Exception as exc:  # noqa: BLE001 - no se muestran SQL ni trazas
        st.error("No fue posible completar el registro. Verifica tus datos e inténtalo de nuevo.")
        st.session_state["registration_error"] = type(exc).__name__
        if settings.app_env == "desarrollo":
            st.exception(exc)


main()
