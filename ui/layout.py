from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from core.permisos import paginas_permitidas


def render_sidebar(rol: str | None, *, nombre: str = "Usuario", entorno: str = "desarrollo") -> str | None:
    with st.sidebar:
        st.title("SUA")
        st.caption("Sistema UTM Antioqueño")
        st.info("Medellín, Colombia\nRegión operativa")
        pages = paginas_permitidas(rol)
        selected = st.radio("Módulos", pages, label_visibility="collapsed") if pages else None
        st.divider()
        st.page_link("pages/ayuda.py", label="Ayuda y documentación")
        st.page_link("pages/acerca.py", label="Acerca de SUA")
        st.divider()
        st.caption(f"{nombre}\nRol: {rol or 'sin perfil'}\nEntorno: {entorno}")
    return selected


def render_header(page: str) -> None:
    now = datetime.now(ZoneInfo("America/Bogota"))
    utc = now.astimezone(ZoneInfo("UTC"))
    st.caption(f"OPERACIONES / {page.upper()}")
    st.badge("PROTOTIPO - DATOS SIMULADOS", color="blue")
    st.caption(f"COT {now:%Y-%m-%d %H:%M} / UTC {utc:%H:%M}")
