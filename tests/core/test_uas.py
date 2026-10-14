from datetime import date

import pytest

from core.services.uas import (
    NuevaAsignacion,
    NuevoUAS,
    validar_asignacion,
    validar_confirmacion_asignacion,
    validar_instalacion,
)


def test_new_uas_is_always_created_in_review() -> None:
    data = NuevoUAS("MED-001", "SN-1", "Fabricante", "Modelo", "org-1", None)
    assert data.matricula == "MED-001"


def test_assignment_dates_and_types_are_validated() -> None:
    with pytest.raises(ValueError, match="posterior"):
        validar_asignacion(NuevaAsignacion("uas", "org", "propio", date(2026, 1, 2), date(2026, 1, 1)))
    with pytest.raises(ValueError, match="Tipo"):
        validar_asignacion(NuevaAsignacion("uas", "org", "otro", date.today(), None))


def test_only_owner_can_confirm_assignment() -> None:
    assignment = {"estado": "pendiente"}
    uas = {"propietario_id": "owner"}
    validar_confirmacion_asignacion(assignment, uas, "owner")
    with pytest.raises(ValueError, match="propietaria"):
        validar_confirmacion_asignacion(assignment, uas, "operator")


def test_component_cannot_be_installed_on_two_drones() -> None:
    with pytest.raises(ValueError, match="otro dron"):
        validar_instalacion(
            {"uas_id": "uas-1", "propietario_id": "org"},
            "uas-2",
            "org",
        )
