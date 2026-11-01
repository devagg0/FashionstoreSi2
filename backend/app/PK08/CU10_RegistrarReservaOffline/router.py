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
    summary="Sincronizar reserva de prendas registrada offline",
    responses=COMMON_RESPONSES,
)
@router.post(
    "/sync",
    response_model=OfflineReservationSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Alias de sincronización de reserva offline",
    responses=COMMON_RESPONSES,
)
def sync_offline_reservation(
    payload: OfflineReservationSyncRequest,
    current_user: Annotated[
        AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)
    ],
    empresa_id: Annotated[
        int | None,
        Query(gt=0, description="ID de empresa (requerido únicamente para SUPERADMIN)"),
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineReservationSyncResponse | JSONResponse:
    """Recibe una reserva de prendas creada en Angular PWA mientras estaba desconectado.

    - Exige autenticación y deriva empresa/usuario exclusivamente del JWT.
    - Valida rol autorizado (ADMINISTRADOR, ENCARGADO_SUCURSAL, CAJERO).
    - Exige suscripción SaaS activa y módulo OFFLINE habilitado (CU07).
    - Valida pertenencia de sucursal, cliente y variantes a la empresa.
    - Comprueba disponibilidad real en PostgreSQL y reserva inventario atómicamente.
    - Garantiza idempotencia estricta por UUID persistiendo el resultado en t_reserva_offline_sync.
    """
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineReservationService(db)
    try:
        effective_company_id = empresa_id or current_user.id_empresa
        if effective_company_id:
            set_tenant_context(
                db,
                effective_company_id,
                is_superadmin=(current_user.rol.upper() == "SUPERADMIN"),
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

