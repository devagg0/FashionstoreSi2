"""Crea manualmente la primera cuenta administradora de FashionStore."""

import getpass
import re

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _request_credentials() -> tuple[str, str, str, str] | None:
    try:
        nombre = input("Nombre: ").strip()
        apellido = input("Apellido: ").strip()
        correo = input("Correo: ").strip().lower()
        password = getpass.getpass("Contraseña: ")
        confirmation = getpass.getpass("Confirmar contraseña: ")
    except (EOFError, KeyboardInterrupt):
        print("\nOperación cancelada. No se insertó ningún registro.")
        return None

    errors: list[str] = []
    if not nombre:
        errors.append("El nombre no puede estar vacío.")
    if not apellido:
        errors.append("El apellido no puede estar vacío.")
    if not correo:
        errors.append("El correo no puede estar vacío.")
    elif EMAIL_PATTERN.fullmatch(correo) is None:
        errors.append("El formato del correo no es válido.")
    if password != confirmation:
        errors.append("La contraseña y su confirmación no coinciden.")
    if len(password) < 8:
        errors.append("La contraseña debe tener al menos 8 caracteres.")

    if errors:
        print("No se creó el administrador:")
        for error in errors:
            print(f"- {error}")
        return None

    return nombre, apellido, correo, password


def create_admin() -> None:
    credentials = _request_credentials()
    if credentials is None:
        return

    nombre, apellido, correo, password = credentials
    del credentials

    session = SessionLocal()

    try:
        admin_role = session.scalar(
            select(Role).where(Role.nombre == "ADMINISTRADOR")
        )
        if admin_role is None:
            print(
                "No existe el rol ADMINISTRADOR. "
                "Ejecute primero: python -m scripts.seed_base"
            )
            return

        existing_user = session.scalar(
            select(User).where(func.lower(User.correo) == correo)
        )
        if existing_user is not None:
            print(f"Ya existe un usuario con el correo {correo}. No se creó otro.")
            return

        password_hash = hash_password(password)
        del password

        user = User(
            id_rol=admin_role.id_rol,
            nombre=nombre,
            apellido=apellido,
            correo=correo,
            password_hash=password_hash,
            estado=True,
        )
        session.add(user)

        session.commit()
        print(f"Administrador creado correctamente para el correo {correo}.")
    except Exception:
        session.rollback()
        print(
            "No se pudo crear el administrador. "
            "Se revirtió toda la transacción."
        )
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_admin()
