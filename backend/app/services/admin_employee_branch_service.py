"""Reglas de CU06 adaptadas a la unicidad por empleado y sucursal."""

from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories.admin_branch_repository import AdminBranchRepository
from app.repositories.admin_employee_branch_repository import AdminEmployeeBranchRepository
from app.repositories.admin_user_repository import AdminUserRepository
from app.schemas.admin_employee_branch import (
    AssignableEmployeeData,
    AdminEmployeeBranchData, EmployeeBranchCreateRequest,
    EmployeeBranchPaginationData, EmployeeBranchStatusUpdateRequest,
)
from app.services.admin_user_service import EMPLOYEE_ROLE_NAMES


class EmployeeBranchNotFoundError(Exception):
    """No existe la asignación, el empleado o la sucursal solicitada."""


class EmployeeBranchValidationError(Exception):
    """El usuario o la sucursal no permiten activar la asignación."""


class EmployeeBranchConflictError(Exception):
    """La pareja ya está activa o existe un conflicto de integridad."""


class AdminEmployeeBranchPersistenceError(Exception):
    """No fue posible persistir la operación."""


class AdminEmployeeBranchService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AdminEmployeeBranchRepository(db)
        self.user_repository = AdminUserRepository(db)
        self.branch_repository = AdminBranchRepository(db)

    def list_assignable_employees(self, *, page: int, page_size: int):
        rows, total = self.repository.list_assignable_employees(
            role_names=EMPLOYEE_ROLE_NAMES, page=page, page_size=page_size,
        )
        return [AssignableEmployeeData.model_validate(row) for row in rows], EmployeeBranchPaginationData(
            page=page, page_size=page_size, total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def _validate_targets(self, employee_id: int, branch_id: int) -> None:
        employee = self.repository.get_employee(employee_id)
        if employee is None:
            raise EmployeeBranchNotFoundError("Empleado no encontrado")
        result = self.user_repository.get_user_with_role(employee.id_usuario, for_update=True)
        if result is None:
            raise EmployeeBranchValidationError("El empleado no tiene un usuario válido")
        user, role = result
        if not user.estado:
            raise EmployeeBranchValidationError("El usuario del empleado está inactivo")
        if role.upper() not in EMPLOYEE_ROLE_NAMES:
            raise EmployeeBranchValidationError("El usuario no tiene un rol de empleado operativo")
        branch = self.branch_repository.get_by_id(branch_id, for_update=True)
        if branch is None:
            raise EmployeeBranchNotFoundError("Sucursal no encontrada")
        if not branch.estado:
            raise EmployeeBranchValidationError("La sucursal está inactiva")

    def get_assignment(self, assignment_id: int) -> AdminEmployeeBranchData:
        row = self.repository.get_detail(assignment_id)
        if row is None:
            raise EmployeeBranchNotFoundError("Asignación no encontrada")
        return AdminEmployeeBranchData.model_validate(row)

    def list_assignments(self, *, employee_id, branch_id, state, page, page_size):
        rows, total = self.repository.list_assignments(
            employee_id=employee_id, branch_id=branch_id, state=state,
            page=page, page_size=page_size,
        )
        return [AdminEmployeeBranchData.model_validate(row) for row in rows], EmployeeBranchPaginationData(
            page=page, page_size=page_size, total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def create_assignment(self, payload: EmployeeBranchCreateRequest):
        """Devuelve también si se creó una fila o se reactivó la existente."""
        try:
            self._validate_targets(payload.id_empleado, payload.id_sucursal)
            assignment = self.repository.get_by_pair(payload.id_empleado, payload.id_sucursal)
            created = assignment is None
            if created:
                assignment = self.repository.create(
                    employee_id=payload.id_empleado, branch_id=payload.id_sucursal,
                )
            elif assignment.estado:
                raise EmployeeBranchConflictError("El empleado ya está asignado a esta sucursal")
            else:
                self.repository.update_status(assignment, state=True)
            result = self.get_assignment(assignment.id_empleado_sucursal)
            self.db.commit()
            return result, created
        except (EmployeeBranchNotFoundError, EmployeeBranchValidationError, EmployeeBranchConflictError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise EmployeeBranchConflictError("Conflicto de integridad al asignar empleado a sucursal") from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminEmployeeBranchPersistenceError from error

    def update_status(self, *, assignment_id: int, payload: EmployeeBranchStatusUpdateRequest):
        try:
            # El mismo orden de bloqueos que POST evita ciclos entre operaciones.
            assignment = self.repository.get_by_id(assignment_id)
            if assignment is None:
                raise EmployeeBranchNotFoundError("Asignación no encontrada")
            if payload.estado:
                self._validate_targets(assignment.id_empleado, assignment.id_sucursal)
            assignment = self.repository.get_by_id(assignment_id, for_update=True)
            if assignment is None:
                raise EmployeeBranchNotFoundError("Asignación no encontrada")
            self.repository.update_status(assignment, state=payload.estado)
            result = self.get_assignment(assignment.id_empleado_sucursal)
            self.db.commit()
            return result
        except (EmployeeBranchNotFoundError, EmployeeBranchValidationError):
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminEmployeeBranchPersistenceError from error
