"""Endpoints FastAPI para PK08 - CU12: Consultar operaciones locales offline y su estado en el servidor central."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import set_tenant_context
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.dependencies import get_current_authenticated_user
from app.PK08.CU12_ConsultarOperacionesPendientes.schemas import (
    OfflineBatchStatusQueryRequest,
    OfflineBatchStatusQueryResponse,
    OfflineOperationsListResponse,
    OfflineOperationStatusResponse,
)
from app.PK08.CU12_ConsultarOperacionesPendientes.service import (
    OfflineOperationError,
    OfflineOperationStatusService,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/offline/operaciones", tags=["PK08 - CU12: Consultar Operaciones Offline"])

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


@router.get(
    "/status/{uuid_operacion}",
    response_model=OfflineOperationStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar estado en el servidor de una operación offline por su UUID",
    responses=COMMON_RESPONSES,
)
def get_offline_operation_status(
    uuid_operacion: str,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0, description="Opcional para SUPERADMIN")] = None,
    db: Session = Depends(get_db),
) -> OfflineOperationStatusResponse | JSONResponse:
    """Consulta de solo lectura para verificar si una operación offline específica ya fue sincronizada en PostgreSQL."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineOperationStatusService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.get_operation_status(
            current_user,
            uuid_operacion,
            requested_company_id=empresa_id,
        )
    except OfflineOperationError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error al consultar estado de operación offline %s: %s", uuid_operacion, exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al consultar el estado de la operación offline.",
        )


@router.post(
    "/status/batch",
    response_model=OfflineBatchStatusQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Verificar en lote el estado en el servidor de múltiples UUIDs offline",
    responses=COMMON_RESPONSES,
)
def query_batch_offline_operations_status(
    payload: OfflineBatchStatusQueryRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0, description="Opcional para SUPERADMIN")] = None,
    db: Session = Depends(get_db),
) -> OfflineBatchStatusQueryResponse | JSONResponse:
    """Verifica de forma masiva y de solo lectura qué operaciones de la cola offline ya alcanzaron el servidor."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineOperationStatusService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.query_batch_status(
            current_user,
            payload.uuids,
            requested_company_id=empresa_id,
        )
    except OfflineOperationError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error al consultar estados de operaciones offline en lote: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al verificar las operaciones offline en lote.",
        )


@router.get(
    "/sincronizadas",
    response_model=OfflineOperationsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Listar operaciones offline sincronizadas para el actor o sucursal",
    responses=COMMON_RESPONSES,
)
def list_synced_offline_operations(
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    id_sucursal: Annotated[int | None, Query(gt=0, description="Filtrar por sucursal autorizada")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Límite de registros a retornar")] = 50,
    empresa_id: Annotated[int | None, Query(gt=0, description="Opcional para SUPERADMIN")] = None,
    db: Session = Depends(get_db),
) -> OfflineOperationsListResponse | JSONResponse:
    """Lista las operaciones offline que ya fueron registradas y sincronizadas en PostgreSQL."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineOperationStatusService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.list_synced_operations(
            current_user,
            branch_id=id_sucursal,
            requested_company_id=empresa_id,
            limit=limit,
        )
    except OfflineOperationError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error al listar operaciones offline sincronizadas: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al listar operaciones offline sincronizadas.",
        )

