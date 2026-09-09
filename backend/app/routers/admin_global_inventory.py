"""Endpoints independientes y de solo lectura para CU16."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.auth import ErrorResponse
from app.schemas.admin_global_inventory import GlobalInventoryListResponse, GlobalInventoryResponse
from app.services.admin_global_inventory import AdminGlobalInventoryService, GlobalInventoryNotFoundError


router = APIRouter(prefix="/api/admin/global-inventory", tags=["Inventario global"])
ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    404: {"model": ErrorResponse, "description": "Variante inexistente"},
    422: {"description": "Parámetros inválidos"},
    500: {"model": ErrorResponse, "description": "Error interno"},
}


def _error_response(error):
    missing = isinstance(error, GlobalInventoryNotFoundError)
    return JSONResponse(status_code=404 if missing else 500, content={
        "success": False,
        "message": "Variante no encontrada" if missing else "No fue posible consultar el inventario global",
    })


@router.get("", response_model=GlobalInventoryListResponse, responses=ERROR_RESPONSES)
def list_inventory(
    administrator: AdminDependency,
    search: Annotated[str | None, Query(max_length=200)] = None,
    id_categoria: Annotated[int | None, Query(gt=0)] = None,
    id_producto: Annotated[int | None, Query(gt=0)] = None,
    id_talla: Annotated[int | None, Query(gt=0)] = None,
    id_color: Annotated[int | None, Query(gt=0)] = None,
    id_ciudad: Annotated[int | None, Query(gt=0)] = None,
    id_sucursal: Annotated[int | None, Query(gt=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, pagination = AdminGlobalInventoryService(db).list_inventory(
            search=search, id_categoria=id_categoria, id_producto=id_producto,
            id_talla=id_talla, id_color=id_color, id_ciudad=id_ciudad,
            id_sucursal=id_sucursal, page=page, page_size=page_size,
        )
        return GlobalInventoryListResponse(data=data, pagination=pagination)
    except Exception as error:
        return _error_response(error)


@router.get("/{id_variante_producto}", response_model=GlobalInventoryResponse, responses=ERROR_RESPONSES)
def get_inventory(
    id_variante_producto: Annotated[int, Path(gt=0)], administrator: AdminDependency,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return GlobalInventoryResponse(data=AdminGlobalInventoryService(db).get_inventory(id_variante_producto))
    except Exception as error:
        return _error_response(error)
