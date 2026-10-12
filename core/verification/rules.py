import re
import unicodedata

from .schemas import ExtraccionDocumento, ExtraccionSerial

CONFUSABLES = {"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"}


def normalizar_documento(valor: str | None) -> str:
    return "".join(char for char in (valor or "") if char.isdigit())


def normalizar_serial(valor: str | None) -> str:
    return re.sub(r"[\s-]", "", (valor or "").upper())


def normalizar_nombre(valor: str | None) -> str | None:
    if valor is None:
        return None
    sin_tildes = "".join(
        char
        for char in unicodedata.normalize("NFD", valor)
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(sin_tildes.upper().split())


def serial_es_ambiguo(ingresado: str, extraido: str) -> bool:
    if len(ingresado) != len(extraido) or ingresado == extraido:
        return False
    return all(
        left == right or CONFUSABLES.get(left) == right or CONFUSABLES.get(right) == left
        for left, right in zip(ingresado, extraido)
    )


def decidir_documento(ingresado: str, extraccion: ExtraccionDocumento, umbral: float) -> tuple[bool | None, str, str]:
    esperado = normalizar_documento(ingresado)
    obtenido = normalizar_documento(extraccion.numero_documento)
    coincide = bool(esperado and obtenido and esperado == obtenido)
    if not extraccion.legible or not obtenido:
        return coincide, "ilegible", normalizar_nombre(extraccion.nombres) or ""
    if not coincide:
        return False, "no_coincide", normalizar_nombre(extraccion.nombres) or ""
    if extraccion.confianza < umbral:
        return True, "confianza_baja", normalizar_nombre(extraccion.nombres) or ""
    if "numero_documento" in extraccion.campos_dudosos:
        return True, "campo_dudoso", normalizar_nombre(extraccion.nombres) or ""
    return True, "", normalizar_nombre(extraccion.nombres) or ""


def decidir_serial(ingresado: str, extraccion: ExtraccionSerial, umbral: float) -> tuple[bool | None, str]:
    esperado = normalizar_serial(ingresado)
    obtenido = normalizar_serial(extraccion.serial)
    coincide = bool(esperado and obtenido and esperado == obtenido)
    if coincide and extraccion.legible and extraccion.confianza >= umbral:
        return True, ""
    if esperado and obtenido and serial_es_ambiguo(esperado, obtenido):
        return False, "serial_ambiguo"
    if not extraccion.legible or not obtenido:
        return coincide, "ilegible"
    if not coincide:
        return False, "no_coincide"
    return True, "confianza_baja"