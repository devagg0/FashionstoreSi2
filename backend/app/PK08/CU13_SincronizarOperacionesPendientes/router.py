"""Endpoints FastAPI para PK08 - CU13: Sincronizar operaciones pendientes (CLIENTE y CAJERO)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import set_tenant_context
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.dependencies import get_current_authenticated_user
from app.PK08.CU13_SincronizarOperacionesPendientes.schemas import (
    OfflineQueueSyncRequest,
    OfflineQueueSyncResponse,
)
from app.PK08.CU13_SincronizarOperacionesPendientes.service import (
    OfflineQueueSyncError,
    OfflineQueueSyncService,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/offline",
    tags=["PK08 - CU13: Sincronizar Operaciones Pendientes"],
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


def _execute_queue_sync(
    payload: OfflineQueueSyncRequest,
    current_user: AuthenticatedUserData | JSONResponse,
    empresa_id: int | None,
    db: Session,
) -> OfflineQueueSyncResponse | JSONResponse:
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineQueueSyncService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.sync_pending_operations(
            current_user,
            payload,
            requested_company_id=empresa_id,
        )
    except OfflineQueueSyncError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado al sincronizar lote de operaciones pendientes: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al sincronizar el lote de operaciones pendientes.",
        )


@router.post(
    "/sincronizar",
    response_model=OfflineQueueSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar lote unificado de operaciones offline pendientes (RESERVA, COMPRA, VENTA, TRANSICION_RESERVA)",
    responses=COMMON_RESPONSES,
)
def sync_pending_offline_operations(
    payload: OfflineQueueSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0, description="Opcional para SUPERADMIN")] = None,
    db: Session = Depends(get_db),
) -> OfflineQueueSyncResponse | JSONResponse:
    """Procesa un lote unificado de operaciones de la cola IndexedDB con atomicidad individual, idempotencia y resolución de dependencias."""
    return _execute_queue_sync(payload, current_user, empresa_id, db)


@router.post(
    "/sync",
    response_model=OfflineQueueSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar lote unificado de operaciones offline pendientes (alias /api/offline/sync)",
    responses=COMMON_RESPONSES,
)
def sync_pending_offline_operations_alias(
    payload: OfflineQueueSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0, description="Opcional para SUPERADMIN")] = None,
    db: Session = Depends(get_db),
) -> OfflineQueueSyncResponse | JSONResponse:
    """Alias compatible para sincronización masiva de la cola offline."""
    return _execute_queue_sync(payload, current_user, empresa_id, db)


@router.post(
    "/operaciones/sincronizar",
    response_model=OfflineQueueSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar lote de operaciones offline pendientes desde la bandeja de operaciones (CU12/CU13)",
    responses=COMMON_RESPONSES,
)
def sync_pending_offline_operations_from_tray(
    payload: OfflineQueueSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0, description="Opcional para SUPERADMIN")] = None,
    db: Session = Depends(get_db),
) -> OfflineQueueSyncResponse | JSONResponse:
    """Ruta bajo /api/offline/operaciones/sincronizar integrada con los contratos de CU12."""
    return _execute_queue_sync(payload, current_user, empresa_id, db)


@router.post(
    "/operaciones/sync",
    response_model=OfflineQueueSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar lote de operaciones offline pendientes (alias /api/offline/operaciones/sync)",
    responses=COMMON_RESPONSES,
)
def sync_pending_offline_operations_from_tray_alias(
    payload: OfflineQueueSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0, description="Opcional para SUPERADMIN")] = None,
    db: Session = Depends(get_db),
) -> OfflineQueueSyncResponse | JSONResponse:
    """Alias bajo /api/offline/operaciones/sync para sincronizar la cola local."""
    return _execute_queue_sync(payload, current_user, empresa_id, db)

