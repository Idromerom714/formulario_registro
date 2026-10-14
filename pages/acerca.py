import streamlit as st

from ui.layout import render_header

st.set_page_config(page_title="Acerca de SUA", page_icon="ℹ️")
render_header("Acerca")
st.title("Acerca de SUA")
st.write("SUA es el Sistema UTM Antioqueño para la gestión segura de operaciones de drones.")
