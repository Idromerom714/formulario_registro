"""
Script de pruebas para los Criterios de Aceptación del documento
"Verificación IA de Serial de Dron - UTM Medellín" (v2).

Qué hace: llama al endpoint /api/v1/verificar-serial con cada imagen de
la carpeta "Imagenes de prueba" y compara la respuesta real contra lo
que el documento espera para cada caso. Además manda datos de ejemplo
de registro del dron (marca, modelo, peso, etc.) para comprobar que el
backend los recibe y los devuelve en "datos_registrados" sin romper
nada de la verificación del serial.

Requisitos antes de correrlo:
  1. El backend debe estar corriendo (otra terminal, dentro de backend):
         python -m uvicorn main:app --reload
  2. Necesitas la librería requests instalada:
         pip install requests

Cómo correrlo (parado dentro de la carpeta backend):
    python test_casos.py
"""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:8000/api/v1/verificar-serial"
API_KEY = os.getenv("API_KEY")

# Esta carpeta está un nivel arriba de backend/
IMG_DIR = Path(__file__).resolve().parent.parent / "Imagenes de prueba"

# Datos de registro del dron de ejemplo: se mandan en TODOS los casos de
# abajo, nada más para comprobar que el backend los recibe bien y los
# devuelve en "datos_registrados". Como todavía son opcionales (no hay
# listas oficiales de selector), estos valores son inventados a modo de
# ejemplo, no corresponden a ningún drone real.
DATOS_DRON_EJEMPLO = {
    "marca": "DJI",
    "modelo": "Mavic 3",
    "tipo_arquitectura": "Multirotor",
    "peso_vacio": "0.90",
    "peso_mtow": "1.05",
    "categoria_uso": "Recreativo",
    "estado_registro": "Activo",
}

# Casos tomados directo de la sección "Criterios de aceptación" del documento
CASOS = [
    {
        "nombre": "1. Foto nítida",
        "imagen": "01-nitida_MDE-UTM-70341-KX.jpg",
        "codigo": "MDE-UTM-70341-KX",
        "esperado": "200, coincide=True",
    },
    {
        "nombre": "2. Foto borrosa",
        "imagen": "02-borrosa_MDE-UTM-88215-JT.jpg",
        "codigo": "MDE-UTM-88215-JT",
        "esperado": "422 (nunca coincide=True)",
    },
    {
        "nombre": "3. Ángulo pronunciado",
        "imagen": "03-angulo_MDE-UTM-15560-QR.jpg",
        "codigo": "MDE-UTM-15560-QR",
        "esperado": "coincide=True, o 422 si no se lee",
    },
    {
        "nombre": "4. Poca luz",
        "imagen": "04-poca-luz_MDE-UTM-29904-LW.jpg",
        "codigo": "MDE-UTM-29904-LW",
        "esperado": "422 o coincide=False (nunca True)",
    },
    {
        "nombre": "5. Reflejo en la etiqueta",
        "imagen": "05-reflejo_MDE-UTM-63712-AB.jpg",
        "codigo": "MDE-UTM-63712-AB",
        "esperado": "coincide=True, o 422 si no se lee",
    },
    {
        "nombre": "6. Código distinto a propósito",
        "imagen": "01-nitida_MDE-UTM-70341-KX.jpg",
        "codigo": "MDE-UTM-00000-ZZ",
        "esperado": "200, coincide=False",
    },
    {
        "nombre": "7. Borrosa de verdad (desenfoque fuerte)",
        "imagen": "07-borrosa-real_MDE-UTM-88215-JT.jpg",
        "codigo": "MDE-UTM-88215-JT",
        "esperado": "422 (nunca coincide=True)",
    },
    {
        "nombre": "8. Peso no numérico (error esperado)",
        "imagen": "01-nitida_MDE-UTM-70341-KX.jpg",
        "codigo": "MDE-UTM-70341-KX",
        "esperado": "400 (peso en vacío inválido)",
        # Este caso pisa el peso_vacio de ejemplo con texto no numérico
        # a propósito, para probar la validación nueva de main.py.
        "datos_dron_extra": {"peso_vacio": "no-es-un-numero"},
    },
    {
        "nombre": "9. MTOW menor que peso en vacío (error esperado)",
        "imagen": "01-nitida_MDE-UTM-70341-KX.jpg",
        "codigo": "MDE-UTM-70341-KX",
        "esperado": "400 (MTOW < peso en vacío)",
        "datos_dron_extra": {"peso_vacio": "2.0", "peso_mtow": "1.0"},
    },
    {
        "nombre": "10. Falta categoria_uso (error esperado)",
        "imagen": "01-nitida_MDE-UTM-70341-KX.jpg",
        "codigo": "MDE-UTM-70341-KX",
        "esperado": "400 (categoria_uso es obligatorio)",
        "datos_dron_extra": {"categoria_uso": ""},
    },
    {
        "nombre": "11. estado_registro con valor inválido (error esperado)",
        "imagen": "01-nitida_MDE-UTM-70341-KX.jpg",
        "codigo": "MDE-UTM-70341-KX",
        "esperado": "400 (estado_registro fuera de la lista)",
        "datos_dron_extra": {"estado_registro": "Suspendido"},
    },
]


def correr_caso(caso):
    ruta_imagen = IMG_DIR / caso["imagen"]
    if not ruta_imagen.exists():
        return None, f"ERROR: no encontré la imagen en {ruta_imagen}"

    # Arrancamos con los datos de ejemplo del dron y, si el caso trae
    # "datos_dron_extra" (como los casos 8 y 9), los pisamos encima para
    # forzar el valor que queremos probar en ese caso puntual.
    datos_dron = {**DATOS_DRON_EJEMPLO, **caso.get("datos_dron_extra", {})}

    with open(ruta_imagen, "rb") as f:
        files = {"imagen": (caso["imagen"], f, "image/jpeg")}
        data = {"codigo": caso["codigo"], **datos_dron}
        headers = {"x-api-key": API_KEY or ""}
        try:
            resp = requests.post(API_URL, data=data, files=files, headers=headers, timeout=30)
        except requests.exceptions.ConnectionError:
            return None, "ERROR: no se pudo conectar al backend (¿está corriendo uvicorn en el puerto 8000?)"
    return resp, None


def formatear_resultado(resp):
    if resp.status_code == 422:
        return "422 (imagen no legible)"
    if resp.status_code == 200:
        body = resp.json()
        return (
            f"200  coincide={body.get('coincide')}  "
            f"confianza={body.get('confianza', 0):.2f}  "
            f"leido='{body.get('serial_leido')}'"
        )
    try:
        detalle = resp.json().get("detail", resp.text[:80])
    except Exception:
        detalle = resp.text[:80]
    return f"{resp.status_code}: {detalle}"


def main():
    if not API_KEY:
        print("No encontré API_KEY en el .env. Corré este script parado dentro de la carpeta backend.")
        sys.exit(1)

    if not IMG_DIR.exists():
        print(f"No encontré la carpeta de imágenes en: {IMG_DIR}")
        sys.exit(1)

    print(f"{'Caso':42} | {'Esperado (documento)':32} | Resultado real")
    print("-" * 120)
    for caso in CASOS:
        resp, error = correr_caso(caso)
        resultado = error if error else formatear_resultado(resp)
        print(f"{caso['nombre']:42} | {caso['esperado']:32} | {resultado}")


if __name__ == "__main__":
    main()
