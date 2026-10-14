from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol, cast

import psycopg  # type: ignore[import-not-found]
from psycopg.rows import dict_row  # type: ignore[import-not-found]
from supabase import Client, create_client  # type: ignore[import-not-found]

from .config import Settings, get_settings


class UserClientFactory(Protocol):
    def __call__(self, access_token: str) -> Client: ...


def create_user_client(access_token: str, settings: Settings | None = None) -> Client:
    """Crea un cliente cuyo PostgREST usa exclusivamente el JWT del usuario."""
    config = settings or get_settings()
    client = create_client(config.supabase_url, config.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


@contextmanager
def backend_transaction(
    actor_id: str,
    actor_role: str | None,
    origin: str,
    settings: Settings | None = None,
) -> Iterator[psycopg.Cursor[Any]]:
    """Abre el único carril privilegiado y fija el contexto de auditoría."""
    if not actor_id or not origin:
        raise ValueError("El actor y el origen son obligatorios.")
    config = settings or get_settings()
    with (
        psycopg.connect(config.database_url, row_factory=dict_row) as connection,
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute("select set_config('app.actor_id', %s, true)", (actor_id,))
        cursor.execute("select set_config('app.actor_rol', %s, true)", (actor_role or "",))
        cursor.execute("select set_config('app.origen', %s, true)", (origin,))
        yield cursor


def execute_user_query(client: Client, table: str, *, columns: str = "*") -> list[dict[str, Any]]:
    """Consulta simple por RLS; no acepta nombres de tabla provenientes de formularios."""
    allowed_tables = {"organizaciones", "pilotos", "tecnicos", "uas", "planes_vuelo", "miembros_organizacion"}
    if table not in allowed_tables:
        raise ValueError("Tabla no permitida para consulta de usuario.")
    return cast(list[dict[str, Any]], client.table(table).select(columns).execute().data or [])
