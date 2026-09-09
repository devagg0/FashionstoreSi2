"""Los cuatro endpoints administrativos de CU14."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.auth import ErrorResponse
from app.schemas.admin_inventory import (
    InventoryCreateRequest, InventoryUpdateRequest, InventoryListResponse, InventoryResponse,
)
from app.services.admin_inventory import (
    AdminInventoryService, InventoryConflictError, InventoryNotFoundError, InventoryValidationError,
)


router = APIRouter(prefix="/api/admin/inventory", tags=["Inventario de sucursal"])
ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    **{code: {"model": ErrorResponse, "description": description} for code, description in (
        (400, "Regla de negocio inválida"), (404, "Recurso inexistente"),
        (409, "Inventario duplicado o conflicto concurrente"), (500, "Error interno"),
    )},
    422: {"description": "Validación automática del request"},
}


def _error_response(error):
    code = 500
    if isinstance(error, InventoryNotFoundError):
        code = 404
    elif isinstance(error, InventoryValidationError):
        code = 400
    elif isinstance(error, InventoryConflictError):
        code = 409
    return JSONResponse(status_code=code, content={
        "success": False,
        "message": str(error) if code != 500 else "No fue posible procesar el inventario",
    })


@router.get("", response_model=InventoryListResponse, responses=ERROR_RESPONSES)
def list_inventory(
    administrator: AdminDependency,
    search: Annotated[str | None, Query(max_length=200)] = None,
    id_sucursal: Annotated[int | None, Query(gt=0)] = None,
    id_ciudad: Annotated[int | None, Query(gt=0)] = None,
    id_categoria: Annotated[int | None, Query(gt=0)] = None,
    id_producto: Annotated[int | None, Query(gt=0)] = None,
    id_variante_producto: Annotated[int | None, Query(gt=0)] = None,
    id_talla: Annotated[int | None, Query(gt=0)] = None,
    id_color: Annotated[int | None, Query(gt=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, pagination = AdminInventoryService(db).list_inventory(
            search=search, id_sucursal=id_sucursal, id_ciudad=id_ciudad,
            id_categoria=id_categoria, id_producto=id_producto,
            id_variante_producto=id_variante_producto, id_talla=id_talla, id_color=id_color,
            page=page, page_size=page_size,
        )
        return InventoryListResponse(data=data, pagination=pagination)
    except Exception as error:
        return _error_response(error)


@router.get("/{id_inventario_sucursal}", response_model=InventoryResponse, responses=ERROR_RESPONSES)
def get_inventory(
    id_inventario_sucursal: Annotated[int, Path(gt=0)], administrator: AdminDependency,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return InventoryResponse(data=AdminInventoryService(db).get_inventory(id_inventario_sucursal))
    except Exception as error:
        return _error_response(error)


@router.post("", response_model=InventoryResponse, status_code=201, responses=ERROR_RESPONSES)
def create_inventory(payload: InventoryCreateRequest, administrator: AdminDependency, db: Session = Depends(get_db)):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return InventoryResponse(data=AdminInventoryService(db).create_inventory(payload))
    except Exception as error:
        return _error_response(error)


@router.patch("/{id_inventario_sucursal}", response_model=InventoryResponse, responses=ERROR_RESPONSES)
def update_inventory(
    id_inventario_sucursal: Annotated[int, Path(gt=0)], payload: InventoryUpdateRequest,
    administrator: AdminDependency, db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return InventoryResponse(data=AdminInventoryService(db).update_inventory(id_inventario_sucursal, payload))
    except Exception as error:
        return _error_response(error)
