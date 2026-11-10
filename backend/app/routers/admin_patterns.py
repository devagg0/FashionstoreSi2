"""Router administrativo para el CU23: Análisis de patrones de comportamiento con K-Means."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_patterns import (
    PatternAnalysisRequest,
    PatternAnalysisResponse,
    PatternFiltersResponse,
    PatternModelInfoResponse,
)
from app.services.admin_patterns import AdminPatternsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/patterns",
    tags=["Análisis de Patrones Machine Learning CU23"],
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
    response_model=PatternModelInfoResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def get_model_info(
    administrator: AdminDependency,
) -> PatternModelInfoResponse | JSONResponse:
    """Obtiene los metadatos y evaluación del modelo no supervisado K-Means."""
    if isinstance(administrator, JSONResponse):
        return administrator
    return AdminPatternsService.get_model_info()


@router.get(
    "/filters",
    response_model=PatternFiltersResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def get_pattern_filters(
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> PatternFiltersResponse | JSONResponse:
    """Obtiene sucursales y categorías activas de la empresa para filtrar el análisis."""
    if isinstance(administrator, JSONResponse):
        return administrator
    empresa_id = _get_tenant_company_id(administrator, db)
    return AdminPatternsService.get_filters(db, empresa_id)


@router.post(
    "/analyze",
    response_model=PatternAnalysisResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def analyze_patterns(
    payload: PatternAnalysisRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> PatternAnalysisResponse | JSONResponse:
    """Ejecuta el análisis de agrupamiento no supervisado K-Means sobre las prendas de la empresa."""
    if isinstance(administrator, JSONResponse):
        return administrator
    empresa_id = _get_tenant_company_id(administrator, db)
    return AdminPatternsService.analyze_patterns(db, empresa_id, payload)

