from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Rol(StrEnum):
    PILOTO = "piloto"
    OPERADOR = "operador"
    TECNICO = "tecnico"
    AUTORIDAD = "autoridad"
    ADMIN = "admin"
    AUDITOR = "auditor"
    VERIFICADOR = "verificador"


PAGINAS_POR_ROL: dict[Rol, tuple[str, ...]] = {
    Rol.PILOTO: ("Control UTM", "Planes de vuelo", "UAS", "Registros", "Mantenimiento", "Ayuda", "Acerca"),
    Rol.OPERADOR: ("Control UTM", "Planes de vuelo", "UAS", "Registros", "Mantenimiento", "Ayuda", "Acerca"),
    Rol.TECNICO: ("Mantenimiento", "UAS", "Ayuda", "Acerca"),
    Rol.AUTORIDAD: ("Control UTM", "Planes de vuelo", "Aprobaciones", "Gestor GIS", "Objetos GIS", "Registros", "UAS", "Mantenimiento", "Ayuda", "Acerca"),
    Rol.ADMIN: ("Control UTM", "Planes de vuelo", "Aprobaciones", "Gestor GIS", "Objetos GIS", "Registros", "UAS", "Mantenimiento", "Cuentas", "Ayuda", "Acerca"),
    Rol.AUDITOR: ("Auditoría", "Ayuda", "Acerca"),
    Rol.VERIFICADOR: ("Verificaciones", "Ayuda", "Acerca"),
}


def paginas_permitidas(rol: str | Rol | None) -> tuple[str, ...]:
    try:
        return PAGINAS_POR_ROL[Rol(rol)] if rol is not None else ()
    except ValueError:
        return ()


def puede_ver(rol: str | Rol | None, pagina: str) -> bool:
    return pagina in paginas_permitidas(rol)


def rol_efectivo(app_role: str | None, member_roles: Iterable[str], *, is_pilot: bool, is_technician: bool) -> Rol | None:
    if app_role in {r.value for r in (Rol.ADMIN, Rol.AUTORIDAD, Rol.AUDITOR, Rol.VERIFICADOR)}:
        return Rol(app_role)
    if is_technician:
        return Rol.TECNICO
    roles = set(member_roles)
    if "admin_org" in roles:
        return Rol.OPERADOR
    if "operador" in roles or "despachador" in roles:
        return Rol.OPERADOR
    if is_pilot:
        return Rol.PILOTO
    return None
