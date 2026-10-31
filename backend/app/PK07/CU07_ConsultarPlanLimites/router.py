"""Endpoints FastAPI para PK07 / CU07: Consultar plan, límites y funcionalidades habilitadas."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.dependencies import get_current_authenticated_user
from app.PK07.CU07_ConsultarPlanLimites.schemas import (
    CompanyBranchConsumptionResponse,
    CompanyPlanLimitsResponse,
)
from app.PK07.CU07_ConsultarPlanLimites.service import (
    CompanyNotFoundError,
    SaasPlanLimitsService,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse

router = APIRouter(prefix="/api/saas", tags=["PK07 - Plan y Límites SaaS"])

COMMON_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


def _resolve_company_for_user(
    user: AuthenticatedUserData,
    requested_company_id: int | None,
) -> int | JSONResponse:
    """Verifica permisos de aislamiento tenant para la consulta del plan y sus límites."""
    role = user.rol.upper()

    if role == "ADMINISTRADOR":
        if not user.id_empresa:
            return _error_response(
                status.HTTP_403_FORBIDDEN,
                "El administrador no tiene una empresa asociada",
            )
        if requested_company_id is not None and requested_company_id != user.id_empresa:
            return _error_response(
                status.HTTP_403_FORBIDDEN,
                "Acceso denegado: un administrador solo puede consultar su propio tenant",
            )
        return user.id_empresa

    if role == "SUPERADMIN":
        if requested_company_id is None:
            return _error_response(
                status.HTTP_400_BAD_REQUEST,
                "Debe especificar el parámetro 'empresa_id' para la consulta administrativa",
            )
        return requested_company_id

    return _error_response(
        status.HTTP_403_FORBIDDEN,
        "Se requiere rol ADMINISTRADOR o SUPERADMIN para consultar el plan y límites",
    )


@router.get(
    "/plan-vigente",
    response_model=CompanyPlanLimitsResponse,
    summary="Consultar plan vigente, límites parametrizados y funcionalidades habilitadas",
    responses=COMMON_RESPONSES,
)
def get_current_plan_limits(
    current_user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
    empresa_id: Annotated[int | None, Query(gt=0, description="ID de empresa (requerido para SUPERADMIN)")] = None,
    db: Session = Depends(get_db),
) -> CompanyPlanLimitsResponse | JSONResponse:
    """Retorna el plan vigente, las funcionalidades y los límites de consumo para la empresa."""
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company = _resolve_company_for_user(current_user, empresa_id)
    if isinstance(target_company, JSONResponse):
        return target_company

    service = SaasPlanLimitsService(db)
    try:
        return service.get_company_plan_limits(target_company)
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error al consultar el plan vigente y límites de la empresa",
        )


@router.get(
    "/plan-vigente/consumo-sucursales",
    response_model=CompanyBranchConsumptionResponse,
    summary="Consultar consumo y disponibilidad de sucursales según el plan contratado",
    responses=COMMON_RESPONSES,
)
def get_current_branch_consumption(
    current_user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
    empresa_id: Annotated[int | None, Query(gt=0, description="ID de empresa (requerido para SUPERADMIN)")] = None,
    db: Session = Depends(get_db),
) -> CompanyBranchConsumptionResponse | JSONResponse:
    """Retorna el estado de ocupación de sucursales activas contra el límite configurado."""
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company = _resolve_company_for_user(current_user, empresa_id)
    if isinstance(target_company, JSONResponse):
        return target_company

    service = SaasPlanLimitsService(db)
    try:
        return service.get_company_branch_consumption(target_company)
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error al consultar el consumo de sucursales de la empresa",
        )


@router.get(
    "/empresas/{id}/plan-vigente",
    response_model=CompanyPlanLimitsResponse,
    summary="Consultar plan vigente y límites de una empresa específica",
    responses=COMMON_RESPONSES,
)
def get_company_plan_limits_by_id(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    current_user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
    db: Session = Depends(get_db),
) -> CompanyPlanLimitsResponse | JSONResponse:
    """Consulta administrativa del plan vigente y límites de una empresa por ID."""
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company = _resolve_company_for_user(current_user, company_id)
    if isinstance(target_company, JSONResponse):
        return target_company

    service = SaasPlanLimitsService(db)
    try:
        return service.get_company_plan_limits(target_company)
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error al consultar el plan vigente de la empresa",
        )


@router.get(
    "/empresas/{id}/consumo-sucursales",
    response_model=CompanyBranchConsumptionResponse,
    summary="Consultar detalle de sucursales y consumo de límites de una empresa",
    responses=COMMON_RESPONSES,
)
def get_company_branch_consumption_by_id(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    current_user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
    db: Session = Depends(get_db),
) -> CompanyBranchConsumptionResponse | JSONResponse:
    """Consulta detallada de sucursales activas contra el límite de la empresa."""
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company = _resolve_company_for_user(current_user, company_id)
    if isinstance(target_company, JSONResponse):
        return target_company

    service = SaasPlanLimitsService(db)
    try:
        return service.get_company_branch_consumption(target_company)
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error al consultar el consumo de sucursales de la empresa",
        )

