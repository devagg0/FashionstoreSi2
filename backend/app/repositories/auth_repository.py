"""Acceso a datos necesario para las operaciones de autenticación."""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.password_recovery import PasswordRecovery
from app.models.role import Role
from app.models.user import User


class AuthRepository:
    """Consultas y operaciones de persistencia usadas por autenticación."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        """Busca un correo sin distinguir mayúsculas de minúsculas."""
        statement = select(User).where(func.lower(User.correo) == email.lower())
        return self.db.scalar(statement)

    def get_user_by_id(self, user_id: int) -> User | None:
        """Obtiene un usuario por el identificador recibido en el JWT."""
        return self.db.get(User, user_id)

    def get_role_by_id(self, role_id: int) -> Role | None:
        """Obtiene el rol real asociado al usuario desde t_rol."""
        return self.db.get(Role, role_id)

    def get_role_by_name(self, name: str) -> Role | None:
        """Obtiene un rol por su nombre, nunca por un identificador fijo."""
        statement = select(Role).where(Role.nombre == name)
        return self.db.scalar(statement)

    def create_user(
        self,
        *,
        role_id: int,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None,
        password_hash: str,
    ) -> User:
        """Prepara el usuario y obtiene su identificador sin hacer commit."""
        user = User(
            id_rol=role_id,
            nombre=first_name,
            apellido=last_name,
            correo=email,
            telefono=phone,
            password_hash=password_hash,
            estado=True,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def create_client(self, *, user_id: int) -> Client:
        """Prepara el perfil de cliente sin completar la transacción."""
        client = Client(
            id_usuario=user_id,
            fecha_nacimiento=None,
            genero=None,
        )
        self.db.add(client)
        return client

    def update_password_hash(self, user: User, password_hash: str) -> None:
        """Actualiza únicamente el hash de contraseña sin hacer commit."""
        user.password_hash = password_hash
        self.db.flush()

    def invalidate_pending_recoveries(self, user_id: int) -> None:
        """Invalida todos los códigos pendientes de un usuario sin hacer commit."""
        statement = (
            update(PasswordRecovery)
            .where(
                PasswordRecovery.id_usuario == user_id,
                PasswordRecovery.usado.is_(False),
            )
            .values(usado=True)
        )
        self.db.execute(statement)

    def create_password_recovery(
        self,
        *,
        user_id: int,
        code_hash: str,
        expires_at: datetime,
    ) -> PasswordRecovery:
        """Crea una recuperación pendiente y obtiene su identificador."""
        recovery = PasswordRecovery(
            id_usuario=user_id,
            codigo_hash=code_hash,
            intentos=0,
            usado=False,
            expira_en=expires_at,
        )
        self.db.add(recovery)
        self.db.flush()
        return recovery

    def get_latest_pending_recovery_for_update(
        self,
        user_id: int,
    ) -> PasswordRecovery | None:
        """Bloquea el código pendiente más reciente durante su verificación."""
        statement = (
            select(PasswordRecovery)
            .where(
                PasswordRecovery.id_usuario == user_id,
                PasswordRecovery.usado.is_(False),
            )
            .order_by(PasswordRecovery.id_recuperacion.desc())
            .limit(1)
            .with_for_update()
        )
        return self.db.scalar(statement)

    def get_password_recovery_for_update(
        self,
        recovery_id: int,
    ) -> PasswordRecovery | None:
        """Bloquea una recuperación específica durante el reset."""
        statement = (
            select(PasswordRecovery)
            .where(PasswordRecovery.id_recuperacion == recovery_id)
            .with_for_update()
        )
        return self.db.scalar(statement)

    def register_failed_recovery_attempt(
        self,
        recovery: PasswordRecovery,
        *,
        max_attempts: int,
    ) -> None:
        """Incrementa intentos e invalida el código al alcanzar el máximo."""
        recovery.intentos += 1
        if recovery.intentos >= max_attempts:
            recovery.usado = True
        self.db.flush()

    def prepare_recovery_for_reset(
        self,
        recovery: PasswordRecovery,
        *,
        invalidated_code_hash: str,
        expires_at: datetime,
    ) -> None:
        """Inutiliza el código verificado y abre la ventana temporal del reset."""
        recovery.codigo_hash = invalidated_code_hash
        recovery.expira_en = expires_at
        self.db.flush()

    def mark_recovery_as_used(self, recovery: PasswordRecovery) -> None:
        """Marca una recuperación como consumida sin hacer commit."""
        recovery.usado = True
        self.db.flush()
