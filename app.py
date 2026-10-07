import base64
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import httpx
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError


load_dotenv()

DATABASE_PATH = "registros.db"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "thinkingmachines/inkling-small:free"
DOCUMENT_TYPES = [
    "Cédula de Ciudadanía",
    "Dron (Serial S/N)",
    "Batería/Componente",
]


class VLMResult(BaseModel):
    extracted_code: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    detected_type: str
    reasoning: str


def init_database() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS registros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                tipo_doc TEXT NOT NULL,
                serial_validado TEXT NOT NULL,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL,
                estado_verificacion TEXT NOT NULL
            )
            """
        )


def sanitize_code(value: Optional[str]) -> str:
    """Remove separators used in IDs and serials before comparing them."""
    if not value:
        return ""
    return re.sub(r"[\s.\-]", "", value).upper()


def levenshtein_distance(first: str, second: str) -> int:
    if len(first) < len(second):
        first, second = second, first
    previous = list(range(len(second) + 1))
    for first_index, first_char in enumerate(first, start=1):
        current = [first_index]
        for second_index, second_char in enumerate(second, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[second_index] + 1,
                    previous[second_index - 1] + (first_char != second_char),
                )
            )
        previous = current
    return previous[-1]


def codes_match(expected: str, extracted: Optional[str]) -> bool:
    expected_clean = sanitize_code(expected)
    extracted_clean = sanitize_code(extracted)
    if not expected_clean or not extracted_clean:
        return False
    if expected_clean == extracted_clean:
        return True
    return len(expected_clean) >= 8 and len(extracted_clean) >= 8 and (
        levenshtein_distance(expected_clean, extracted_clean) <= 1
    )


def image_as_base64(image_file) -> str:
    return base64.b64encode(image_file.getvalue()).decode("ascii")


def parse_vlm_response(response: httpx.Response) -> VLMResult:
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("El modelo no devolvió contenido de texto.")
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
    parsed_payload = json.loads(content)
    if hasattr(VLMResult, "model_validate"):
        return VLMResult.model_validate(parsed_payload)
    return VLMResult.parse_obj(parsed_payload)


def extract_code_from_image(image_file, document_type: str) -> VLMResult:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("Falta configurar la variable de entorno OPENROUTER_API_KEY.")

    encoded_image = image_as_base64(image_file)
    system_prompt = (
        "Eres un extractor de identificadores. Analiza la imagen y responde únicamente "
        "con JSON válido, sin markdown, usando exactamente estas claves: "
        '{"extracted_code":"string o null","confidence":0.0,"detected_type":"string",'
        '"reasoning":"breve explicación"}. confidence debe estar entre 0 y 1. '
        "Extrae el código visible completo, conservando sus caracteres relevantes."
    )
    request = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Tipo seleccionado: {document_type}. Extrae su número o serial.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                    },
                ],
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "Formulario de registro",
    }
    with httpx.Client(timeout=60) as client:
        response = client.post(OPENROUTER_URL, headers=headers, json=request)
        response.raise_for_status()
    return parse_vlm_response(response)


def save_registration(document_type: str, validated_code: str, name: str, email: str) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO registros
                (timestamp, tipo_doc, serial_validado, nombre, email, estado_verificacion)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                document_type,
                validated_code,
                name.strip(),
                email.strip(),
                "VERIFICADO",
            ),
        )


def reset_verification_when_expected_changes(expected_code: str) -> None:
    previous_expected = st.session_state.get("expected_code")
    if previous_expected is not None and previous_expected != expected_code:
        st.session_state["verified"] = False
        st.session_state["validated_code"] = ""
    st.session_state["expected_code"] = expected_code


def main() -> None:
    st.set_page_config(page_title="Registro verificado", page_icon="📋")
    init_database()
    st.session_state.setdefault("verified", False)
    st.session_state.setdefault("validated_code", "")
    st.title("Formulario de registro")
    st.caption("La captura visual debe coincidir con el identificador esperado para continuar.")

    document_type = st.selectbox("Tipo de documento/equipo", DOCUMENT_TYPES)
    expected_code = st.text_input("Número de Identificación / Serial Esperado")
    reset_verification_when_expected_changes(expected_code)

    camera_image = st.camera_input("Captura una foto del documento o serial")
    uploaded_image = st.file_uploader(
        "Alternativa: sube una imagen", type=["jpg", "jpeg", "png", "webp"]
    )
    image = camera_image or uploaded_image

    if st.button("Verificar identificación", type="primary", disabled=not bool(image and expected_code.strip())):
        with st.spinner("Analizando la imagen..."):
            try:
                result = extract_code_from_image(image, document_type)
                st.session_state["last_vlm_result"] = result
                if codes_match(expected_code, result.extracted_code):
                    st.session_state["verified"] = True
                    st.session_state["validated_code"] = sanitize_code(result.extracted_code)
                    st.success(
                        f"Identificación verificada ({result.confidence:.0%} de confianza)."
                    )
                else:
                    st.session_state["verified"] = False
                    st.session_state["validated_code"] = ""
                    st.error(
                        "El código detectado no coincide con el esperado. "
                        f"Detectado: {result.extracted_code or 'no identificado'}."
                    )
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValidationError, ValueError) as error:
                st.session_state["verified"] = False
                st.session_state["validated_code"] = ""
                st.error(f"No fue posible validar la imagen: {error}")
            except RuntimeError as error:
                st.session_state["verified"] = False
                st.session_state["validated_code"] = ""
                st.error(str(error))

    if st.session_state.get("verified", False):
        st.success(f"Código validado: {st.session_state['validated_code']}")
    else:
        st.info("El formulario permanece bloqueado hasta verificar el identificador.")

    is_verified = st.session_state.get("verified", False)
    with st.form("registration_form"):
        name = st.text_input("Nombre completo", disabled=not is_verified)
        email = st.text_input("Correo electrónico", disabled=not is_verified)
        role = st.selectbox(
            "Rol", ["Selecciona un rol", "Propietario", "Operador", "Técnico"], disabled=not is_verified
        )
        notes = st.text_area("Notas", disabled=not is_verified)
        complete = st.form_submit_button("Completar Registro", disabled=not is_verified)

    if complete:
        if not name.strip() or not email.strip() or role == "Selecciona un rol":
            st.error("Completa nombre, correo electrónico y rol.")
        else:
            try:
                save_registration(
                    document_type,
                    st.session_state["validated_code"],
                    name,
                    email,
                )
                st.success("Registro guardado correctamente.")
                st.session_state["registration_saved_notes"] = notes
            except sqlite3.Error as error:
                st.error(f"No fue posible guardar el registro: {error}")


if __name__ == "__main__":
    main()