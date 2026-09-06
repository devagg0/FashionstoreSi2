"""Endpoints protegidos para gestionar proveedores."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_supplier import (
    AdminSupplierCreateResponse,
    AdminSupplierListResponse,
    AdminSupplierResponse,
    AdminSupplierUpdateResponse,
    SupplierCreateRequest,
    SupplierStatusUpdateRequest,
    SupplierUpdateRequest,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_supplier_service import (
    AdminSupplierPersistenceError,
    AdminSupplierService,
    SupplierNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/suppliers",
    tags=["Administración de proveedores"],
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Devuelve el formato de error compartido por el backend."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )


SUPPLIER_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Proveedor no encontrado",
    },
}


@router.get(
    "",
    response_model=AdminSupplierListResponse,
    summary="Listar proveedores",
    responses=COMMON_ERROR_RESPONSES,
)
def list_suppliers(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=150, description="Búsqueda parcial por nombre, NIT o correo"),
    ] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminSupplierListResponse | JSONResponse:
    """Lista proveedores con búsqueda, estado y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        suppliers, pagination = AdminSupplierService(db).list_suppliers(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
        return AdminSupplierListResponse(data=suppliers, pagination=pagination)
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")


@router.get(
    "/{id_proveedor}",
    response_model=AdminSupplierResponse,
    summary="Obtener detalle de proveedor",
    responses=SUPPLIER_ERROR_RESPONSES,
)
def get_supplier(
    id_proveedor: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSupplierResponse | JSONResponse:
    """Devuelve el detalle de un proveedor existente."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        supplier = AdminSupplierService(db).get_supplier(id_proveedor)
    except SupplierNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Proveedor no encontrado")
    except SQLAlchemyError:
        db.rollback()
        return _error_response(500, "No fue posible consultar el catálogo")
    return AdminSupplierResponse(data=supplier)


@router.post(
    "",
    response_model=AdminSupplierCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear proveedor",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear el proveedor",
        },
    },
)
def create_supplier(
    payload: SupplierCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSupplierCreateResponse | JSONResponse:
    """Crea un proveedor activo por defecto."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        supplier = AdminSupplierService(db).create_supplier(payload)
    except AdminSupplierPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear el proveedor",
        )
    return AdminSupplierCreateResponse(data=supplier)


@router.patch(
    "/{id_proveedor}",
    response_model=AdminSupplierUpdateResponse,
    summary="Modificar proveedor",
    responses={
        **SUPPLIER_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el proveedor",
        },
    },
)
def update_supplier(
    id_proveedor: int,
    payload: SupplierUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSupplierUpdateResponse | JSONResponse:
    """Modifica los campos de un proveedor."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        supplier = AdminSupplierService(db).update_supplier(
            supplier_id=id_proveedor,
            payload=payload,
        )
    except SupplierNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Proveedor no encontrado")
    except AdminSupplierPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el proveedor",
        )
    return AdminSupplierUpdateResponse(
        message="Proveedor actualizado correctamente",
        data=supplier,
    )


@router.patch(
    "/{id_proveedor}/status",
    response_model=AdminSupplierUpdateResponse,
    summary="Activar o desactivar proveedor",
    responses={
        **SUPPLIER_ERROR_RESPONSES,
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar el estado",
        },
    },
)
def update_supplier_status(
    id_proveedor: int,
    payload: SupplierStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminSupplierUpdateResponse | JSONResponse:
    """Activa o desactiva un proveedor sin eliminarlo."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        supplier = AdminSupplierService(db).update_status(
            supplier_id=id_proveedor,
            payload=payload,
        )
    except SupplierNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Proveedor no encontrado")
    except AdminSupplierPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado del proveedor",
        )
    return AdminSupplierUpdateResponse(
        message="Estado del proveedor actualizado correctamente",
        data=supplier,
    )
