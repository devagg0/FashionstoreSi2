"""Persistencia para CU03: asignar y consultar administrador de empresa."""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.role import Role
from app.models.user import User
from app.models.user_company import UserCompany


ADMIN_ROLE_NAME = "ADMINISTRADOR"
SUPERADMIN_ROLE_NAME = "SUPERADMIN"


class CompanyAdminRepository:
    """Consultas y modificaciones sobre empresas, usuarios y membresías SaaS."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_company(self, company_id: int) -> Company | None:
        """Obtiene la empresa directamente por su identificador."""
        return self.db.get(Company, company_id)

    def get_user_with_role(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> tuple[User, Role] | None:
        """Obtiene un usuario junto a su rol global asignado en t_usuario."""
        statement = (
            select(User, Role)
            .join(Role, Role.id_rol == User.id_rol)
            .where(User.id_usuario == user_id)
        )
        if for_update:
            statement = statement.with_for_update()
        row = self.db.execute(statement).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    def get_user_by_email(self, email: str) -> User | None:
        """Busca un usuario por correo electrónico insensible a mayúsculas."""
        statement = select(User).where(func.lower(User.correo) == email.strip().lower())
        return self.db.scalar(statement)

    def create_admin_user(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        password_hash: str,
        role_id: int,
        phone: str | None = None,
    ) -> User:
        """Crea un nuevo usuario con rol ADMINISTRADOR en t_usuario sin hacer commit."""
        user = User(
            nombre=first_name,
            apellido=last_name,
            correo=email.strip().lower(),
            password_hash=password_hash,
            id_rol=role_id,
            telefono=phone.strip() if phone else None,
            estado=True,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def get_role_by_name(self, name: str) -> Role | None:
        """Busca un rol por su nombre."""
        statement = select(Role).where(func.upper(Role.nombre) == name.upper())
        return self.db.scalar(statement)

    def get_other_company_ownership(
        self,
        user_id: int,
        exclude_company_id: int | None = None,
    ) -> UserCompany | None:
        """Verifica si el usuario ya es propietario/administrador principal de otra empresa."""
        statement = select(UserCompany).where(
            UserCompany.id_usuario == user_id,
            UserCompany.es_propietario.is_(True),
        )
        if exclude_company_id is not None:
            statement = statement.where(UserCompany.id_empresa != exclude_company_id)
        return self.db.scalars(statement).first()

    def get_assigned_admin(
        self,
        company_id: int,
    ) -> tuple[UserCompany, User, Role] | None:
        """Obtiene el administrador principal asignado a la empresa."""
        # 1. Prioriza membresía marcada como es_propietario = true
        owner_statement = (
            select(UserCompany, User, Role)
            .join(User, User.id_usuario == UserCompany.id_usuario)
            .join(Role, Role.id_rol == UserCompany.id_rol)
            .where(
                UserCompany.id_empresa == company_id,
                UserCompany.es_propietario.is_(True),
            )
        )
        owner_row = self.db.execute(owner_statement).one_or_none()
        if owner_row is not None:
            return owner_row[0], owner_row[1], owner_row[2]

        # 2. Fallback: primera membresía activa con rol ADMINISTRADOR
        admin_statement = (
            select(UserCompany, User, Role)
            .join(User, User.id_usuario == UserCompany.id_usuario)
            .join(Role, Role.id_rol == UserCompany.id_rol)
            .where(
                UserCompany.id_empresa == company_id,
                func.upper(Role.nombre) == ADMIN_ROLE_NAME,
                UserCompany.estado == "ACTIVO",
            )
            .order_by(UserCompany.created_at.asc())
        )
        fallback_row = self.db.execute(admin_statement).first()
        if fallback_row is not None:
            return fallback_row[0], fallback_row[1], fallback_row[2]

        return None

    def get_user_membership(
        self,
        company_id: int,
        user_id: int,
    ) -> UserCompany | None:
        """Obtiene la membresía específica de un usuario en una empresa."""
        return self.db.get(UserCompany, (company_id, user_id))

    def clear_existing_owner(
        self,
        company_id: int,
        *,
        exclude_user_id: int | None = None,
    ) -> None:
        """Desmarca el flag es_propietario para otros administradores de la empresa."""
        statement = select(UserCompany).where(
            UserCompany.id_empresa == company_id,
            UserCompany.es_propietario.is_(True),
        )
        if exclude_user_id is not None:
            statement = statement.where(UserCompany.id_usuario != exclude_user_id)

        existing_owners = self.db.scalars(statement).all()
        for owner in existing_owners:
            owner.es_propietario = False
            owner.updated_at = func.now()
        if existing_owners:
            self.db.flush()

    def save_admin_membership(
        self,
        *,
        company_id: int,
        user_id: int,
        role_id: int,
        state: str,
    ) -> UserCompany:
        """Crea o actualiza la membresía como ADMINISTRADOR y propietario."""
        membership = self.get_user_membership(company_id, user_id)
        if membership is not None:
            membership.id_rol = role_id
            membership.es_propietario = True
            membership.estado = state
            membership.updated_at = func.now()
        else:
            membership = UserCompany(
                id_empresa=company_id,
                id_usuario=user_id,
                id_rol=role_id,
                estado=state,
                es_propietario=True,
            )
            self.db.add(membership)

        self.db.flush()
        return membership

    def search_available_users(
        self,
        *,
        search: str | None = None,
        company_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[tuple[User, Role]], int]:
        """Busca usuarios activos ADMINISTRADOR no asignados como titulares a otra empresa."""
        other_owner_filter = [
            UserCompany.id_usuario == User.id_usuario,
            UserCompany.es_propietario.is_(True),
        ]
        if company_id is not None:
            other_owner_filter.append(UserCompany.id_empresa != company_id)

        other_owner_subquery = exists(
            select(1).select_from(UserCompany).where(*other_owner_filter)
        )

        statement = (
            select(User, Role)
            .join(Role, Role.id_rol == User.id_rol)
            .where(
                User.estado.is_(True),
                func.upper(Role.nombre) == ADMIN_ROLE_NAME,
                ~other_owner_subquery,
            )
        )
        count_statement = (
            select(func.count(User.id_usuario))
            .join(Role, Role.id_rol == User.id_rol)
            .where(
                User.estado.is_(True),
                func.upper(Role.nombre) == ADMIN_ROLE_NAME,
                ~other_owner_subquery,
            )
        )

        if search and search.strip():
            escaped = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            filter_condition = or_(
                User.nombre.ilike(pattern, escape="\\"),
                User.apellido.ilike(pattern, escape="\\"),
                User.correo.ilike(pattern, escape="\\"),
                (User.nombre + " " + User.apellido).ilike(pattern, escape="\\"),
            )
            statement = statement.where(filter_condition)
            count_statement = count_statement.where(filter_condition)

        total = self.db.scalar(count_statement) or 0
        rows = self.db.execute(
            statement.order_by(User.nombre.asc(), User.apellido.asc(), User.id_usuario.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return [(row[0], row[1]) for row in rows], total
