"""Endpoints protegidos para gestionar tallas."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_size import (
    AdminSizeCreateResponse,
    AdminSizeListResponse,
    AdminSizeResponse,
    AdminSizeUpdateResponse,
    SizeCreateRequest,
    SizeStatusUpdateRequest,
    SizeUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_size_service import (
    AdminSizePersistenceError,
    AdminSizeService,
    SizeNameDuplicateError,
    SizeNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/sizes",
    tags=["Administración de tallas"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


SIZE_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Talla no encontrada",
    },
}


@router.get(
    "",
    response_model=AdminSizeListResponse,
    summary="Listar tallas",
    responses=COMMON_ERROR_RESPONSES,
)
def list_sizes(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=20, description="Búsqueda parcial por nombre"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminSizeListResponse | JSONResponse:
    """Lista tallas con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        sizes, pagination = AdminSizeService(db).list_sizes(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
        return AdminSizeListResponse(data=sizes, pagination=pagination)
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")


@router.get(
    "/{id_talla}",
    response_model=AdminSizeResponse,
    summary="Obtener detalle de talla",
    responses=SIZE_ERROR_RESPONSES,
)
def get_size(
    id_talla: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSizeResponse | JSONResponse:
    """Devuelve el detalle de una talla existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        size = AdminSizeService(db).get_size(id_talla)
    except SizeNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Talla no encontrada")
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")
    return AdminSizeResponse(data=size)


@router.post(
    "",
    response_model=AdminSizeCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear talla",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre de la talla ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear la talla",
        },
    },
)
def create_size(
    payload: SizeCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSizeCreateResponse | JSONResponse:
    """Crea una talla activa por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        size = AdminSizeService(db).create_size(payload)
    except SizeNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe una talla con ese nombre",
        )
    except AdminSizePersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear la talla",
        )
    return AdminSizeCreateResponse(data=size)


@router.patch(
    "/{id_talla}",
    response_model=AdminSizeUpdateResponse,
    summary="Modificar talla",
    responses={
        **SIZE_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre de la talla ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar la talla",
        },
    },
)
def update_size(
    id_talla: int,
    payload: SizeUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSizeUpdateResponse | JSONResponse:
    """Modifica los campos de una talla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        size = AdminSizeService(db).update_size(
            size_id=id_talla,
            payload=payload,
        )
    except SizeNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Talla no encontrada")
    except SizeNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe una talla con ese nombre",
        )
    except AdminSizePersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar la talla",
        )
    return AdminSizeUpdateResponse(
        message="Talla actualizada correctamente",
        data=size,
    )


@router.patch(
    "/{id_talla}/status",
    response_model=AdminSizeUpdateResponse,
    summary="Activar o desactivar talla",
    responses={
        **SIZE_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_size_status(
    id_talla: int,
    payload: SizeStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSizeUpdateResponse | JSONResponse:
    """Activa o desactiva una talla sin eliminarla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        size = AdminSizeService(db).update_status(
            size_id=id_talla,
            payload=payload,
        )
    except SizeNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Talla no encontrada")
    except AdminSizePersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado de la talla",
        )
    return AdminSizeUpdateResponse(
        message="Estado de la talla actualizado correctamente",
        data=size,
    )
