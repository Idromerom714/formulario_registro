"""
API de Verificación de Serial de Dron — backend
=================================================

Qué hace este archivo, en una frase: recibe una foto + un código escrito
por el usuario, le pide a un modelo de IA (vía OpenRouter) que lea el
texto de la foto, compara ese texto contra el código escrito, y responde
si coinciden o no. Además, recibe (y guarda en el log) los datos de
registro del dron que todavía no vienen de la foto: marca, modelo, peso,
categoría, etc.

Flujo completo de una petición (ver función verificar_serial más abajo):
  1. Revisar que quien llama tenga la API_KEY correcta (seguridad).
  2. Revisar que el archivo sea jpg/png y no pese más de la cuenta.
  3. Validar los campos numéricos opcionales (peso en vacío y MTOW).
  4. Mandarle la imagen a OpenRouter y pedirle que lea el serial.
  5. Si no se pudo leer nada con sentido -> 422 (foto no legible).
  6. Normalizar los dos textos (mayúsculas, sin símbolos) y compararlos
     con un porcentaje de similitud (Levenshtein).
  7. Guardar el intento en el log técnico (con todos los datos de registro).
  8. Responder con el resultado.
"""

import base64
import os
import re
import httpx
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from rapidfuzz import fuzz
from logger import log_intento

# load_dotenv() lee el archivo .env (que vos creaste a mano) y mete esas
# variables en el entorno del proceso, como si las hubieras exportado en
# la terminal. Por eso después podemos usar os.getenv("ALGO").
load_dotenv()

# Esta es la aplicación FastAPI en sí. "app" es el objeto que uvicorn
# busca cuando corrés "uvicorn main:app" — main.py, variable app.
app = FastAPI(title="API Verificación de Serial de Dron")

# --- Seguridad del endpoint ---------------------------------------------
# APIKeyHeader le dice a FastAPI: "voy a exigir un header HTTP llamado
# x-api-key". auto_error=False significa que si no viene el header, no
# tira error solo: dejamos que nuestra función get_api_key decida qué
# hacer (así controlamos nosotros el mensaje de error).
API_KEY_NAME = "x-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# --- Variables de entorno -------------------------------------------------
# Todas estas vienen del archivo .env, NUNCA están escritas fijas en el
# código. El segundo argumento de os.getenv es el valor por defecto si
# la variable no existiera.
API_KEY = os.getenv("API_KEY", "default-secret-key")       # protege el endpoint
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")        # credencial de OpenRouter
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.92"))  # umbral de similitud (0 a 1)
MAX_FILE_SIZE_MB = float(os.getenv("MAX_FILE_SIZE_MB", "10"))  # tamaño máximo de imagen
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")  # dominios permitidos (CORS)

# --- OpenRouter ----------------------------------------------------------
# OpenRouter es un "proxy" que da acceso a varios modelos de IA (de
# distintos proveedores) con una sola API key y un formato de petición
# compatible con la API de OpenAI. Acá usamos el mismo modelo que ya
# viene usando el módulo del compañero, para no depender de dos cuentas
# distintas en el equipo.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "qwen/qwen3.7-flash"

# --- CORS --------------------------------------------------------------
# CORS es la regla del navegador que dice "qué páginas web tienen permiso
# de llamar a esta API desde JavaScript". Sin esto, el frontend (que vive
# en otro puerto, ej. localhost:5501) no podría hablarle al backend
# (localhost:8000) porque el navegador bloquearía la petición.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # lista de orígenes permitidos (viene del .env)
    allow_credentials=True,
    allow_methods=["*"],             # permite POST, GET, etc.
    allow_headers=["*"],             # permite headers como x-api-key
)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    """
    Esto es una "dependencia" de FastAPI: una función que se ejecuta ANTES
    del código del endpoint. Si lanza una excepción, el endpoint ni
    siquiera llega a correr. Acá comparamos el header que mandó el
    frontend contra la API_KEY que configuramos en el .env; si no
    coinciden, cortamos la petición con 403 (prohibido).
    """
    if api_key_header != API_KEY:
        raise HTTPException(status_code=403, detail="No autorizado")
    return api_key_header


def normalizar_texto(texto: str) -> str:
    """
    Regla de normalización del documento: pasar a mayúsculas y quitar
    todo lo que no sea letra o número (espacios, guiones, dos puntos...).
    Así "MDE-UTM-70341-KX" y "mde utm 70341 kx" terminan siendo
    exactamente el mismo texto para la comparación: "MDEUTM70341KX".
    """
    texto = str(texto).upper()
    return re.sub(r"[^A-Z0-9]", "", texto)


