"""Consultas bloqueables para habilitar una cuenta SUPERADMIN existente."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User
from app.models.user_company import UserCompany


class SuperadminBootstrapRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_with_global_role(
        self,
        email: str,
        *,
        for_update: bool = False,
    ) -> tuple[User, Role] | None:
        statement = (
            select(User, Role)
            .join(Role, Role.id_rol == User.id_rol)
            .where(func.lower(User.correo) == email.lower())
        )
        if for_update:
            statement = statement.with_for_update(of=User)
        row = self.db.execute(statement).one_or_none()
        return (row[0], row[1]) if row is not None else None

    def get_active_role(self, name: str) -> Role | None:
        return self.db.scalar(
            select(Role).where(
                func.upper(Role.nombre) == name.upper(),
                Role.estado.is_(True),
            )
        )

    def has_active_admin_membership(self, user_id: int) -> bool:
        statement = (
            select(UserCompany.id_usuario)
            .join(Role, Role.id_rol == UserCompany.id_rol)
            .where(
                UserCompany.id_usuario == user_id,
                UserCompany.estado == "ACTIVO",
                func.upper(Role.nombre) == "ADMINISTRADOR",
                Role.estado.is_(True),
            )
            .limit(1)
        )
        return self.db.scalar(statement) is not None

    def assign_global_role(self, user: User, role: Role) -> None:
        user.id_rol = role.id_rol
        self.db.flush()
