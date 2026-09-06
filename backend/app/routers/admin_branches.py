"""Endpoints protegidos para gestionar sucursales."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_branch import (
    AdminBranchCreateResponse,
    AdminBranchListResponse,
    AdminBranchResponse,
    AdminBranchUpdateResponse,
    BranchCreateRequest,
    BranchStatusUpdateRequest,
    BranchUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_branch_service import (
    AdminBranchPersistenceError,
    AdminBranchService,
    BranchCityNotFoundError,
    BranchCityInactiveError,
    BranchNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/branches",
    tags=["Administración de sucursales"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


BRANCH_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Sucursal no encontrada",
    },
}


@router.get(
    "",
    response_model=AdminBranchListResponse,
    summary="Listar sucursales",
    responses=COMMON_ERROR_RESPONSES,
)
def list_branches(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=150, description="Búsqueda parcial por nombre"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminBranchListResponse | JSONResponse:
    """Lista sucursales con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        branches, pagination = AdminBranchService(db).list_branches(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible listar las sucursales",
        )
    return AdminBranchListResponse(data=branches, pagination=pagination)


@router.get(
    "/{id_sucursal}",
    response_model=AdminBranchResponse,
    summary="Obtener detalle de sucursal",
    responses=BRANCH_ERROR_RESPONSES,
)
def get_branch(
    id_sucursal: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminBranchResponse | JSONResponse:
    """Devuelve el detalle de una sucursal existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        branch = AdminBranchService(db).get_branch(id_sucursal)
    except BranchNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada")
    except SQLAlchemyError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible consultar la sucursal",
        )
    return AdminBranchResponse(data=branch)


@router.post(
    "",
    response_model=AdminBranchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear sucursal",
    responses={
        **BRANCH_ERROR_RESPONSES,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
            "description": "La ciudad seleccionada está inactiva",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear la sucursal",
        },
    },
)
def create_branch(
    payload: BranchCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminBranchCreateResponse | JSONResponse:
    """Crea una sucursal activa por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        branch = AdminBranchService(db).create_branch(payload)
    except BranchCityNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Ciudad no encontrada")
    except BranchCityInactiveError:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "La ciudad seleccionada está inactiva",
        )
    except AdminBranchPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear la sucursal",
        )
    return AdminBranchCreateResponse(data=branch)


@router.patch(
    "/{id_sucursal}",
    response_model=AdminBranchUpdateResponse,
    summary="Modificar sucursal",
    responses={
        **BRANCH_ERROR_RESPONSES,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
            "description": "La ciudad seleccionada está inactiva",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar la sucursal",
        },
    },
)
def update_branch(
    id_sucursal: int,
    payload: BranchUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminBranchUpdateResponse | JSONResponse:
    """Modifica los datos de una sucursal."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        branch = AdminBranchService(db).update_branch(
            branch_id=id_sucursal,
            payload=payload,
        )
    except BranchNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada")
    except BranchCityNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Ciudad no encontrada")
    except BranchCityInactiveError:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "La ciudad seleccionada está inactiva",
        )
    except AdminBranchPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar la sucursal",
        )
    return AdminBranchUpdateResponse(
        message="Sucursal actualizada correctamente",
        data=branch,
    )


@router.patch(
    "/{id_sucursal}/status",
    response_model=AdminBranchUpdateResponse,
    summary="Activar o desactivar sucursal",
    responses={
        **BRANCH_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_branch_status(
    id_sucursal: int,
    payload: BranchStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminBranchUpdateResponse | JSONResponse:
    """Activa o desactiva una sucursal sin eliminarla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        branch = AdminBranchService(db).update_status(
            branch_id=id_sucursal,
            payload=payload,
        )
    except BranchNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Sucursal no encontrada")
    except AdminBranchPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado de la sucursal",
        )
    return AdminBranchUpdateResponse(
        message="Estado de la sucursal actualizado correctamente",
        data=branch,
    )
