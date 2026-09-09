"""Endpoint publico CU13; la unica dependencia es la sesion de lectura."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.catalog_availability import CatalogAvailabilityResponse
from app.services.catalog_availability import (
    AvailabilityNotFoundError, AvailabilityValidationError, CatalogAvailabilityService,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/catalog/products", tags=["Catalogo publico"])


@router.get("/{id_producto}/availability", response_model=CatalogAvailabilityResponse,
            summary="Consultar disponibilidad por sucursal",
            responses={400: {"description": "Variante ajena al producto"},
                       404: {"description": "Producto o variante no disponible"},
                       500: {"description": "Error al consultar disponibilidad"}})
def get_catalog_availability(
    id_producto: Annotated[int, Path(gt=0)],
    id_variante_producto: Annotated[int | None, Query(gt=0)] = None,
    id_sucursal: Annotated[int | None, Query(gt=0)] = None,
    id_ciudad: Annotated[int | None, Query(gt=0)] = None,
    id_talla: Annotated[int | None, Query(gt=0)] = None,
    id_color: Annotated[int | None, Query(gt=0)] = None,
    db: Session = Depends(get_db),
) -> CatalogAvailabilityResponse | JSONResponse:
    try:
        return CatalogAvailabilityResponse(data=CatalogAvailabilityService(db).get_availability(
            id_producto, id_variante_producto=id_variante_producto,
            id_sucursal=id_sucursal, id_ciudad=id_ciudad, id_talla=id_talla, id_color=id_color,
        ))
    except AvailabilityNotFoundError as error:
        code, message = 404, str(error)
    except AvailabilityValidationError as error:
        code, message = 400, str(error)
    except Exception:
        logger.exception("Error consultando disponibilidad CU13")
        code, message = 500, "No fue posible consultar la disponibilidad"
    return JSONResponse(status_code=code, content={
        "success": False, "data": None, "message": message,
    })
