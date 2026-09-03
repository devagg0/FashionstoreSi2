"""Utilidades reutilizables para el manejo seguro de contraseñas."""

from pwdlib import PasswordHash


_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Genera un hash seguro de la contraseña usando Argon2."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Comprueba una contraseña contra un hash previamente almacenado."""
    return _password_hash.verify(password, hashed_password)
