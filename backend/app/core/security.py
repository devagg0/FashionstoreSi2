"""Utilidades reutilizables para contraseñas y access tokens JWT."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import settings


_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Genera un hash seguro de la contraseña usando Argon2."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Comprueba una contraseña contra un hash previamente almacenado."""
    return _password_hash.verify(password, hashed_password)


def hash_recovery_code(code: str) -> str:
    """Protege un código corto con HMAC y un secreto fuera de la base de datos."""
    return hmac.new(
        settings.JWT_SECRET_KEY.get_secret_value().encode("utf-8"),
        f"fashionstore:password-recovery:{code}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_recovery_code(code: str, code_hash: str) -> bool:
    """Compara el código usando tiempo constante."""
    return hmac.compare_digest(hash_recovery_code(code), code_hash)


def create_access_token(
    *,
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Genera un JWT individual, firmado y con fechas expresadas en UTC."""
    issued_at = datetime.now(timezone.utc)
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    expires_at = issued_at + lifetime
    payload = {
        "sub": subject,
        "role": role,
        "iat": issued_at,
        "exp": expires_at,
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Valida firma, expiración y claims mínimos de un access token."""
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "role", "iat", "exp", "jti"]},
    )


def create_password_reset_token(
    *,
    subject: str,
    recovery_id: int,
    expires_delta: timedelta = timedelta(minutes=10),
) -> str:
    """Genera un JWT temporal que sólo puede usarse para restablecer contraseña."""
    issued_at = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "purpose": "password_reset",
        "recovery_id": recovery_id,
        "iat": issued_at,
        "exp": issued_at + expires_delta,
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_password_reset_token(token: str) -> dict[str, Any]:
    """Valida firma, expiración y propósito de un reset token."""
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithms=[settings.JWT_ALGORITHM],
        options={
            "require": [
                "sub",
                "purpose",
                "recovery_id",
                "iat",
                "exp",
                "jti",
            ]
        },
    )
    if payload.get("purpose") != "password_reset":
        raise jwt.InvalidTokenError("Invalid token purpose")

    return payload
