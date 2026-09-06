"""Endpoints protegidos para gestionar temporadas."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_season import (
    AdminSeasonCreateResponse,
    AdminSeasonListResponse,
    AdminSeasonResponse,
    AdminSeasonUpdateResponse,
    SeasonCreateRequest,
    SeasonStatusUpdateRequest,
    SeasonUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_season_service import (
    AdminSeasonPersistenceError,
    AdminSeasonService,
    SeasonNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/seasons",
    tags=["Administración de temporadas"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


SEASON_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Temporada no encontrada",
    },
}


@router.get(
    "",
    response_model=AdminSeasonListResponse,
    summary="Listar temporadas",
    responses=COMMON_ERROR_RESPONSES,
)
def list_seasons(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=100, description="Búsqueda parcial por nombre"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminSeasonListResponse | JSONResponse:
    """Lista temporadas con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        seasons, pagination = AdminSeasonService(db).list_seasons(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
        return AdminSeasonListResponse(data=seasons, pagination=pagination)
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")


@router.get(
    "/{id_temporada}",
    response_model=AdminSeasonResponse,
    summary="Obtener detalle de temporada",
    responses=SEASON_ERROR_RESPONSES,
)
def get_season(
    id_temporada: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSeasonResponse | JSONResponse:
    """Devuelve el detalle de una temporada existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        season = AdminSeasonService(db).get_season(id_temporada)
    except SeasonNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Temporada no encontrada")
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")
    return AdminSeasonResponse(data=season)


@router.post(
    "",
    response_model=AdminSeasonCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear temporada",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear la temporada",
        },
    },
)
def create_season(
    payload: SeasonCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSeasonCreateResponse | JSONResponse:
    """Crea una temporada activa por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        season = AdminSeasonService(db).create_season(payload)
    except AdminSeasonPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear la temporada",
        )
    return AdminSeasonCreateResponse(data=season)


@router.patch(
    "/{id_temporada}",
    response_model=AdminSeasonUpdateResponse,
    summary="Modificar temporada",
    responses={
        **SEASON_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar la temporada",
        },
    },
)
def update_season(
    id_temporada: int,
    payload: SeasonUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSeasonUpdateResponse | JSONResponse:
    """Modifica los campos de una temporada."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        season = AdminSeasonService(db).update_season(
            season_id=id_temporada,
            payload=payload,
        )
    except SeasonNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Temporada no encontrada")
    except AdminSeasonPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar la temporada",
        )
    return AdminSeasonUpdateResponse(
        message="Temporada actualizada correctamente",
        data=season,
    )


@router.patch(
    "/{id_temporada}/status",
    response_model=AdminSeasonUpdateResponse,
    summary="Activar o desactivar temporada",
    responses={
        **SEASON_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_season_status(
    id_temporada: int,
    payload: SeasonStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSeasonUpdateResponse | JSONResponse:
    """Activa o desactiva una temporada sin eliminarla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        season = AdminSeasonService(db).update_status(
            season_id=id_temporada,
            payload=payload,
        )
    except SeasonNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Temporada no encontrada")
    except AdminSeasonPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado de la temporada",
        )
    return AdminSeasonUpdateResponse(
        message="Estado de la temporada actualizado correctamente",
        data=season,
    )
