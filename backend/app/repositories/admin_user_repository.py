"""Persistencia para la gestión administrativa de usuarios y roles."""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.employee import Employee
from app.models.role import Role
from app.models.supplier import Supplier
from app.models.user import User


class AdminUserRepository:
    """Consultas de usuarios usadas exclusivamente por el caso de uso CU03."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _apply_user_filters(
        statement: Select,
        *,
        search: str | None,
        role: str | None,
        state: bool | None,
    ) -> Select:
        """Aplica los mismos filtros tanto al listado como al conteo."""
        if search:
            escaped_search = (
                search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            pattern = f"%{escaped_search}%"
            statement = statement.where(
                or_(
                    User.nombre.ilike(pattern, escape="\\"),
                    User.apellido.ilike(pattern, escape="\\"),
                    User.correo.ilike(pattern, escape="\\"),
                    (User.nombre + " " + User.apellido).ilike(
                        pattern,
                        escape="\\",
                    ),
                )
            )
        if role:
            statement = statement.where(
                func.upper(Role.nombre) == role.strip().upper()
            )
        if state is not None:
            statement = statement.where(User.estado.is_(state))

        return statement

    def list_users(
        self,
        *,
        search: str | None,
        role: str | None,
        state: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[User, str]], int]:
        """Lista usuarios con su rol real y devuelve el total filtrado."""
        filters = {"search": search, "role": role, "state": state}
        statement = self._apply_user_filters(
            select(User, Role.nombre).join(Role, User.id_rol == Role.id_rol),
            **filters,
        )
        count_statement = self._apply_user_filters(
            select(func.count(User.id_usuario)).join(
                Role,
                User.id_rol == Role.id_rol,
            ),
            **filters,
        )

        rows = self.db.execute(
            statement.order_by(User.id_usuario).offset(
                (page - 1) * page_size
            ).limit(page_size)
        ).all()
        total = self.db.scalar(count_statement) or 0
        return [(row[0], row[1]) for row in rows], total

    def get_user_with_role(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> tuple[User, str] | None:
        """Obtiene un usuario y su rol; opcionalmente bloquea la fila."""
        statement = select(User, Role.nombre).join(
            Role,
            User.id_rol == Role.id_rol,
        ).where(User.id_usuario == user_id)
        if for_update:
            statement = statement.with_for_update(of=User)

        row = self.db.execute(statement).one_or_none()
        return (row[0], row[1]) if row is not None else None

    def get_role_by_name(self, name: str) -> Role | None:
        """Busca el rol por nombre sin asumir ningún id_rol."""
        statement = select(Role).where(func.upper(Role.nombre) == name.upper())
        return self.db.scalar(statement)

    def list_roles(self) -> list[Role]:
        """Lista todos los roles configurados directamente en t_rol."""
        statement = select(Role).order_by(Role.nombre)
        return list(self.db.scalars(statement).all())

    def has_client_profile(self, user_id: int) -> bool:
        """Indica si el usuario posee un registro en t_cliente."""
        statement = select(Client.id_cliente).where(Client.id_usuario == user_id)
        return self.db.scalar(statement) is not None

    def has_employee_profile(self, user_id: int) -> bool:
        """Indica si el usuario posee un registro en t_empleado."""
        statement = select(Employee.id_empleado).where(
            Employee.id_usuario == user_id
        )
        return self.db.scalar(statement) is not None

    def has_supplier_profile(self, user_id: int) -> bool:
        """Indica si el usuario está asociado a un registro en t_proveedor."""
        statement = select(Supplier.id_proveedor).where(
            Supplier.id_usuario == user_id
        )
        return self.db.scalar(statement) is not None

    def create_employee(self, *, user_id: int) -> Employee:
        """Crea el perfil laboral sin sucursal dentro de la transacción actual."""
        employee = Employee(
            id_usuario=user_id,
            ci=None,
            cargo=None,
        )
        self.db.add(employee)
        self.db.flush()
        return employee

    def update_status(self, user: User, state: bool) -> None:
        """Prepara el cambio de estado sin confirmar la transacción."""
        user.estado = state
        self.db.flush()

    def update_role(self, user: User, role: Role) -> None:
        """Asigna el id obtenido de t_rol sin confirmar la transacción."""
        user.id_rol = role.id_rol
        self.db.flush()
