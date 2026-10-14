import streamlit as st

from ui.layout import render_header

st.set_page_config(page_title="Ayuda | SUA", page_icon="❔")
render_header("Ayuda")
st.title("Ayuda y documentación")
st.write("Consulta los procedimientos de registro, operación y reporte de discrepancias.")