def leer_serial_con_openrouter(file_bytes: bytes, content_type: str) -> str:
    """
    Le manda la imagen a un modelo de visión a través de OpenRouter y le
    pide que devuelva SOLO el texto del serial, nada más.

    Por qué está en su propia función: así, si el día de mañana cambian
    de proveedor otra vez, solo hay que tocar esta función — el resto del
    endpoint (normalizar, comparar, loguear) no se entera de qué IA se
    usó para leer la foto.
    """
    # OpenRouter (como la mayoría de APIs de chat con imágenes) no acepta
    # el archivo binario directo: hay que codificarlo en base64 y armar
    # una URL de datos ("data URL") con el tipo de imagen adelante.
    encoded_image = base64.b64encode(file_bytes).decode("ascii")
    data_url = f"data:{content_type};base64,{encoded_image}"

    prompt = (
        "Extrae únicamente el número de serie (serial) del dron que aparece "
        "en la imagen. Responde sólo con el texto del código, sin "
        "explicaciones ni caracteres adicionales."
    )

    request_body = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0,  # 0 = respuestas lo más consistentes/deterministas posible
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60) as client:
        response = client.post(OPENROUTER_URL, headers=headers, json=request_body)
        response.raise_for_status()  # lanza una excepción si OpenRouter responde error (4xx/5xx)
        payload = response.json()

    # La respuesta de OpenRouter viene en el mismo formato que la API de
    # OpenAI: una lista de "choices", cada una con un mensaje de texto.
    return payload["choices"][0]["message"]["content"].strip()


# Valores permitidos para los dos campos que SÍ ya tienen lista oficial
# (vinieron del documento de referencia del profesor). Mientras
# "tipo_arquitectura" sigue sin lista definida y por eso queda como texto
# libre, estos dos ya se validan contra un conjunto cerrado de opciones.
CATEGORIAS_USO_VALIDAS = ["Profesional", "Comercial", "Recreativo", "Servicio público"]
ESTADOS_REGISTRO_VALIDOS = ["Activo", "Inactivo"]


def validar_peso(valor: str | None, nombre_campo: str) -> float | None:
    """
    Convierte un campo de peso (que llega como texto desde el formulario)
    a número decimal, si es que vino con algo escrito.

    Por qué existe esta función aparte: tanto "peso en vacío" como
    "MTOW" necesitan exactamente la misma validación, así que en vez de
    repetir el mismo try/except dos veces, lo dejamos en un solo lugar.

    Devuelve None si el campo vino vacío (es opcional por ahora, mientras
    no estén definidas las listas oficiales de selección). Si vino con
    algo que no se puede convertir a número, corta la petición con 400.
    """
    if valor is None or valor.strip() == "":
        return None
    try:
        return float(valor)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{nombre_campo} debe ser un número (en kg).")


