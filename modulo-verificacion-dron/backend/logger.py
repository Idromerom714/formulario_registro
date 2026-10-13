"""
Logger técnico — guarda un registro de cada intento de verificación.

Por qué existe este archivo aparte y no se guarda directo en main.py:
separar la "lógica de negocio" (comparar serial) de la "infraestructura"
(cómo y dónde se escribe el log) hace el código más fácil de leer y de
cambiar después (por ejemplo, si un día querés mandar el log a una base
de datos en vez de un archivo, solo tocás este archivo).
"""

import logging
import json
from datetime import datetime  # importado pero no se usa directamente:
                                 # el formatter de abajo ya agrega la fecha
                                 # automáticamente con %(asctime)s.

# logging es la librería estándar de Python para mensajes de registro.
# getLogger("verificacion_dron") crea (o reutiliza) un logger con ese
# nombre; si varias partes del programa piden el logger con el mismo
# nombre, todas comparten la misma configuración.
logger = logging.getLogger('verificacion_dron')
logger.setLevel(logging.INFO)  # INFO = nivel normal de registro (ni debug ni solo errores)

# FileHandler es el "destino" del log: un archivo en disco llamado
# verificaciones.log, en la misma carpeta donde corrés uvicorn (backend).
# encoding='utf-8' evita problemas con tildes y ñ.
handler = logging.FileHandler('verificaciones.log', encoding='utf-8')
handler.setLevel(logging.INFO)

# El formatter define cómo se ve cada línea del archivo: fecha y hora
# primero, seguido del mensaje que nosotros armamos en log_intento().
formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)


def log_intento(
    codigo_escrito: str,
    serial_leido: str,
    similitud: float,
    resultado: str,
    motivo: str = '',
    # --- Datos de registro del dron (nuevos, todos opcionales) ---------
    # Mismos campos que recibe el endpoint en main.py. Se guardan tal
    # cual lleguen (pueden venir en None si el usuario no los llenó,
    # porque todavía son opcionales mientras no haya listas de selector
    # oficiales para categoría/tipo de uso/estado de registro).
    marca: str = None,
    modelo: str = None,
    tipo_arquitectura: str = None,
    peso_vacio_kg: float = None,
    peso_mtow_kg: float = None,
    categoria_uso: str = None,
    estado_registro: str = None,
    equipamiento: list = None,
):
    """
    Guarda una línea en verificaciones.log con los datos de un intento.

    Se guarda como JSON (en vez de texto suelto) a propósito: así es
    fácil de leer tanto para un humano como para un programa que más
    adelante quiera procesar el log automáticamente (por ejemplo, para
    contar cuántos 422 hubo en un día, o cuántos drones de una marca
    se registraron).
    """
    # equipamiento=None pasaría como "null" en el JSON; mejor dejarlo
    # como lista vacía para que sea consistente con lo que manda el
    # frontend cuando no se marca ninguna casilla.
    if equipamiento is None:
        equipamiento = []

    log_data = {
        'codigo_escrito': codigo_escrito,
        'serial_leido': serial_leido,
        'porcentaje_similitud': similitud,
        'resultado': resultado,   # "true" / "false" / "422"
        'motivo': motivo,         # solo se llena cuando resultado es "422"
        # --- Datos de registro del dron ---
        'marca': marca,
        'modelo': modelo,
        'tipo_arquitectura': tipo_arquitectura,
        'peso_vacio_kg': peso_vacio_kg,
        'peso_mtow_kg': peso_mtow_kg,
        'categoria_uso': categoria_uso,
        'estado_registro': estado_registro,
        'equipamiento': equipamiento,
    }
    # json.dumps convierte el diccionario a un string JSON de una sola
    # línea. ensure_ascii=False permite que tildes y ñ salgan legibles
    # en vez de como ñ.
    logger.info(json.dumps(log_data, ensure_ascii=False))
