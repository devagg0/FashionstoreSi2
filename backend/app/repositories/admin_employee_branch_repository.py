"""Persistencia de CU06 sin cambios al esquema ni borrados físicos."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.role import Role
from app.models.user import User


class AdminEmployeeBranchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_employee(self, employee_id: int) -> Employee | None:
        return self.db.get(Employee, employee_id)

    def list_assignable_employees(
        self, *, role_names: set[str], page: int, page_size: int,
    ):
        """Incluye perfiles operativos activos incluso sin asignaciones previas."""
        statement = select(
            Employee.id_empleado, User.id_usuario, User.nombre, User.apellido,
            User.correo, Role.nombre.label("rol"), User.estado,
        ).select_from(Employee).join(
            User, User.id_usuario == Employee.id_usuario,
        ).join(Role, Role.id_rol == User.id_rol).where(
            User.estado.is_(True), func.upper(Role.nombre).in_(sorted(role_names)),
        )
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(statement.order_by(
            User.nombre, User.apellido, Employee.id_empleado,
        ).offset((page - 1) * page_size).limit(page_size)).mappings().all()
        return rows, total

    def get_by_id(self, assignment_id: int, *, for_update: bool = False):
        statement = select(EmployeeBranch).where(
            EmployeeBranch.id_empleado_sucursal == assignment_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_by_pair(self, employee_id: int, branch_id: int):
        return self.db.scalar(select(EmployeeBranch).where(
            EmployeeBranch.id_empleado == employee_id,
            EmployeeBranch.id_sucursal == branch_id,
        ).with_for_update())

    @staticmethod
    def _detail_statement():
        return select(
            EmployeeBranch.id_empleado_sucursal,
            EmployeeBranch.id_empleado,
            (User.nombre + " " + User.apellido).label("nombre_empleado"),
            User.correo,
            Role.nombre.label("rol"),
            EmployeeBranch.id_sucursal,
            Branch.nombre.label("nombre_sucursal"),
            EmployeeBranch.fecha_asignacion,
            EmployeeBranch.estado,
        ).join(Employee, Employee.id_empleado == EmployeeBranch.id_empleado).join(
            User, User.id_usuario == Employee.id_usuario
        ).join(Role, Role.id_rol == User.id_rol).join(
            Branch, Branch.id_sucursal == EmployeeBranch.id_sucursal
        )

    def get_detail(self, assignment_id: int):
        return self.db.execute(self._detail_statement().where(
            EmployeeBranch.id_empleado_sucursal == assignment_id
        )).mappings().one_or_none()

    def list_assignments(self, *, employee_id, branch_id, state, page, page_size):
        statement = self._detail_statement()
        if employee_id is not None:
            statement = statement.where(EmployeeBranch.id_empleado == employee_id)
        if branch_id is not None:
            statement = statement.where(EmployeeBranch.id_sucursal == branch_id)
        if state is not None:
            statement = statement.where(EmployeeBranch.estado.is_(state))
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(statement.order_by(
            EmployeeBranch.id_empleado_sucursal
        ).offset((page - 1) * page_size).limit(page_size)).mappings().all()
        return rows, total

    def create(self, *, employee_id: int, branch_id: int) -> EmployeeBranch:
        assignment = EmployeeBranch(
            id_empleado=employee_id, id_sucursal=branch_id, estado=True,
        )
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def update_status(self, assignment: EmployeeBranch, *, state: bool) -> None:
        assignment.estado = state
        self.db.flush()
