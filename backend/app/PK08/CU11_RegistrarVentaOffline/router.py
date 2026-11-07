"""Endpoints FastAPI para PK08 - CU11: Registrar venta de contado y compra digital offline en FashionStore."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import set_tenant_context
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.dependencies import get_current_authenticated_user
from app.PK08.CU11_RegistrarVentaOffline.schemas import (
    OfflineBatchSyncRequest,
    OfflineBatchSyncResponse,
    OfflineReservationTransitionRequest,
    OfflineReservationTransitionResponse,
    OfflineSaleSyncRequest,
    OfflineSaleSyncResponse,
)
from app.PK08.CU11_RegistrarVentaOffline.service import (
    OfflineSaleError,
    OfflineSaleService,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/offline/ventas", tags=["PK08 - Ventas y Compras Offline"])

COMMON_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


def _apply_tenant_context(
    db: Session, current_user: AuthenticatedUserData
) -> None:
    if current_user.id_empresa:
        set_tenant_context(
            db,
            current_user.id_empresa,
            is_superadmin=False,
        )


@router.post(
    "",
    response_model=OfflineSaleSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar venta presencial (POS) o compra digital registrada offline",
    responses=COMMON_RESPONSES,
)
@router.post(
    "/sync",
    response_model=OfflineSaleSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Alias de sincronización de venta presencial o compra digital offline",
    responses=COMMON_RESPONSES,
)
def sync_offline_sale(
    payload: OfflineSaleSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[
        int | None,
        Query(
            gt=0,
            description="Opcional; si se envía debe coincidir estrictamente con la empresa de la sesión autenticada",
        ),
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineSaleSyncResponse | JSONResponse:
    """Recibe y sincroniza una venta presencial del CAJERO (directa o por reserva) o compra digital del CLIENTE."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineSaleService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.sync_offline_sale(
            current_user,
            payload,
            requested_company_id=empresa_id,
        )
    except OfflineSaleError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado en sincronización de venta offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al procesar la venta o compra offline.",
        )


@router.post(
    "/digital",
    response_model=OfflineSaleSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar compra digital offline del CLIENTE (carrito -> checkout -> pago QR/tarjeta simulado)",
    responses=COMMON_RESPONSES,
)
def sync_offline_digital_purchase(
    payload: OfflineSaleSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0)] = None,
    db: Session = Depends(get_db),
) -> OfflineSaleSyncResponse | JSONResponse:
    """Endpoint específico para compra digital offline del CLIENTE con pago QR o TARJETA simulado."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineSaleService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.sync_offline_sale(
            current_user,
            payload,
            requested_company_id=empresa_id,
            forced_channel="DIGITAL",
        )
    except OfflineSaleError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado en compra digital offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al procesar la compra digital offline.",
        )


@router.post(
    "/presencial",
    response_model=OfflineSaleSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar venta presencial POS offline del CAJERO (directa o por reserva)",
    responses=COMMON_RESPONSES,
)
def sync_offline_pos_sale(
    payload: OfflineSaleSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0)] = None,
    db: Session = Depends(get_db),
) -> OfflineSaleSyncResponse | JSONResponse:
    """Endpoint específico para venta presencial POS del CAJERO (efectivo cobrado físicamente o QR/tarjeta simulados)."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineSaleService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.sync_offline_sale(
            current_user,
            payload,
            requested_company_id=empresa_id,
            forced_channel="PRESENCIAL",
        )
    except OfflineSaleError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado en venta presencial offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al procesar la venta presencial offline.",
        )


@router.post(
    "/reservas/transicion",
    response_model=OfflineReservationTransitionResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar transición offline de reserva por CAJERO (PENDIENTE -> CONFIRMADA -> ATENDIDA)",
    responses=COMMON_RESPONSES,
)
def sync_offline_reservation_transition(
    payload: OfflineReservationTransitionRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0)] = None,
    db: Session = Depends(get_db),
) -> OfflineReservationTransitionResponse | JSONResponse:
    """Sincroniza la confirmación de preparación o atención de una reserva antes de su venta en POS."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineSaleService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.sync_reservation_transition(
            current_user,
            payload,
            requested_company_id=empresa_id,
        )
    except OfflineSaleError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado en transición de reserva offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al procesar la transición de la reserva.",
        )


@router.post(
    "/lote",
    response_model=OfflineBatchSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar lote secuencial ordenado de operaciones offline dependientes",
    responses=COMMON_RESPONSES,
)
@router.post(
    "/batch",
    response_model=OfflineBatchSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Alias para sincronización secuencial en lote de operaciones offline",
    responses=COMMON_RESPONSES,
)
def sync_offline_batch(
    payload: OfflineBatchSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[int | None, Query(gt=0)] = None,
    db: Session = Depends(get_db),
) -> OfflineBatchSyncResponse | JSONResponse:
    """Procesa en orden estricto una secuencia de operaciones dependientes (ej. confirmar -> atender -> venta POS)."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineSaleService(db)
    try:
        _apply_tenant_context(db, current_user)
        return service.sync_batch_operations(
            current_user,
            payload,
            requested_company_id=empresa_id,
        )
    except OfflineSaleError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado en lote de operaciones offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al procesar el lote de operaciones offline.",
        )

