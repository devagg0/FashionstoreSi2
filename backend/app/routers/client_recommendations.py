"""CU26: recomendaciones de prendas para el CLIENTE autenticado. Solo GET."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.client_reservations import ClientDependency
from app.schemas.auth import ErrorResponse
from app.schemas.client_recommendations import RecommendationListResponse
from app.services.catalog import (
    CatalogFilterError,
    CatalogReferenceInactiveError,
    CatalogReferenceNotFoundError,
)
from app.services.client_recommendations import (
    ClientRecommendationsService,
    RecommendationAccessError,
)


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/client/recommendations",
    tags=["Recomendaciones del cliente CU26"],
)

ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Token invalido o expirado",
    },
    status.HTTP_403_FORBIDDEN: {
        "model": ErrorResponse,
        "description": "Se requiere el rol CLIENTE con perfil asociado",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Sucursal o ciudad no encontrada",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "description": "Sucursal o ciudad no disponible, o filtros incompatibles",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "Error interno",
    },
}


@router.get("", response_model=RecommendationListResponse, responses=ERROR_RESPONSES)
def list_recommendations(
    client: ClientDependency,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    id_sucursal: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
    id_ciudad: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
):
    # require_client devuelve el error en lugar de lanzarlo (patron de CU17/19/23).
    if isinstance(client, JSONResponse):
        return client
    try:
        data, origen = ClientRecommendationsService(db).recommend(
            client.id_usuario,
            limit=limit,
            branch_id=id_sucursal,
            city_id=id_ciudad,
        )
    except RecommendationAccessError as error:
        return _error(status.HTTP_403_FORBIDDEN, str(error))
    except CatalogReferenceNotFoundError as error:
        return _error(status.HTTP_404_NOT_FOUND, str(error))
    except (CatalogReferenceInactiveError, CatalogFilterError) as error:
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))
    except Exception:
        logger.exception("Error interno de CU26")
        return _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible generar las recomendaciones",
        )
    return RecommendationListResponse(data=data, origen=origen)


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
    )
