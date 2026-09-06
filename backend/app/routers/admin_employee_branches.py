"""Endpoints administrativos de CU06."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.auth import ErrorResponse
from app.schemas.admin_employee_branch import (
    AssignableEmployeeListResponse,
    AdminEmployeeBranchListResponse, AdminEmployeeBranchResponse,
    AdminEmployeeBranchUpdateResponse, EmployeeBranchCreateRequest,
    EmployeeBranchStatusUpdateRequest,
)
from app.services.admin_employee_branch_service import (
    AdminEmployeeBranchPersistenceError, AdminEmployeeBranchService,
    EmployeeBranchConflictError, EmployeeBranchNotFoundError,
    EmployeeBranchValidationError,
)


router = APIRouter(
    prefix="/api/admin/employee-branches", tags=["Asignaciones de empleados"],
)
ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    404: {"model": ErrorResponse, "description": "Empleado, sucursal o asignación inexistente"},
    409: {"model": ErrorResponse, "description": "Asignación duplicada o conflicto de integridad"},
    422: {"model": ErrorResponse, "description": "Datos de asignación inválidos"},
    500: {"model": ErrorResponse, "description": "Error interno"},
}
OPERATION_ERRORS = (
    EmployeeBranchNotFoundError, EmployeeBranchValidationError,
    EmployeeBranchConflictError, AdminEmployeeBranchPersistenceError, SQLAlchemyError,
)


def _error_response(error: Exception) -> JSONResponse:
    if isinstance(error, EmployeeBranchNotFoundError):
        code = 404
    elif isinstance(error, EmployeeBranchValidationError):
        code = 422
    elif isinstance(error, EmployeeBranchConflictError):
        code = 409
    else:
        code = 500
    return JSONResponse(status_code=code, content={
        "success": False,
        "message": str(error) if code != 500 else "No fue posible procesar la asignación",
    })


@router.get("", response_model=AdminEmployeeBranchListResponse, responses=ERROR_RESPONSES)
def list_assignments(
    administrator: AdminDependency,
    id_sucursal: Annotated[int | None, Query(gt=0)] = None,
    id_empleado: Annotated[int | None, Query(gt=0)] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminEmployeeBranchListResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, pagination = AdminEmployeeBranchService(db).list_assignments(
            employee_id=id_empleado, branch_id=id_sucursal, state=estado,
            page=page, page_size=page_size,
        )
        return AdminEmployeeBranchListResponse(data=data, pagination=pagination)
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.get(
    "/options/employees", response_model=AssignableEmployeeListResponse,
    responses=ERROR_RESPONSES,
    summary="Listar empleados activos asignables a sucursales",
)
def list_assignable_employees(
    administrator: AdminDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AssignableEmployeeListResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, pagination = AdminEmployeeBranchService(db).list_assignable_employees(
            page=page, page_size=page_size,
        )
        return AssignableEmployeeListResponse(data=data, pagination=pagination)
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.get("/{id_empleado_sucursal}", response_model=AdminEmployeeBranchResponse, responses=ERROR_RESPONSES)
def get_assignment(
    id_empleado_sucursal: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminEmployeeBranchResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminEmployeeBranchResponse(
            data=AdminEmployeeBranchService(db).get_assignment(id_empleado_sucursal),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.post(
    "", response_model=AdminEmployeeBranchUpdateResponse, status_code=201,
    responses={**ERROR_RESPONSES, 200: {
        "model": AdminEmployeeBranchUpdateResponse,
        "description": "Asignación existente reactivada",
    }},
)
def create_assignment(
    payload: EmployeeBranchCreateRequest,
    administrator: AdminDependency,
    response: Response,
    db: Session = Depends(get_db),
) -> AdminEmployeeBranchUpdateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, created = AdminEmployeeBranchService(db).create_assignment(payload)
        response.status_code = 201 if created else 200
        return AdminEmployeeBranchUpdateResponse(
            data=data, message="Asignación creada correctamente" if created else "Asignación reactivada correctamente",
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch("/{id_empleado_sucursal}/status", response_model=AdminEmployeeBranchUpdateResponse, responses=ERROR_RESPONSES)
def update_assignment_status(
    id_empleado_sucursal: int,
    payload: EmployeeBranchStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminEmployeeBranchUpdateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminEmployeeBranchUpdateResponse(
            data=AdminEmployeeBranchService(db).update_status(
                assignment_id=id_empleado_sucursal, payload=payload,
            ),
            message="Estado de la asignación actualizado correctamente",
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)