# @app.post(...) registra esta función como la que atiende
# POST /api/v1/verificar-serial. FastAPI arma automáticamente el
# multipart/form-data a partir de los parámetros: "codigo" como texto del
# formulario y "imagen" como archivo subido.
@app.post("/api/v1/verificar-serial")
async def verificar_serial(
    codigo: str = Form(...),
    imagen: UploadFile = File(...),
    api_key: str = Depends(get_api_key),  # esto ejecuta get_api_key antes de seguir

    # --- Datos de registro del dron (nuevos) ---------------------------
    # marca, modelo, tipo_arquitectura y los pesos siguen OPCIONALES:
    # todavía no tenemos la lista oficial de valores permitidos para
    # "tipo de arquitectura", así que por ahora es texto libre.
    marca: str | None = Form(default=None),
    modelo: str | None = Form(default=None),
    tipo_arquitectura: str | None = Form(default=None),
    peso_vacio: str | None = Form(default=None),       # texto; se valida como número más abajo
    peso_mtow: str | None = Form(default=None),         # texto; se valida como número más abajo

    # categoria_uso y estado_registro YA tienen lista oficial (vino del
    # documento de referencia), así que son obligatorios EN LOS HECHOS —
    # pero los dejamos como Form(default=None), igual que los demás, y
    # los validamos nosotros mismos más abajo con un 400 propio. Por qué
    # no usar Form(...) (obligatorio "de fábrica" como en "codigo"): si
    # FastAPI detecta que falta un campo obligatorio, corta la petición
    # ANTES de que nuestro código corra y responde con SU PROPIO 422 (con
    # otro formato de mensaje) — y en este proyecto el 422 está reservado
    # a propósito para un solo caso: "la imagen no es legible". Validando
    # nosotros mismos evitamos esa mezcla y mandamos siempre 400, nunca un
    # 422 con un significado distinto al que espera el frontend.
    categoria_uso: str | None = Form(default=None),
    estado_registro: str | None = Form(default=None),

    # Las casillas de equipamiento mandan varios valores con el mismo
    # "name" (ver frontend), por eso esto es una lista y no un texto.
    equipamiento: list[str] = Form(default=[]),
):
    # --- Paso 1: validar tipo de archivo (seguridad / documento) ---
    # Solo aceptamos jpg o png. Content-Type lo manda el navegador según
    # el archivo que el usuario eligió.
    if imagen.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=400, detail="Formato de archivo no soportado. Usa JPG o PNG.")

    # --- Paso 2: validar tamaño del archivo ---
    # imagen.read() carga el archivo completo en memoria como bytes.
    file_bytes = await imagen.read()
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:  # MB a bytes
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo permitido.")

    # --- Paso 3: validar los campos de peso (si vinieron con algo) ---
    # validar_peso ya corta con 400 si lo que vino no es un número.
    peso_vacio_kg = validar_peso(peso_vacio, "El peso en vacío")
    peso_mtow_kg = validar_peso(peso_mtow, "El Peso Máximo al Despegue (MTOW)")

    # Chequeo de sentido común: si vinieron los dos pesos, el MTOW no
    # puede ser menor que el peso en vacío (un dron no puede despegar
    # pesando menos de lo que pesa vacío). Si el día de mañana no querés
    # esta regla, basta con borrar este "if".
    if peso_vacio_kg is not None and peso_mtow_kg is not None and peso_mtow_kg < peso_vacio_kg:
        raise HTTPException(
            status_code=400,
            detail="El Peso Máximo al Despegue (MTOW) no puede ser menor que el peso en vacío.",
        )

    # --- Paso 3b: validar categoría de uso y estado de registro ---
    # Estos dos son obligatorios y además tienen lista cerrada de valores
    # válidos. Primero chequeamos que no vengan vacíos, y después que lo
    # que vino esté en la lista (por ejemplo, alguien manda la petición a
    # mano con "Militar", que no es una opción) — los dos casos cortan
    # con 400, nunca con el 422 que está reservado para "imagen no legible".
    if not categoria_uso or not categoria_uso.strip():
        raise HTTPException(status_code=400, detail="categoria_uso es obligatorio.")
    if categoria_uso not in CATEGORIAS_USO_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"categoria_uso debe ser una de: {', '.join(CATEGORIAS_USO_VALIDAS)}.",
        )
    if not estado_registro or not estado_registro.strip():
        raise HTTPException(status_code=400, detail="estado_registro es obligatorio.")
    if estado_registro not in ESTADOS_REGISTRO_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"estado_registro debe ser uno de: {', '.join(ESTADOS_REGISTRO_VALIDOS)}.",
        )

    if not OPENROUTER_API_KEY:
        # Esto protege contra un despliegue mal configurado: si a alguien
        # se le olvidó poner la clave de OpenRouter en el .env, preferimos
        # fallar claro con 500 en vez de que el programa explote más feo.
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY no configurada.")

    # --- Paso 4: pedirle a OpenRouter que lea el texto de la foto ---
    try:
        texto_detectado = leer_serial_con_openrouter(file_bytes, imagen.content_type)
    except Exception as e:
        # Cualquier falla llamando a OpenRouter (API caída, timeout, clave
        # inválida, etc.) la convertimos en un 500 con el motivo. Nota
        # para más adelante: exponer str(e) tal cual al cliente es
        # cómodo para depurar ahora, pero en producción conviene
        # loguearlo internamente y mandar un mensaje genérico al usuario.
        raise HTTPException(status_code=500, detail=f"Error interno del servicio de IA: {str(e)}")

    # --- Paso 5: regla de los 6 caracteres mínimos (documento) ---
    # Si el texto que leyó el modelo es muy corto, asumimos que la imagen
    # no se pudo leer bien. Respondemos 422, NUNCA "coincide: false" —
    # son casos distintos: 422 es "no pude leer la foto", false es
    # "leí la foto pero no coincide con lo escrito".
    texto_limpio = texto_detectado.strip()
    if len(texto_limpio) < 6:
        log_intento(
            codigo, texto_detectado, 0.0, "422", "La imagen no tiene texto legible (menos de 6 caracteres).",
            marca=marca, modelo=modelo, tipo_arquitectura=tipo_arquitectura,
            peso_vacio_kg=peso_vacio_kg, peso_mtow_kg=peso_mtow_kg,
            categoria_uso=categoria_uso, estado_registro=estado_registro,
            equipamiento=equipamiento,
        )
        raise HTTPException(status_code=422, detail="La imagen no tiene texto legible (foto borrosa, mal enfocada, etc.)")

    # --- Paso 6: normalizar y comparar ---
    codigo_norm = normalizar_texto(codigo)
    serial_norm = normalizar_texto(texto_detectado)

    # Segunda revisión de longitud mínima, esta vez DESPUÉS de normalizar.
    # Por qué hace falta además de la de arriba: si el modelo devolviera
    # algo como "- - - -" (puros símbolos), pasaría la revisión del texto
    # crudo (son más de 6 caracteres) pero al normalizar quedaría vacío o
    # casi vacío. Esta segunda revisión atrapa ese caso raro.
    if len(serial_norm) < 6:
        log_intento(
            codigo, texto_detectado, 0.0, "422", "El texto extraído normalizado tiene menos de 6 caracteres.",
            marca=marca, modelo=modelo, tipo_arquitectura=tipo_arquitectura,
            peso_vacio_kg=peso_vacio_kg, peso_mtow_kg=peso_mtow_kg,
            categoria_uso=categoria_uso, estado_registro=estado_registro,
            equipamiento=equipamiento,
        )
        raise HTTPException(status_code=422, detail="La imagen no tiene texto legible (foto borrosa, mal enfocada, etc.)")

    # fuzz.ratio calcula qué tan parecidas son dos cadenas de texto y
    # devuelve un número de 0 a 100 (100 = idénticas). Lo dividimos entre
    # 100 para trabajar con 0 a 1, que es como está expresado el umbral.
    similitud_porcentaje = fuzz.ratio(codigo_norm, serial_norm) / 100.0

    # La decisión final: ¿la similitud alcanza el umbral configurado?
    coincide = similitud_porcentaje >= MATCH_THRESHOLD
    mensaje = "" if coincide else "La foto no coincide con el código escrito, por favor sube otra."

    # --- Paso 7: log técnico de cada intento (documento) ---
    # Esto pasa siempre, haya coincidido o no, porque el documento pide
    # poder auditar todos los intentos más adelante (no solo los que
    # fallan). Se guarda en un archivo aparte (verificaciones.log), no en
    # la futura base de datos de fase 2. Ahora también se guardan los
    # datos de registro del dron, no solo el resultado de la comparación.
    log_intento(
        codigo_escrito=codigo,
        serial_leido=texto_detectado,
        similitud=similitud_porcentaje,
        resultado="true" if coincide else "false",
        motivo="",
        marca=marca, modelo=modelo, tipo_arquitectura=tipo_arquitectura,
        peso_vacio_kg=peso_vacio_kg, peso_mtow_kg=peso_mtow_kg,
        categoria_uso=categoria_uso, estado_registro=estado_registro,
        equipamiento=equipamiento,
    )

    # --- Paso 8: responder ---
    # Los primeros 4 campos son exactamente los que define el documento
    # para la respuesta de este endpoint. "datos_registrados" es nuevo:
    # devuelve tal cual lo que se recibió, para que el frontend (o quien
    # consuma la API) pueda confirmar qué quedó guardado en el log.
    return {
        "coincide": coincide,
        "serial_leido": texto_detectado,
        "confianza": similitud_porcentaje,
        "mensaje": mensaje,
        "datos_registrados": {
            "marca": marca,
            "modelo": modelo,
            "tipo_arquitectura": tipo_arquitectura,
            "peso_vacio_kg": peso_vacio_kg,
            "peso_mtow_kg": peso_mtow_kg,
            "categoria_uso": categoria_uso,
            "estado_registro": estado_registro,
            "equipamiento": equipamiento,
        },
    }
