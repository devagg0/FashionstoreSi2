"""Endpoints administrativos de CU15."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.auth import ErrorResponse
from app.schemas.admin_inventory_movements import (
    MovementCreateRequest, MovementListResponse, MovementResponse, MovementState, MovementType,
)
from app.services.admin_inventory_movements import (
    AdminInventoryMovementService, MovementConflictError, MovementNotFoundError,
    MovementPersistenceError, MovementValidationError,
)


router = APIRouter(prefix="/api/admin/inventory-movements", tags=["Movimientos de inventario"])
ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    **{code: {"model": ErrorResponse, "description": description} for code, description in (
        (400, "Regla de negocio inválida"), (404, "Recurso inexistente"),
        (409, "Conflicto de estado, stock o concurrencia"), (500, "Error interno"),
    )},
    422: {"description": "Validación automática del request"},
}
OPERATION_ERRORS = (
    MovementNotFoundError, MovementValidationError, MovementConflictError,
    MovementPersistenceError, SQLAlchemyError,
)


def _error_response(error):
    code = 500
    if isinstance(error, MovementNotFoundError):
        code = 404
    elif isinstance(error, MovementValidationError):
        code = 400
    elif isinstance(error, MovementConflictError):
        code = 409
    return JSONResponse(status_code=code, content={
        "success": False,
        "message": str(error) if code != 500 else "No fue posible procesar el movimiento de inventario",
    })


@router.get("", response_model=MovementListResponse, responses=ERROR_RESPONSES)
def list_movements(
    administrator: AdminDependency,
    search: Annotated[str | None, Query(max_length=200)] = None,
    tipo_movimiento: MovementType | None = None,
    estado: MovementState | None = None,
    id_sucursal: Annotated[int | None, Query(gt=0)] = None,
    id_variante_producto: Annotated[int | None, Query(gt=0)] = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, pagination = AdminInventoryMovementService(db).list_movements(
            search=search, tipo_movimiento=tipo_movimiento, estado=estado,
            id_sucursal=id_sucursal, id_variante_producto=id_variante_producto,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, page=page, page_size=page_size,
        )
        return MovementListResponse(data=data, pagination=pagination)
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.get("/{id_movimiento_inventario}", response_model=MovementResponse, responses=ERROR_RESPONSES)
def get_movement(
    id_movimiento_inventario: Annotated[int, Path(gt=0)], administrator: AdminDependency,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return MovementResponse(data=AdminInventoryMovementService(db).get_movement(id_movimiento_inventario))
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.post("", response_model=MovementResponse, status_code=201, responses=ERROR_RESPONSES)
def create_movement(payload: MovementCreateRequest, administrator: AdminDependency, db: Session = Depends(get_db)):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return MovementResponse(data=AdminInventoryMovementService(db).create_movement(payload))
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch("/{id_movimiento_inventario}/confirm", response_model=MovementResponse, responses=ERROR_RESPONSES)
def confirm_movement(
    id_movimiento_inventario: Annotated[int, Path(gt=0)], administrator: AdminDependency,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return MovementResponse(data=AdminInventoryMovementService(db).confirm_movement(id_movimiento_inventario))
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch("/{id_movimiento_inventario}/cancel", response_model=MovementResponse, responses=ERROR_RESPONSES)
def cancel_movement(
    id_movimiento_inventario: Annotated[int, Path(gt=0)], administrator: AdminDependency,
    db: Session = Depends(get_db),
):
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return MovementResponse(data=AdminInventoryMovementService(db).cancel_movement(id_movimiento_inventario))
    except OPERATION_ERRORS as error:
        return _error_response(error)
