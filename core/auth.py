from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from supabase import Client  # type: ignore[import-not-found]

from .config import Settings, get_settings
from .db import UserClientFactory, create_user_client


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    expires_at: int
    user_id: str
    email: str | None
    app_role: str | None
    aal: str | None

    @property
    def expires_soon(self) -> bool:
        return self.expires_at <= int(datetime.now(UTC).timestamp()) + 60


class AuthService:
    def __init__(
        self,
        client: Client,
        *,
        settings: Settings | None = None,
        user_client_factory: UserClientFactory = create_user_client,
    ) -> None:
        self.client: Any = client
        self.settings = settings or get_settings()
        self.user_client_factory = user_client_factory

    def sign_in(self, email: str, password: str) -> Session:
        response = self.client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        return self._session(response.session)

    def sign_up(self, email: str, password: str) -> Session | None:
        response = self.client.auth.sign_up({"email": email.strip(), "password": password})
        return self._session(response.session) if response.session else None

    def refresh(self, session: Session) -> Session:
        response = self.client.auth.refresh_session(session.refresh_token)
        return self._session(response.session)

    def verify_access_token(self, access_token: str) -> dict[str, Any]:
        """Supabase valida firma y expiración al resolver get_user con el token."""
        response = self.client.auth.get_user(access_token)
        if not response.user:
            raise ValueError("La sesión no es válida.")
        return dict(response.user.model_dump() if hasattr(response.user, "model_dump") else response.user)

    def client_for(self, session: Session) -> Client:
        current = self.refresh(session) if session.expires_soon else session
        return self.user_client_factory(current.access_token)

    def sign_out(self) -> None:
        self.client.auth.sign_out()

    def enroll_totp(self, name: str = "SUA") -> dict[str, Any]:
        factor = self.client.auth.mfa.enroll({"factor_type": "totp", "friendly_name": name})
        if hasattr(factor, "model_dump"):
            return dict(factor.model_dump())
        return dict(factor)

    def challenge_totp(self, factor_id: str) -> str:
        challenge = self.client.auth.mfa.challenge(factor_id)
        return str(challenge.id)

    def verify_totp(self, factor_id: str, challenge_id: str, code: str) -> Session:
        self.client.auth.mfa.verify(
            {"factor_id": factor_id, "challenge_id": challenge_id, "code": code.strip()}
        )
        current = self.client.auth.get_session()
        return self._session(current.session)

    def current_aal(self) -> str | None:
        response = self.client.auth.mfa.get_authenticator_assurance_level()
        return getattr(response, "current_level", None)

    def _session(self, value: Any) -> Session:
        if value is None or not value.access_token or not value.refresh_token or not value.user:
            raise ValueError("Supabase no devolvió una sesión autenticada.")
        metadata = value.user.app_metadata or {}
        return Session(
            access_token=value.access_token,
            refresh_token=value.refresh_token,
            expires_at=int(value.expires_at or 0),
            user_id=str(value.user.id),
            email=value.user.email,
            app_role=metadata.get("rol"),
            aal=getattr(value.user, "aal", None) or getattr(value, "aal", None),
        )


def mfa_required(session: Session, current_aal: str | None = None) -> bool:
    aal = current_aal or session.aal
    return session.app_role in {"admin", "autoridad", "auditor", "verificador"} and aal != "aal2"
