"""Smoke test de RLS contra un proyecto Supabase de pruebas.

Variables requeridas:
SUPABASE_URL, SUPABASE_ANON_KEY, RLS_ALLOWED_URLS,
RLS_PILOTO_A_EMAIL, RLS_PILOTO_A_PASSWORD,
RLS_PILOTO_B_EMAIL, RLS_PILOTO_B_PASSWORD,
RLS_SIN_ROL_EMAIL, RLS_SIN_ROL_PASSWORD,
RLS_B_UAS_ID y RLS_B_PLAN_ID.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from supabase import Client, create_client  # type: ignore[import-not-found]


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Falta la variable {name}.")
    return value


def user_client(url: str, key: str, email_var: str, password_var: str) -> Client:
    client = create_client(url, key)
    session = client.auth.sign_in_with_password(
        {"email": required(email_var), "password": required(password_var)}
    ).session
    if session is None:
        raise RuntimeError(f"No fue posible iniciar sesión con {email_var}.")
    client.postgrest.auth(session.access_token)
    return client


def rows(client: Client, table: str, record_id: str) -> list[dict[str, Any]]:
    return list(client.table(table).select("id").eq("id", record_id).execute().data or [])


def main() -> int:
    url = required("SUPABASE_URL")
    allowed = {item.strip().rstrip("/") for item in required("RLS_ALLOWED_URLS").split(",") if item.strip()}
    if url.rstrip("/") not in allowed:
        raise RuntimeError("SUPABASE_URL no está en RLS_ALLOWED_URLS; prueba abortada.")
    key = required("SUPABASE_ANON_KEY")
    uas_id = required("RLS_B_UAS_ID")
    plan_id = required("RLS_B_PLAN_ID")

    piloto_a = user_client(url, key, "RLS_PILOTO_A_EMAIL", "RLS_PILOTO_A_PASSWORD")
    piloto_b = user_client(url, key, "RLS_PILOTO_B_EMAIL", "RLS_PILOTO_B_PASSWORD")
    sin_rol = user_client(url, key, "RLS_SIN_ROL_EMAIL", "RLS_SIN_ROL_PASSWORD")

    assert rows(piloto_b, "uas", uas_id), "El usuario B no ve su dron de prueba."
    assert rows(piloto_b, "planes_vuelo", plan_id), "El usuario B no ve su plan de prueba."
    assert not rows(piloto_a, "uas", uas_id), "Fallo RLS: A ve el dron de B."
    assert not rows(piloto_a, "planes_vuelo", plan_id), "Fallo RLS: A ve el plan de B."
    assert not rows(sin_rol, "uas", uas_id), "Fallo RLS: usuario sin rol ve el dron de B."
    assert not rows(sin_rol, "planes_vuelo", plan_id), "Fallo RLS: usuario sin rol ve el plan de B."
    print("RLS OK: A y el usuario sin rol no ven los recursos de B.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, AssertionError) as error:
        print(f"RLS FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
