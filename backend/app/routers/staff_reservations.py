"""API de CU18 para gestionar reservas en sucursales asignadas."""

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.auth import bearer_scheme
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.schemas.client_reservations import ReservationState
from app.schemas.staff_reservations import (
    StaffReservationListResponse,
    StaffReservationResponse,
)
from app.services.admin_user_service import EMPLOYEE_ROLE_NAMES
from app.services.auth_service import (
    AuthenticationConfigurationError,
    AuthService,
    InactiveAccountError,
    InvalidAccessTokenError,
)
from app.services.client_reservations import (
    ReservationConflictError,
    ReservationNotFoundError,
    ReservationPersistenceError,
    ReservationValidationError,
)
from app.services.staff_reservations import (
    StaffReservationAccessError,
    StaffReservationService,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/staff/reservations", tags=["Atencion de reservas"])


def _error(status_code: int, message: str, *, bearer=False):
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
        headers={"WWW-Authenticate": "Bearer"} if bearer else None,
    )


def require_reservation_staff(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(bearer_scheme)
    ],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error(401, "Token invalido o expirado", bearer=True)
    try:
        user = AuthService(db).get_current_user(credentials.credentials)
        if user.rol.upper() not in EMPLOYEE_ROLE_NAMES:
            return _error(403, "Se requiere rol CAJERO o ENCARGADO_SUCURSAL")
        return user
    except InvalidAccessTokenError:
        return _error(401, "Token invalido o expirado", bearer=True)
    except InactiveAccountError:
        return _error(403, "La cuenta se encuentra inactiva")
    except AuthenticationConfigurationError:
        return _error(500, "Error de configuracion del sistema")
    except Exception:
        logger.exception("Error validando personal de CU18")
        return _error(500, "No fue posible validar la autenticacion")


StaffDependency = Annotated[
    AuthenticatedUserData | JSONResponse, Depends(require_reservation_staff)
]

ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Token invalido o expirado"},
    403: {"model": ErrorResponse, "description": "Rol, empleado o sucursal invalida"},
    404: {"model": ErrorResponse, "description": "Reserva no encontrada en la sucursal"},
    409: {"model": ErrorResponse, "description": "Estado o concurrencia"},
    422: {"description": "Parametros o regla de negocio invalidos"},
    500: {"model": ErrorResponse, "description": "Error interno"},
}


def _operation_error(error):
    if isinstance(error, StaffReservationAccessError):
        return _error(403, str(error))
    if isinstance(error, ReservationNotFoundError):
        return _error(404, str(error))
    if isinstance(error, ReservationValidationError):
        return _error(422, str(error))
    if isinstance(error, ReservationConflictError):
        return _error(409, str(error))
    logger.exception("Error interno de CU18", exc_info=error)
    return _error(500, "No fue posible procesar la reserva")


@router.get("", response_model=StaffReservationListResponse, responses=ERROR_RESPONSES)
def list_reservations(
    staff: StaffDependency,
    estado: ReservationState | None = None,
    fecha_programada: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    if isinstance(staff, JSONResponse):
        return staff
    try:
        data, pagination = StaffReservationService(db).list_reservations(
            staff.id_usuario,
            state=estado,
            scheduled_date=fecha_programada,
            page=page,
            page_size=page_size,
        )
        return StaffReservationListResponse(data=data, pagination=pagination)
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)


@router.get(
    "/code/{codigo}", response_model=StaffReservationResponse, responses=ERROR_RESPONSES
)
def get_reservation_by_code(
    codigo: Annotated[str, Path(min_length=1, max_length=50)],
    staff: StaffDependency,
    db: Session = Depends(get_db),
):
    if isinstance(staff, JSONResponse):
        return staff
    try:
        return StaffReservationResponse(
            data=StaffReservationService(db).get_reservation_by_code(
                staff.id_usuario, codigo
            )
        )
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)


@router.get(
    "/{id_reserva}", response_model=StaffReservationResponse, responses=ERROR_RESPONSES
)
def get_reservation(
    id_reserva: Annotated[int, Path(gt=0)],
    staff: StaffDependency,
    db: Session = Depends(get_db),
):
    if isinstance(staff, JSONResponse):
        return staff
    try:
        return StaffReservationResponse(
            data=StaffReservationService(db).get_reservation(
                staff.id_usuario, id_reserva
            )
        )
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)


def _transition(staff, db, reservation_id, action):
    if isinstance(staff, JSONResponse):
        return staff
    try:
        data = action(StaffReservationService(db), staff.id_usuario, reservation_id)
        return StaffReservationResponse(data=data)
    except (
        ReservationNotFoundError,
        ReservationValidationError,
        ReservationConflictError,
        ReservationPersistenceError,
    ) as error:
        return _operation_error(error)


@router.patch(
    "/{id_reserva}/confirm",
    response_model=StaffReservationResponse,
    responses=ERROR_RESPONSES,
)
def confirm_reservation(
    id_reserva: Annotated[int, Path(gt=0)],
    staff: StaffDependency,
    db: Session = Depends(get_db),
):
    result = _transition(
        staff,
        db,
        id_reserva,
        lambda service, user_id, reservation_id: service.confirm_reservation(
            user_id, reservation_id
        ),
    )
    if isinstance(result, StaffReservationResponse):
        result.message = "Reserva confirmada correctamente"
    return result


@router.patch(
    "/{id_reserva}/attend",
    response_model=StaffReservationResponse,
    responses=ERROR_RESPONSES,
)
def attend_reservation(
    id_reserva: Annotated[int, Path(gt=0)],
    staff: StaffDependency,
    db: Session = Depends(get_db),
):
    result = _transition(
        staff,
        db,
        id_reserva,
        lambda service, user_id, reservation_id: service.attend_reservation(
            user_id, reservation_id
        ),
    )
    if isinstance(result, StaffReservationResponse):
        result.message = "Reserva atendida correctamente"
    return result
