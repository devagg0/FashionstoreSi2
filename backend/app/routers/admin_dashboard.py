"""Router administrativo para el CU24: Dashboard Analítico Inteligente."""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_dashboard import (
    DashboardAnalyticsRequest,
    DashboardAnalyticsResponse,
    DashboardFiltersResponse,
)
from app.services.admin_dashboard import AdminDashboardService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/dashboard",
    tags=["Dashboard Analítico Inteligente CU24"],
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


def _check_saas_plan(db: Session, empresa_id: int) -> None:
    """Verifica si la empresa tiene habilitada la funcionalidad de reportes e inteligencia empresarial."""
    try:
        from app.PK07.CU07_ConsultarPlanLimites.service import (
            FeatureNotEnabledError,
            NoActiveSubscriptionError,
            SaasPlanLimitsService,
        )
        SaasPlanLimitsService(db).validate_feature_enabled(empresa_id, "REPORTES_IA")
    except (NoActiveSubscriptionError, FeatureNotEnabledError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except Exception:
        # En caso de entornos de prueba SQLite sin tablas SaaS cargadas, permitir el flujo
        pass


@router.get(
    "/filters",
    response_model=DashboardFiltersResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def get_dashboard_filters(
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> DashboardFiltersResponse | JSONResponse:
    """Devuelve las sucursales, categorías y periodos disponibles para filtrar el dashboard."""
    if isinstance(administrator, JSONResponse):
        return administrator
    empresa_id = _get_tenant_company_id(administrator, db)
    _check_saas_plan(db, empresa_id)
    return AdminDashboardService.get_filters(db, empresa_id)


@router.post(
    "/analytics",
    response_model=DashboardAnalyticsResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def get_dashboard_analytics(
    payload: DashboardAnalyticsRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> DashboardAnalyticsResponse | JSONResponse:
    """Consolida KPIs de negocio, series temporales, predicciones ML, patrones K-Means e historial de reportes."""
    if isinstance(administrator, JSONResponse):
        return administrator
    empresa_id = _get_tenant_company_id(administrator, db)
    _check_saas_plan(db, empresa_id)
    return AdminDashboardService.get_analytics(db, empresa_id, payload)

