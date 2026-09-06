"""Endpoints protegidos para gestionar colores."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_color import (
    AdminColorCreateResponse,
    AdminColorListResponse,
    AdminColorResponse,
    AdminColorUpdateResponse,
    ColorCreateRequest,
    ColorStatusUpdateRequest,
    ColorUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_color_service import (
    AdminColorPersistenceError,
    AdminColorService,
    ColorNameDuplicateError,
    ColorNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/colors",
    tags=["Administración de colores"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


COLOR_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Color no encontrado",
    },
}


@router.get(
    "",
    response_model=AdminColorListResponse,
    summary="Listar colores",
    responses=COMMON_ERROR_RESPONSES,
)
def list_colors(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=50, description="Búsqueda parcial por nombre"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminColorListResponse | JSONResponse:
    """Lista colores con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        colors, pagination = AdminColorService(db).list_colors(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
        return AdminColorListResponse(data=colors, pagination=pagination)
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")


@router.get(
    "/{id_color}",
    response_model=AdminColorResponse,
    summary="Obtener detalle de color",
    responses=COLOR_ERROR_RESPONSES,
)
def get_color(
    id_color: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminColorResponse | JSONResponse:
    """Devuelve el detalle de un color existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        color = AdminColorService(db).get_color(id_color)
    except ColorNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Color no encontrado")
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")
    return AdminColorResponse(data=color)


@router.post(
    "",
    response_model=AdminColorCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear color",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre del color ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear el color",
        },
    },
)
def create_color(
    payload: ColorCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminColorCreateResponse | JSONResponse:
    """Crea un color activo por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        color = AdminColorService(db).create_color(payload)
    except ColorNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe un color con ese nombre",
        )
    except AdminColorPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear el color",
        )
    return AdminColorCreateResponse(data=color)


@router.patch(
    "/{id_color}",
    response_model=AdminColorUpdateResponse,
    summary="Modificar color",
    responses={
        **COLOR_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre del color ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el color",
        },
    },
)
def update_color(
    id_color: int,
    payload: ColorUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminColorUpdateResponse | JSONResponse:
    """Modifica los campos de un color."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        color = AdminColorService(db).update_color(
            color_id=id_color,
            payload=payload,
        )
    except ColorNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Color no encontrado")
    except ColorNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe un color con ese nombre",
        )
    except AdminColorPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el color",
        )
    return AdminColorUpdateResponse(
        message="Color actualizado correctamente",
        data=color,
    )


@router.patch(
    "/{id_color}/status",
    response_model=AdminColorUpdateResponse,
    summary="Activar o desactivar color",
    responses={
        **COLOR_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_color_status(
    id_color: int,
    payload: ColorStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminColorUpdateResponse | JSONResponse:
    """Activa o desactiva un color sin eliminarla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        color = AdminColorService(db).update_status(
            color_id=id_color,
            payload=payload,
        )
    except ColorNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Color no encontrado")
    except AdminColorPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado del color",
        )
    return AdminColorUpdateResponse(
        message="Estado del color actualizado correctamente",
        data=color,
    )
