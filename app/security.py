"""Hash de contraseñas y tokens JWT de acceso."""
from datetime import datetime, timedelta, timezone
import secrets
from typing import Callable

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from app.config import Settings


password_hasher = PasswordHash.recommended()
DUMMY_HASH = password_hasher.hash("dummy-password")
REVOCATED_JTIS: set[str] = set()


def unauthorized_error() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas o token expirado.", headers={"WWW-Authenticate": "Bearer"})


def revoke_token(jti: str) -> None:
    REVOCATED_JTIS.add(jti)


def is_token_revoked(jti: str) -> bool:
    return jti in REVOCATED_JTIS


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    return password_hasher.verify(plain_password, hashed_password or DUMMY_HASH)


def create_token(user_id: int, settings: Settings) -> tuple[str, datetime, str]:
    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(24)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.token_minutes),
               "iss": settings.issuer, "aud": settings.audience, "jti": jti, "token_use": "access"}
    return jwt.encode(payload, settings.secret, algorithm="HS256"), now, jti


def read_subject(token: str, settings: Settings, check_revoked: Callable[[str], bool] = is_token_revoked) -> int:
    try:
        data = jwt.decode(token, settings.secret, algorithms=["HS256"], audience=settings.audience,
                          issuer=settings.issuer, options={"require": ["sub", "exp", "iat", "iss", "aud", "jti", "token_use"]})
        jti, subject = data.get("jti"), data.get("sub")
        if not secrets.compare_digest(str(data.get("token_use", "")), "access") or not isinstance(jti, str) or len(jti) != 32 or check_revoked(jti):
            raise ValueError("token inválido")
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdigit() or int(subject) < 1:
            raise ValueError("subject inválido")
        return int(subject)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, TypeError, ValueError, KeyError):
        raise unauthorized_error() from None
