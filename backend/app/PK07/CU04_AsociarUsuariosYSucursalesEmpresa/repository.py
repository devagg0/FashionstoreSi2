"""Persistencia para PK07 / CU04: Asociar usuarios y sucursales a empresa."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.city import City
from app.models.client import Client
from app.models.company import Company
from app.models.employee import Employee
from app.models.role import Role
from app.models.user import User
from app.models.user_company import UserCompany


class CompanyResourcesRepository:
    """Consultas y modificaciones para usuarios, sucursales y membresías empresariales."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_company(self, company_id: int) -> Company | None:
        """Obtiene la empresa directamente por su identificador primario."""
        return self.db.get(Company, company_id)

    def get_user(self, user_id: int) -> User | None:
        """Obtiene un usuario por su identificador primario."""
        return self.db.get(User, user_id)

    def get_user_with_role(self, user_id: int) -> tuple[User, Role] | None:
        """Obtiene un usuario junto a su rol global en t_usuario."""
        statement = (
            select(User, Role)
            .join(Role, Role.id_rol == User.id_rol)
            .where(User.id_usuario == user_id)
        )
        row = self.db.execute(statement).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    def get_role_by_name(self, name: str) -> Role | None:
        """Busca un rol en t_rol por su nombre en mayúsculas."""
        statement = select(Role).where(func.upper(Role.nombre) == name.upper())
        return self.db.scalar(statement)

    def get_role_by_id(self, role_id: int) -> Role | None:
        """Obtiene un rol por su identificador primario."""
        return self.db.get(Role, role_id)

    def list_company_users(
        self,
        company_id: int,
        *,
        role_name: str | None = None,
        state: str | None = None,
        search: str | None = None,
    ) -> list[tuple[UserCompany, User, Role]]:
        """Lista usuarios asociados a la empresa con filtros opcionales."""
        statement = (
            select(UserCompany, User, Role)
            .join(User, User.id_usuario == UserCompany.id_usuario)
            .join(Role, Role.id_rol == UserCompany.id_rol)
            .where(UserCompany.id_empresa == company_id)
        )
        if role_name:
            statement = statement.where(func.upper(Role.nombre) == role_name.upper())
        if state:
            statement = statement.where(UserCompany.estado == state.upper())
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(
                    func.lower(User.nombre).like(term),
                    func.lower(User.apellido).like(term),
                    func.lower(User.correo).like(term),
                )
            )
        statement = statement.order_by(
            UserCompany.es_propietario.desc(),
            User.apellido.asc(),
            User.nombre.asc(),
        )
        rows = self.db.execute(statement).all()
        return [(row[0], row[1], row[2]) for row in rows]

    def get_user_membership(
        self,
        company_id: int,
        user_id: int,
    ) -> UserCompany | None:
        """Busca la membresía de un usuario en una empresa específica."""
        statement = select(UserCompany).where(
            UserCompany.id_empresa == company_id,
            UserCompany.id_usuario == user_id,
        )
        return self.db.scalar(statement)

    def save_user_membership(
        self,
        *,
        company_id: int,
        user_id: int,
        role_id: int,
        state: str = "ACTIVO",
        es_propietario: bool = False,
    ) -> UserCompany:
        """Crea o actualiza la membresía empresarial sin hacer commit."""
        membership = self.get_user_membership(company_id, user_id)
        if membership is None:
            membership = UserCompany(
                id_empresa=company_id,
                id_usuario=user_id,
                id_rol=role_id,
                estado=state,
                es_propietario=es_propietario,
            )
            self.db.add(membership)
        else:
            membership.id_rol = role_id
            membership.estado = state
            membership.es_propietario = es_propietario
        self.db.flush()
        return membership

    def clear_existing_owner(self, company_id: int, exclude_user_id: int | None = None) -> None:
        """Garantiza que solo exista un propietario activo en la empresa."""
        statement = select(UserCompany).where(
            UserCompany.id_empresa == company_id,
            UserCompany.es_propietario.is_(True),
        )
        if exclude_user_id is not None:
            statement = statement.where(UserCompany.id_usuario != exclude_user_id)
        previous_owners = self.db.scalars(statement).all()
        for owner in previous_owners:
            owner.es_propietario = False
        if previous_owners:
            self.db.flush()

    def get_other_company_ownership(
        self,
        user_id: int,
        exclude_company_id: int | None = None,
    ) -> UserCompany | None:
        """Comprueba si el usuario ya es propietario/administrador de otra empresa."""
        statement = select(UserCompany).where(
            UserCompany.id_usuario == user_id,
            UserCompany.es_propietario.is_(True),
        )
        if exclude_company_id is not None:
            statement = statement.where(UserCompany.id_empresa != exclude_company_id)
        return self.db.scalars(statement).first()

    def get_employee(self, user_id: int, company_id: int) -> Employee | None:
        """Obtiene el perfil de empleado de un usuario en una empresa."""
        statement = select(Employee).where(
            Employee.id_usuario == user_id,
            Employee.empresa_id == company_id,
        )
        return self.db.scalar(statement)

    def create_employee(self, *, user_id: int, company_id: int, cargo: str | None = None) -> Employee:
        """Crea el perfil de empleado asociado a la empresa en t_empleado."""
        employee = Employee(
            id_usuario=user_id,
            empresa_id=company_id,
            cargo=cargo,
        )
        self.db.add(employee)
        self.db.flush()
        return employee

    def get_client(self, user_id: int, company_id: int) -> Client | None:
        """Obtiene el perfil de cliente de un usuario en una empresa."""
        statement = select(Client).where(
            Client.id_usuario == user_id,
            Client.empresa_id == company_id,
        )
        return self.db.scalar(statement)

    def create_client(self, *, user_id: int, company_id: int) -> Client:
        """Crea el perfil de cliente asociado a la empresa en t_cliente."""
        client = Client(
            id_usuario=user_id,
            empresa_id=company_id,
        )
        self.db.add(client)
        self.db.flush()
        return client

    def list_company_branches(
        self,
        company_id: int,
        *,
        state: bool | None = None,
        search: str | None = None,
    ) -> list[tuple[Branch, City | None]]:
        """Lista las sucursales pertenecientes a la empresa con datos de su ciudad."""
        statement = (
            select(Branch, City)
            .outerjoin(City, City.id_ciudad == Branch.id_ciudad)
            .where(Branch.empresa_id == company_id)
        )
        if state is not None:
            statement = statement.where(Branch.estado.is_(state))
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(func.lower(Branch.nombre).like(term))
        statement = statement.order_by(Branch.nombre.asc())
        rows = self.db.execute(statement).all()
        return [(row[0], row[1]) for row in rows]

    def get_branch(self, branch_id: int) -> tuple[Branch, City | None] | None:
        """Obtiene una sucursal por su identificador primario junto a su ciudad."""
        statement = (
            select(Branch, City)
            .outerjoin(City, City.id_ciudad == Branch.id_ciudad)
            .where(Branch.id_sucursal == branch_id)
        )
        row = self.db.execute(statement).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    def get_city(self, city_id: int, *, for_update: bool = False) -> City | None:
        """Obtiene una ciudad para validar su existencia y estado."""
        statement = select(City).where(City.id_ciudad == city_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create_branch(self, *, company_id: int, **values: object) -> Branch:
        """Crea una nueva sucursal con propiedad exclusiva fijada a la empresa."""
        branch = Branch(
            empresa_id=company_id,
            estado=True,
            **values,
        )
        self.db.add(branch)
        self.db.flush()
        return branch

