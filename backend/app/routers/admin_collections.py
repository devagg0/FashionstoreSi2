"""Endpoints protegidos para gestionar colecciones."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_collection import (
    AdminCollectionCreateResponse,
    AdminCollectionListResponse,
    AdminCollectionResponse,
    AdminCollectionUpdateResponse,
    CollectionCreateRequest,
    CollectionStatusUpdateRequest,
    CollectionUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_collection_service import (
    AdminCollectionPersistenceError,
    AdminCollectionService,
    CollectionNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/collections",
    tags=["Administración de colecciones"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


COLLECTION_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Coleccion no encontrada",
    },
}


@router.get(
    "",
    response_model=AdminCollectionListResponse,
    summary="Listar colecciones",
    responses=COMMON_ERROR_RESPONSES,
)
def list_collections(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=100, description="Búsqueda parcial por nombre"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminCollectionListResponse | JSONResponse:
    """Lista colecciones con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        collections, pagination = AdminCollectionService(db).list_collections(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
        return AdminCollectionListResponse(data=collections, pagination=pagination)
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")


@router.get(
    "/{id_coleccion}",
    response_model=AdminCollectionResponse,
    summary="Obtener detalle de coleccion",
    responses=COLLECTION_ERROR_RESPONSES,
)
def get_collection(
    id_coleccion: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCollectionResponse | JSONResponse:
    """Devuelve el detalle de una coleccion existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        collection = AdminCollectionService(db).get_collection(id_coleccion)
    except CollectionNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Coleccion no encontrada")
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")
    return AdminCollectionResponse(data=collection)


@router.post(
    "",
    response_model=AdminCollectionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear coleccion",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear la coleccion",
        },
    },
)
def create_collection(
    payload: CollectionCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCollectionCreateResponse | JSONResponse:
    """Crea una coleccion activa por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        collection = AdminCollectionService(db).create_collection(payload)
    except AdminCollectionPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear la coleccion",
        )
    return AdminCollectionCreateResponse(data=collection)


@router.patch(
    "/{id_coleccion}",
    response_model=AdminCollectionUpdateResponse,
    summary="Modificar coleccion",
    responses={
        **COLLECTION_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar la coleccion",
        },
    },
)
def update_collection(
    id_coleccion: int,
    payload: CollectionUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCollectionUpdateResponse | JSONResponse:
    """Modifica los campos de una coleccion."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        collection = AdminCollectionService(db).update_collection(
            collection_id=id_coleccion,
            payload=payload,
        )
    except CollectionNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Coleccion no encontrada")
    except AdminCollectionPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar la coleccion",
        )
    return AdminCollectionUpdateResponse(
        message="Coleccion actualizada correctamente",
        data=collection,
    )


@router.patch(
    "/{id_coleccion}/status",
    response_model=AdminCollectionUpdateResponse,
    summary="Activar o desactivar coleccion",
    responses={
        **COLLECTION_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_collection_status(
    id_coleccion: int,
    payload: CollectionStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCollectionUpdateResponse | JSONResponse:
    """Activa o desactiva una coleccion sin eliminarla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        collection = AdminCollectionService(db).update_status(
            collection_id=id_coleccion,
            payload=payload,
        )
    except CollectionNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Coleccion no encontrada")
    except AdminCollectionPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado de la coleccion",
        )
    return AdminCollectionUpdateResponse(
        message="Estado de la coleccion actualizado correctamente",
        data=collection,
    )
