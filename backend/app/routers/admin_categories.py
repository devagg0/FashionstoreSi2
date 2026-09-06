"""Endpoints protegidos para gestionar categorías."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_category import (
    AdminCategoryCreateResponse,
    AdminCategoryListResponse,
    AdminCategoryResponse,
    AdminCategoryUpdateResponse,
    CategoryCreateRequest,
    CategoryStatusUpdateRequest,
    CategoryUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_category_service import (
    AdminCategoryPersistenceError,
    AdminCategoryService,
    CategoryNameDuplicateError,
    CategoryNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/categories",
    tags=["Administración de categorías"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


CATEGORY_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Categoría no encontrada",
    },
}


@router.get(
    "",
    response_model=AdminCategoryListResponse,
    summary="Listar categorías",
    responses=COMMON_ERROR_RESPONSES,
)
def list_categories(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=100, description="Búsqueda parcial por nombre"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminCategoryListResponse | JSONResponse:
    """Lista categorías con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        categories, pagination = AdminCategoryService(db).list_categories(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
        return AdminCategoryListResponse(data=categories, pagination=pagination)
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")


@router.get(
    "/{id_categoria}",
    response_model=AdminCategoryResponse,
    summary="Obtener detalle de categoría",
    responses=CATEGORY_ERROR_RESPONSES,
)
def get_category(
    id_categoria: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCategoryResponse | JSONResponse:
    """Devuelve el detalle de una categoría existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        category = AdminCategoryService(db).get_category(id_categoria)
    except CategoryNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")
    return AdminCategoryResponse(data=category)


@router.post(
    "",
    response_model=AdminCategoryCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear categoría",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre de la categoría ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear la categoría",
        },
    },
)
def create_category(
    payload: CategoryCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCategoryCreateResponse | JSONResponse:
    """Crea una categoría activa por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        category = AdminCategoryService(db).create_category(payload)
    except CategoryNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe una categoría con ese nombre",
        )
    except AdminCategoryPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear la categoría",
        )
    return AdminCategoryCreateResponse(data=category)


@router.patch(
    "/{id_categoria}",
    response_model=AdminCategoryUpdateResponse,
    summary="Modificar categoría",
    responses={
        **CATEGORY_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El nombre de la categoría ya existe",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar la categoría",
        },
    },
)
def update_category(
    id_categoria: int,
    payload: CategoryUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCategoryUpdateResponse | JSONResponse:
    """Modifica los campos de una categoría."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        category = AdminCategoryService(db).update_category(
            category_id=id_categoria,
            payload=payload,
        )
    except CategoryNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
    except CategoryNameDuplicateError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Ya existe una categoría con ese nombre",
        )
    except AdminCategoryPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar la categoría",
        )
    return AdminCategoryUpdateResponse(
        message="Categoría actualizada correctamente",
        data=category,
    )


@router.patch(
    "/{id_categoria}/status",
    response_model=AdminCategoryUpdateResponse,
    summary="Activar o desactivar categoría",
    responses={
        **CATEGORY_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_category_status(
    id_categoria: int,
    payload: CategoryStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminCategoryUpdateResponse | JSONResponse:
    """Activa o desactiva una categoría sin eliminarla."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        category = AdminCategoryService(db).update_status(
            category_id=id_categoria,
            payload=payload,
        )
    except CategoryNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Categoría no encontrada")
    except AdminCategoryPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado de la categoría",
        )
    return AdminCategoryUpdateResponse(
        message="Estado de la categoría actualizado correctamente",
        data=category,
    )
