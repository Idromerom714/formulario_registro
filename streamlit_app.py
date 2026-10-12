import os

import streamlit as st

from core.verification.schemas import ResultadoVerificacion
from core.verification.service import verificar_documento, verificar_serial

DOCUMENT_TYPES = {
    "Cedula de piloto o tecnico": "documento",
    "Placa o serial de UAS/componente": "serial",
}


def _reset_when_input_changes(value: str) -> None:
    previous = st.session_state.get("verification_input")
    if previous is not None and previous != value:
        st.session_state.pop("verification_result", None)
        st.session_state["verified"] = False
    st.session_state["verification_input"] = value


def _show_result(result: ResultadoVerificacion, kind: str) -> None:
    st.session_state["verification_result"] = result
    st.session_state["verified"] = result.estado == "verificado"

    if result.estado == "verificado":
        st.success("Identificacion verificada.")
    else:
        st.warning(f"Resultado en revision: {result.motivo}.")

    details = {
        "Estado": result.estado,
        "Coincidencia": "Si" if result.coincide is True else "No" if result.coincide is False else "No determinada",
        "Confianza": f"{result.confianza:.0%}" if result.confianza is not None else "No disponible",
    }
    if result.valor_extraido:
        details["Valor extraido"] = result.valor_extraido
    if kind == "documento":
        if result.nombres_extraidos:
            details["Nombres"] = result.nombres_extraidos
        if result.apellidos_extraidos:
            details["Apellidos"] = result.apellidos_extraidos
    st.table(details)


def main() -> None:
    st.set_page_config(page_title="Verificacion documental SUA", page_icon="SUA", layout="centered")
    st.title("Verificacion documental SUA")
    st.caption("Validacion de cedulas, placas y seriales mediante vision artificial.")

    selected_type = st.selectbox("Tipo de identificador", list(DOCUMENT_TYPES))
    kind = DOCUMENT_TYPES[selected_type]
    entered_value = st.text_input(
        "Numero de documento" if kind == "documento" else "Serial esperado",
        placeholder="Ingresa el valor que debe coincidir",
    )
    _reset_when_input_changes(entered_value)

    image = st.camera_input("Toma una fotografia")
    if image is None:
        image = st.file_uploader(
            "O carga una imagen",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=False,
        )

    can_verify = bool(image and entered_value.strip())
    if st.button("Verificar", type="primary", disabled=not can_verify, use_container_width=True):
        try:
            image_bytes = image.getvalue()
            mime = image.type or ""
            with st.spinner("Analizando la imagen..."):
                if kind == "documento":
                    result = verificar_documento(
                        image_bytes,
                        mime,
                        selected_type,
                        entered_value,
                    )
                else:
                    result = verificar_serial(image_bytes, mime, entered_value)
            _show_result(result, kind)
        except Exception:  # noqa: BLE001 - la interfaz debe contener fallos de configuracion o entrada
            st.session_state["verified"] = False
            st.error("No fue posible iniciar la verificacion. Revisa la configuracion del proveedor.")

    result = st.session_state.get("verification_result")
    if isinstance(result, ResultadoVerificacion) and result.estado == "verificado":
        st.divider()
        st.subheader("Datos para el formulario")
        if kind == "documento":
            st.text_input("Nombres", value=result.nombres_extraidos or "", disabled=True)
            st.text_input("Apellidos", value=result.apellidos_extraidos or "", disabled=True)
        else:
            st.text_input("Serial validado", value=result.valor_extraido or "", disabled=True)
        st.info("La verificacion fue exitosa. El llamador puede continuar con su propio formulario.")
    elif isinstance(result, ResultadoVerificacion):
        st.info("Este resultado requiere revision humana; no se habilita como verificado automaticamente.")

    if not os.getenv("VLM_MODEL"):
        st.caption("Configura VLM_MODEL para habilitar el proveedor VLM.")


if __name__ == "__main__":
    main()
