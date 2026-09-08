"""Endpoints publicos de CU12 para consultar el catalogo."""

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import ErrorResponse
from app.schemas.catalog import (
    CatalogProductListResponse,
    CatalogProductResponse,
    CatalogSort,
)
from app.services.catalog import (
    CatalogFilterError,
    CatalogProductNotFoundError,
    CatalogReferenceInactiveError,
    CatalogReferenceNotFoundError,
    CatalogService,
)


router = APIRouter(prefix="/api/catalog/products", tags=["Catalogo publico"])

CATALOG_ERROR_RESPONSES = {
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Producto, sucursal o ciudad no encontrada",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "Sucursal, ciudad o combinacion de filtros no disponible",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "No fue posible consultar el catalogo",
    },
}

OPERATION_ERRORS = (
    CatalogProductNotFoundError,
    CatalogReferenceNotFoundError,
    CatalogReferenceInactiveError,
    CatalogFilterError,
    SQLAlchemyError,
)


def _error_response(error: Exception) -> JSONResponse:
    if isinstance(
        error, (CatalogProductNotFoundError, CatalogReferenceNotFoundError)
    ):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, (CatalogReferenceInactiveError, CatalogFilterError)):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = str(error) if code != 500 else "No fue posible consultar el catalogo"
    return JSONResponse(
        status_code=code,
        content={"success": False, "message": message},
    )


@router.get(
    "",
    response_model=CatalogProductListResponse,
    summary="Consultar catalogo publico",
    responses=CATALOG_ERROR_RESPONSES,
)
def list_catalog_products(
    search: Annotated[str | None, Query(max_length=150)] = None,
    seccion: Literal["HOMBRE", "MUJER", "UNISEX"] | None = None,
    id_categoria: Annotated[int | None, Query(gt=0)] = None,
    id_talla: Annotated[int | None, Query(gt=0)] = None,
    id_color: Annotated[int | None, Query(gt=0)] = None,
    precio_min: Annotated[Decimal | None, Query(ge=0)] = None,
    precio_max: Annotated[Decimal | None, Query(ge=0)] = None,
    en_promocion: bool | None = None,
    id_sucursal: Annotated[int | None, Query(gt=0)] = None,
    id_ciudad: Annotated[int | None, Query(gt=0)] = None,
    sort: CatalogSort = "recientes",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> CatalogProductListResponse | JSONResponse:
    if precio_min is not None and precio_max is not None and precio_min > precio_max:
        return _error_response(
            CatalogFilterError("precio_min no puede ser mayor que precio_max")
        )
    try:
        data, pagination = CatalogService(db).list_products(
            search=search,
            section=seccion,
            category_id=id_categoria,
            size_id=id_talla,
            color_id=id_color,
            min_price=precio_min,
            max_price=precio_max,
            on_promotion=en_promocion,
            branch_id=id_sucursal,
            city_id=id_ciudad,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        return CatalogProductListResponse(data=data, pagination=pagination)
    except OPERATION_ERRORS as error:
        db.rollback()
        return _error_response(error)


@router.get(
    "/{id_producto}",
    response_model=CatalogProductResponse,
    summary="Consultar detalle publico de producto",
    responses=CATALOG_ERROR_RESPONSES,
)
def get_catalog_product(
    id_producto: Annotated[int, Path(gt=0)],
    id_sucursal: Annotated[int | None, Query(gt=0)] = None,
    db: Session = Depends(get_db),
) -> CatalogProductResponse | JSONResponse:
    try:
        return CatalogProductResponse(
            data=CatalogService(db).get_product(
                id_producto, branch_id=id_sucursal
            )
        )
    except OPERATION_ERRORS as error:
        db.rollback()
        return _error_response(error)
