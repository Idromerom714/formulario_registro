from core.permisos import Rol, paginas_permitidas, puede_ver, rol_efectivo


def test_privileged_roles_override_profile_roles() -> None:
    assert rol_efectivo("autoridad", ["operador"], is_pilot=True, is_technician=False) == Rol.AUTORIDAD


def test_profile_roles_are_deduced_without_token_role() -> None:
    assert rol_efectivo(None, ["operador"], is_pilot=False, is_technician=False) == Rol.OPERADOR
    assert rol_efectivo(None, [], is_pilot=True, is_technician=False) == Rol.PILOTO
    assert rol_efectivo(None, [], is_pilot=False, is_technician=True) == Rol.TECNICO


def test_unknown_role_has_no_pages() -> None:
    assert paginas_permitidas("desconocido") == ()
    assert not puede_ver("piloto", "Cuentas")
