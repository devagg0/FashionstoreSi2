"""API de CU17 para el cliente autenticado."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.auth import bearer_scheme
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.schemas.client_reservations import (
    ReservationCreateRequest,
    ReservationListResponse,
    ReservationResponse,
    ReservationState,
)
from app.services.auth_service import (
    AuthenticationConfigurationError,
    AuthService,
    InactiveAccountError,
    InvalidAccessTokenError,
)
from app.services.client_reservations import (
    ClientReservationService,
    ReservationConflictError,
    ReservationNotFoundError,
    ReservationPersistenceError,
    ReservationValidationError,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/client/reservations", tags=["Reservas del cliente"])


def _error(status_code: int, message: str, *, bearer=False):
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
        headers={"WWW-Authenticate": "Bearer"} if bearer else None,
    )


def require_client(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer_scheme)
    ],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error(401, "Token invalido o expirado", bearer=True)
    try:
        user = AuthService(db).get_current_user(credentials.credentials)
        if user.rol.upper() != "CLIENTE":
            return _error(403, "Se requiere el rol CLIENTE")
        return user
    except InvalidAccessTokenError:
        return _error(401, "Token invalido o expirado", bearer=True)
    except InactiveAccountError:
        return _error(403, "La cuenta se encuentra inactiva")
    except AuthenticationConfigurationError:
        return _error(500, "Error de configuracion del sistema")
    except Exception:
        logger.exception("Error validando cliente de CU17")
        return _error(500, "No fue posible validar la autenticacion")


ClientDependency = Annotated[
    AuthenticatedUserData | JSONResponse, Depends(require_client)
]

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Token invalido o expirado"},
    403: {"model": ErrorResponse, "description": "Se requiere rol CLIENTE"},
    404: {"model": ErrorResponse, "description": "Reserva o referencia inexistente"},
    409: {"model": ErrorResponse, "description": "Stock, estado o concurrencia"},
    422: {"description": "Datos o regla de negocio invalidos"},
    500: {"model": ErrorResponse, "description": "Error interno"},
}


def _operation_error(error):
    if isinstance(error, ReservationNotFoundError):
        return _error(404, str(error))
    if isinstance(error, ReservationValidationError):
        return _error(422, str(error))
    if isinstance(error, ReservationConflictError):
        return _error(409, str(error))
    logger.exception("Error interno de CU17", exc_info=error)
    return _error(500, "No fue posible procesar la reserva")


@router.post(
    "",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_reservation(
    payload: ReservationCreateRequest,
    client: ClientDependency,
    db: Session = Depends(get_db),
):
    if isinstance(client, JSONResponse):
        return client
    try:
        data = ClientReservationService(db).create_reservation(
            client.id_usuario, payload
        )
        return ReservationResponse(data=data, message="Reserva creada correctamente")
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)


@router.get("", response_model=ReservationListResponse, responses=ERROR_RESPONSES)
def list_reservations(
    client: ClientDependency,
    estado: ReservationState | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    if isinstance(client, JSONResponse):
        return client
    try:
        data, pagination = ClientReservationService(db).list_reservations(
            client.id_usuario,
            state=estado,
            page=page,
            page_size=page_size,
        )
        return ReservationListResponse(data=data, pagination=pagination)
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)


@router.get(
    "/{id_reserva}", response_model=ReservationResponse, responses=ERROR_RESPONSES
)
def get_reservation(
    id_reserva: Annotated[int, Path(gt=0)],
    client: ClientDependency,
    db: Session = Depends(get_db),
):
    if isinstance(client, JSONResponse):
        return client
    try:
        return ReservationResponse(
            data=ClientReservationService(db).get_reservation(
                client.id_usuario, id_reserva
            )
        )
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)


@router.patch(
    "/{id_reserva}/cancel",
    response_model=ReservationResponse,
    responses=ERROR_RESPONSES,
)
def cancel_reservation(
    id_reserva: Annotated[int, Path(gt=0)],
    client: ClientDependency,
    db: Session = Depends(get_db),
):
    if isinstance(client, JSONResponse):
        return client
    try:
        return ReservationResponse(
            data=ClientReservationService(db).cancel_reservation(
                client.id_usuario, id_reserva
            ),
            message="Reserva cancelada correctamente",
        )
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)
