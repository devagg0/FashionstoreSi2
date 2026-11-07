"""Endpoints FastAPI para PK08 - CU10: Registrar reserva de prendas offline en FashionStore."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import set_tenant_context
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.dependencies import get_current_authenticated_user
from app.PK08.CU10_RegistrarReservaOffline.schemas import (
    OfflineReservationSyncRequest,
    OfflineReservationSyncResponse,
)
from app.PK08.CU10_RegistrarReservaOffline.service import (
    OfflineReservationError,
    OfflineReservationService,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/offline/reservas", tags=["PK08 - Reservas Offline"])

COMMON_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=OfflineReservationSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sincronizar reserva de prendas registrada offline por el CLIENTE",
    responses=COMMON_RESPONSES,
)
@router.post(
    "/sync",
    response_model=OfflineReservationSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Alias de sincronización de reserva offline del CLIENTE",
    responses=COMMON_RESPONSES,
)
def sync_offline_reservation(
    payload: OfflineReservationSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[
        int | None,
        Query(
            gt=0,
            description="Opcional; si se envía debe coincidir estrictamente con la empresa del CLIENTE autenticado",
        ),
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineReservationSyncResponse | JSONResponse:
    """Recibe y sincroniza una reserva de prendas creada por el CLIENTE en Angular PWA mientras estaba desconectado.

    - Exige rol CLIENTE autenticado (rechaza CAJERO y otros roles en la creación/sincronización).
    - Deriva empresa, usuario y perfil de cliente exclusivamente desde la sesión autenticada.
    - Exige suscripción SaaS activa y funcionalidad OFFLINE habilitada (CU07).
    - Valida producto, variante (talla/color), cantidad, sucursal, horario de atención y disponibilidad real.
    - Garantiza idempotencia por UUID e integra la reserva en t_reserva y t_detalle_reserva para atención por CAJERO.
    """
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineReservationService(db)
    try:
        if current_user.id_empresa:
            set_tenant_context(
                db,
                current_user.id_empresa,
                is_superadmin=False,
            )

        return service.sync_offline_reservation(
            current_user,
            payload,
            requested_company_id=empresa_id,
        )
    except OfflineReservationError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado en sincronización de reserva offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al procesar la reserva offline.",
        )
