"""Autenticacao simples: uma password -> cookie de sessao assinado."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Cookie, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import Settings

COOKIE = "plumbybit_session"
_SALT = "plumbybit-web-session"


class Auth:
    def __init__(self, settings: Settings):
        self.enabled = bool(settings.web_password)
        self.max_age = settings.web_session_hours * 3600
        self._pw = settings.web_password
        secret = settings.web_secret or (settings.web_password + "::fallback-secret")
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)

    def verify_password(self, password: str) -> bool:
        return self.enabled and hmac.compare_digest(
            hashlib.sha256(password.encode()).digest(),
            hashlib.sha256(self._pw.encode()).digest(),
        )

    def issue_token(self) -> str:
        return self._serializer.dumps({"sid": secrets.token_hex(8)})

    def valid(self, token: str | None) -> bool:
        if not self.enabled:
            return True
        if not token:
            return False
        try:
            self._serializer.loads(token, max_age=self.max_age)
            return True
        except (BadSignature, SignatureExpired):
            return False


def require_auth(auth: Auth):
    def _dep(plumbybit_session: str | None = Cookie(default=None)) -> None:
        if not auth.valid(plumbybit_session):
            raise HTTPException(status_code=401, detail="nao autenticado")

    return _dep
