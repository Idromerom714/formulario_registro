from typing import Any

import pytest

from core.services.registro_cuenta import RegistroCuenta, completar_registro


class Repository:
    def __init__(self) -> None:
        self.profile: dict[str, Any] | None = None
        self.creates = 0

    def find_profile(self, auth_user_id: str, tipo: str) -> dict[str, Any] | None:
        return self.profile

    def create_profile(self, auth_user_id: str, data: RegistroCuenta, *, organization_id: str | None) -> dict[str, Any]:
        self.creates += 1
        self.profile = {"id": "profile-1", "auth_user_id": auth_user_id}
        return self.profile


def data() -> RegistroCuenta:
    return RegistroCuenta(
        tipo="piloto",
        documento_tipo="CC",
        documento_numero="123",
        nombres="Ana",
        apellidos="Pérez",
        correo="ana@example.test",
        organizacion=None,
        consentimiento_version="C1-2026-01",
        consentimiento_texto="La imagen se procesa con un proveedor externo.",
    )


def test_registration_is_idempotent() -> None:
    repository = Repository()
    assert completar_registro("user-1", data(), repository)["id"] == "profile-1"
    assert completar_registro("user-1", data(), repository)["id"] == "profile-1"
    assert repository.creates == 1


def test_consent_must_mention_external_provider() -> None:
    repository = Repository()
    invalid = data()
    invalid = RegistroCuenta(**{**invalid.__dict__, "consentimiento_texto": "Acepto."})
    with pytest.raises(ValueError, match="proveedor externo"):
        completar_registro("user-1", invalid, repository)
