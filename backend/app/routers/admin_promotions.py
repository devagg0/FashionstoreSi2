"""Endpoints protegidos de CU11 para gestionar promociones."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_promotions import (
    AdminPromotionCreateResponse,
    AdminPromotionListResponse,
    AdminPromotionResponse,
    AdminPromotionUpdateResponse,
    PromotionCreateRequest,
    PromotionProductListResponse,
    PromotionProductsRequest,
    PromotionProductsResponse,
    PromotionStatusUpdateRequest,
    PromotionUpdateRequest,
    Validity,
)
from app.schemas.auth import ErrorResponse
from app.services.admin_promotions import (
    AdminPromotionPersistenceError,
    AdminPromotionService,
    PromotionBusinessRuleError,
    PromotionConflictError,
    PromotionNotFoundError,
    PromotionProductInactiveError,
    PromotionProductNotFoundError,
)


router = APIRouter(
    prefix="/api/admin/promotions",
    tags=["Administracion de promociones"],
)


PROMOTION_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Promocion o producto no encontrado",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Codigo o asociacion duplicada",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "Producto inactivo o regla de promocion invalida",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "No fue posible procesar la promocion",
    },
}


OPERATION_ERRORS = (
    PromotionNotFoundError,
    PromotionProductNotFoundError,
    PromotionProductInactiveError,
    PromotionConflictError,
    PromotionBusinessRuleError,
    AdminPromotionPersistenceError,
    SQLAlchemyError,
)


def _error_response(error: Exception) -> JSONResponse:
    if isinstance(error, (PromotionNotFoundError, PromotionProductNotFoundError)):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, PromotionConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(error, (PromotionProductInactiveError, PromotionBusinessRuleError)):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = str(error) if code != 500 else "No fue posible procesar la promocion"
    return JSONResponse(
        status_code=code,
        content={"success": False, "message": message},
    )


@router.get(
    "",
    response_model=AdminPromotionListResponse,
    summary="Listar promociones",
    responses=PROMOTION_ERROR_RESPONSES,
)
def list_promotions(
    administrator: AdminDependency,
    search: Annotated[str | None, Query(max_length=150)] = None,
    estado: bool | None = None,
    vigencia: Validity | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminPromotionListResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data, pagination = AdminPromotionService(db).list_promotions(
            search=search,
            state=estado,
            validity=vigencia,
            page=page,
            page_size=page_size,
        )
        return AdminPromotionListResponse(data=data, pagination=pagination)
    except OPERATION_ERRORS as error:
        db.rollback()
        return _error_response(error)


@router.get(
    "/{id_promocion}",
    response_model=AdminPromotionResponse,
    summary="Obtener detalle de promocion",
    responses=PROMOTION_ERROR_RESPONSES,
)
def get_promotion(
    id_promocion: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminPromotionResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminPromotionResponse(
            data=AdminPromotionService(db).get_promotion(id_promocion)
        )
    except OPERATION_ERRORS as error:
        db.rollback()
        return _error_response(error)


@router.post(
    "",
    response_model=AdminPromotionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear promocion",
    responses=PROMOTION_ERROR_RESPONSES,
)
def create_promotion(
    payload: PromotionCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminPromotionCreateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminPromotionCreateResponse(
            data=AdminPromotionService(db).create_promotion(payload)
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_promocion}",
    response_model=AdminPromotionUpdateResponse,
    summary="Actualizar promocion",
    responses=PROMOTION_ERROR_RESPONSES,
)
def update_promotion(
    id_promocion: int,
    payload: PromotionUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminPromotionUpdateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminPromotionUpdateResponse(
            message="Promocion actualizada correctamente",
            data=AdminPromotionService(db).update_promotion(
                promotion_id=id_promocion, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.patch(
    "/{id_promocion}/status",
    response_model=AdminPromotionUpdateResponse,
    summary="Activar o desactivar promocion",
    responses=PROMOTION_ERROR_RESPONSES,
)
def update_promotion_status(
    id_promocion: int,
    payload: PromotionStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminPromotionUpdateResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return AdminPromotionUpdateResponse(
            message="Estado de la promocion actualizado correctamente",
            data=AdminPromotionService(db).update_status(
                promotion_id=id_promocion, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)


@router.get(
    "/{id_promocion}/products",
    response_model=PromotionProductListResponse,
    summary="Consultar productos asociados a la promocion",
    responses=PROMOTION_ERROR_RESPONSES,
)
def list_promotion_products(
    id_promocion: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> PromotionProductListResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return PromotionProductListResponse(
            data=AdminPromotionService(db).list_products(id_promocion)
        )
    except OPERATION_ERRORS as error:
        db.rollback()
        return _error_response(error)


@router.post(
    "/{id_promocion}/products",
    response_model=PromotionProductsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asociar productos a la promocion",
    responses=PROMOTION_ERROR_RESPONSES,
)
def add_promotion_products(
    id_promocion: int,
    payload: PromotionProductsRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> PromotionProductsResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        return PromotionProductsResponse(
            message="Productos asociados correctamente",
            data=AdminPromotionService(db).add_products(
                promotion_id=id_promocion, payload=payload
            ),
        )
    except OPERATION_ERRORS as error:
        return _error_response(error)
