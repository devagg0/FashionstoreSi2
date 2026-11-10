"""Router administrativo para el CU22: Predicciones de demanda con Machine Learning."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_predictions import (
    ModelInfoResponse,
    PredictionFiltersResponse,
    PredictionRequest,
    PredictionResponse,
)
from app.services.admin_predictions import AdminPredictionsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/predictions",
    tags=["Predicciones Machine Learning CU22"],
)


def _get_tenant_company_id(administrator: AdminDependency, db: Session) -> int:
    """Extrae y valida el ID de la empresa del administrador autenticado."""
    company_id = getattr(administrator, "id_empresa", None) or getattr(db, "info", {}).get("empresa_id")
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudo determinar la empresa del administrador.",
        )
    return int(company_id)


@router.get(
    "/model-info",
    response_model=ModelInfoResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def get_model_info(
    administrator: AdminDependency,
) -> ModelInfoResponse | JSONResponse:
    """Obtiene los metadatos, algoritmo y métricas de evaluación reales del modelo ML."""
    if isinstance(administrator, JSONResponse):
        return administrator
    return AdminPredictionsService.get_model_info()


@router.get(
    "/filters",
    response_model=PredictionFiltersResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def get_prediction_filters(
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> PredictionFiltersResponse | JSONResponse:
    """Obtiene las opciones de filtrado (productos y sucursales) de la empresa."""
    if isinstance(administrator, JSONResponse):
        return administrator
    empresa_id = _get_tenant_company_id(administrator, db)
    return AdminPredictionsService.get_filters(db, empresa_id)


@router.post(
    "/predict",
    response_model=PredictionResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def generate_prediction(
    payload: PredictionRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> PredictionResponse | JSONResponse:
    """Genera una predicción de demanda supervisada para un producto, sucursal y horizonte."""
    if isinstance(administrator, JSONResponse):
        return administrator
    empresa_id = _get_tenant_company_id(administrator, db)
    return AdminPredictionsService.generate_prediction(db, empresa_id, payload)

