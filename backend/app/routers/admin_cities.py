"""Endpoints protegidos para gestionar ciudades."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_city import (
    AdminCityCreateResponse,
    AdminCityListResponse,
    AdminCityResponse,
    AdminCityUpdateResponse,
    CityCreateRequest,
    CityStatusUpdateRequest,
    CityUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_city_service import (
    AdminCityPersistenceError,
    AdminCityService,
    CityNameDuplicateError,
    CityNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/cities",
    tags=["Administración de ciudades"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


CITY_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Ciudad no encontrada",
    },
}


@router.get(
    "",
    response_model=AdminCityListResponse,
    summary="Listar ciudades",
    responses=COMMON_ERROR_RESPONSES,
)
def list_cities(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=100, description="Búsqueda parcial por nombre"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminCityListResponse | JSONResponse:
    """Lista ciudades con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    cities, pagination = AdminCityService(db).list_cities(
        search=search,
        state=estado,
        page=page,
        page_size=page_size,
    )
    return AdminCityListResponse(data=cities, pagination=pagination)


@router.get(
    "/{id_ciudad}",
    response_model=AdminCityResponse,
    summary="Obtener detalle de ciudad",
    responses=CITY_ERROR_RESPONSES,
)
def get_city(
    id_ciudad: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCityResponse | JSONResponse:
    """Devuelve el detalle de una ciudad existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        city = AdminCityService(db).get_city(id_ciudad)
    except CityNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Ciudad no encontrada")
    return AdminCityResponse(data=city)


@router.post(
    "",
    response_model=AdminCityCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ciudad",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre de la ciudad ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear la ciudad",
        },
    },
)
def create_city(
    payload: CityCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCityCreateResponse | JSONResponse:
    """Crea una ciudad activa por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        city = AdminCityService(db).create_city(payload)
    except CityNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe una ciudad con ese nombre",
        )
    except AdminCityPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear la ciudad",
        )
    return AdminCityCreateResponse(data=city)


@router.patch(
    "/{id_ciudad}",
    response_model=AdminCityUpdateResponse,
    summary="Modificar nombre de ciudad",
    responses={
        **CITY_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre de la ciudad ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar la ciudad",
        },
    },
)
def update_city(
    id_ciudad: int,
    payload: CityUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCityUpdateResponse | JSONResponse:
    """Modifica solamente el nombre de una ciudad."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        city = AdminCityService(db).update_city(
            city_id=id_ciudad,
            payload=payload,
        )
    except CityNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Ciudad no encontrada")
    except CityNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe una ciudad con ese nombre",
        )
    except AdminCityPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar la ciudad",
        )
    return AdminCityUpdateResponse(
        message="Ciudad actualizada correctamente",
        data=city,
    )


@router.patch(
    "/{id_ciudad}/status",
    response_model=AdminCityUpdateResponse,
    summary="Activar o desactivar ciudad",
    responses={
        **CITY_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_city_status(
    id_ciudad: int,
    payload: CityStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCityUpdateResponse | JSONResponse:
    """Activa o desactiva una ciudad sin eliminarla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        city = AdminCityService(db).update_status(
            city_id=id_ciudad,
            payload=payload,
        )
    except CityNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Ciudad no encontrada")
    except AdminCityPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado de la ciudad",
        )
    return AdminCityUpdateResponse(
        message="Estado de la ciudad actualizado correctamente",
        data=city,
    )
