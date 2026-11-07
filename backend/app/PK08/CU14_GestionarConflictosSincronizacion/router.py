"""Endpoints FastAPI para PK08 - CU14: Gestionar conflictos y resultados de sincronización."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import set_tenant_context
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.dependencies import get_current_authenticated_user
from app.PK08.CU14_GestionarConflictosSincronizacion.schemas import (
    OfflineConflictDiagnoseRequest,
    OfflineConflictDiagnoseResponse,
    OfflineConflictResolveRequest,
    OfflineConflictResolveResponse,
)
from app.PK08.CU14_GestionarConflictosSincronizacion.service import (
    OfflineConflictError,
    OfflineConflictManagementService,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/offline",
    tags=["PK08 - CU14: Gestionar Conflictos y Resultados de Sincronización"],
)

COMMON_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


def _apply_tenant_context(db: Session, current_user: AuthenticatedUserData) -> None:
    if current_user.id_empresa:
        set_tenant_context(
            db,
            current_user.id_empresa,
            is_superadmin=(current_user.rol.upper() == "SUPERADMIN"),
        )


def _execute_diagnose(
    payload: OfflineConflictDiagnoseRequest,
    current_user: AuthenticatedUserData | JSONResponse,
    empresa_id: int | None,
    db: Session,
) -> OfflineConflictDiagnoseResponse | JSONResponse:
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineConflictManagementService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.diagnose_conflicts(
            current_user,
            payload,
            requested_company_id=empresa_id,
        )
    except OfflineConflictError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado al diagnosticar conflictos offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al diagnosticar conflictos de sincronización.",
        )


def _execute_resolve(
    payload: OfflineConflictResolveRequest,
    current_user: AuthenticatedUserData | JSONResponse,
    empresa_id: int | None,
    db: Session,
) -> OfflineConflictResolveResponse | JSONResponse:
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineConflictManagementService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.resolve_conflicts(
            current_user,
            payload,
            requested_company_id=empresa_id,
        )
    except OfflineConflictError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado al resolver conflictos offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al resolver conflictos de sincronización.",
        )


@router.post(
    "/conflictos/diagnosticar",
    response_model=OfflineConflictDiagnoseResponse,
    status_code=status.HTTP_200_OK,
    summary="Diagnosticar y revalidar operaciones offline frente a PostgreSQL (stock, precios, horarios, reservas y dependencias)",
    responses=COMMON_RESPONSES,
)
def diagnose_offline_conflicts(
    payload: OfflineConflictDiagnoseRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[
        int | None, Query(gt=0, description="Opcional para validación multitenant")
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineConflictDiagnoseResponse | JSONResponse:
    """Evalúa el estado real del servidor sin mutar inventario y devuelve códigos de conflicto, motivos, datos actuales y acciones permitidas según rol."""
    return _execute_diagnose(payload, current_user, empresa_id, db)


@router.post(
    "/operaciones/diagnosticar",
    response_model=OfflineConflictDiagnoseResponse,
    status_code=status.HTTP_200_OK,
    summary="Diagnosticar operaciones offline desde la bandeja de operaciones (alias /api/offline/operaciones/diagnosticar)",
    responses=COMMON_RESPONSES,
)
def diagnose_offline_conflicts_from_tray(
    payload: OfflineConflictDiagnoseRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[
        int | None, Query(gt=0, description="Opcional para validación multitenant")
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineConflictDiagnoseResponse | JSONResponse:
    """Alias bajo /api/offline/operaciones/diagnosticar compatible con CU12/CU13."""
    return _execute_diagnose(payload, current_user, empresa_id, db)


@router.post(
    "/conflictos/resolver",
    response_model=OfflineConflictResolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolver y reintentar operaciones offline corregibles con consentimiento explícito del usuario",
    responses=COMMON_RESPONSES,
)
def resolve_offline_conflicts(
    payload: OfflineConflictResolveRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[
        int | None, Query(gt=0, description="Opcional para validación multitenant")
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineConflictResolveResponse | JSONResponse:
    """Revalida y ejecuta la resolución autorizada preservando UUID, historial, idempotencia y reglas de inventario/pagos."""
    return _execute_resolve(payload, current_user, empresa_id, db)


@router.post(
    "/operaciones/resolver",
    response_model=OfflineConflictResolveResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolver operaciones offline desde la bandeja de operaciones (alias /api/offline/operaciones/resolver)",
    responses=COMMON_RESPONSES,
)
def resolve_offline_conflicts_from_tray(
    payload: OfflineConflictResolveRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[
        int | None, Query(gt=0, description="Opcional para validación multitenant")
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineConflictResolveResponse | JSONResponse:
    """Alias bajo /api/offline/operaciones/resolver compatible con CU12/CU13."""
    return _execute_resolve(payload, current_user, empresa_id, db)

