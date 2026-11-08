from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Path, Query, Security
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from fastapi.security import HTTPAuthorizationCredentials
from app.core.database import get_db
from app.routers.auth import bearer_scheme
from app.routers.client_reservations import ClientDependency
from app.routers.staff_sales import _error
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.schemas.returns import (
    CancellationRequest,
    CheckoutSessionResponse,
    ConfirmPaymentRequest,
    DeliveryModality,
    DeliveryModalitySelectionRequest,
    ExchangeRequest,
    InitialReviewRequest,
    InspectionRequest,
    ProcessExchangeRequest,
    ProcessRequest,
    ReceiveItemRequest,
    ReturnListResponse,
    ReturnRequest,
    ReturnResponse,
    ReviewRequest,
    StripeConfirmRequest,
)
from app.services.auth_service import AuthService, InvalidAccessTokenError, InactiveAccountError, AuthenticationConfigurationError
from app.services.returns import ReturnsService
from app.services.payments import PaymentError

router = APIRouter(tags=["Devoluciones y cancelaciones CU24"])
ERRORS = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500, 503)}


def require_returns_staff(credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
                          db: Session = Depends(get_db)):
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error(401, "Token invalido o expirado")
    try:
        user = AuthService(db).get_current_user(credentials.credentials)
        if user.rol.upper() not in {"CAJERO", "ENCARGADO_SUCURSAL", "ENCARGADO", "ADMINISTRADOR"}:
            return _error(403, "Se requiere personal autorizado")
        return user
    except InvalidAccessTokenError:
        return _error(401, "Token invalido o expirado")
    except InactiveAccountError:
        return _error(403, "La cuenta se encuentra inactiva")
    except Exception:
        return _error(500, "No fue posible validar la autenticacion")

Staff = Annotated[AuthenticatedUserData | JSONResponse, Depends(require_returns_staff)]
Key = Annotated[UUID, Header(description="UUID de la solicitud; reutilizar ante reintento")]
Id = Annotated[int, Path(gt=0, le=2147483647)]


def run(user, operation, response=ReturnResponse):
    if isinstance(user, JSONResponse):
        return user
    try:
        return response(data=operation())
    except PaymentError as error:
        return _error(error.status_code, str(error))


@router.post("/api/client/purchases/{id_venta}/cancellation", response_model=ReturnResponse, status_code=201, responses=ERRORS)
def cancellation(id_venta: Id, payload: CancellationRequest, client: ClientDependency, idempotency_key: Key, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).request(client, id_venta, payload, idempotency_key, True))


@router.post("/api/client/purchases/{id_venta}/returns", response_model=ReturnResponse, status_code=201, responses=ERRORS)
def request_return(id_venta: Id, payload: ReturnRequest, client: ClientDependency, idempotency_key: Key, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).request(client, id_venta, payload, idempotency_key))


@router.post("/api/client/purchases/{id_venta}/exchanges", response_model=ReturnResponse, status_code=201, responses=ERRORS)
def request_exchange(id_venta: Id, payload: ExchangeRequest, client: ClientDependency, idempotency_key: Key, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).request(client, id_venta, payload, idempotency_key))


@router.get("/api/client/purchases/{id_venta}/exchange-options", response_model=ReturnResponse, responses=ERRORS)
def get_exchange_options(id_venta: Id, client: ClientDependency, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).exchange_options(client, id_venta))


@router.get("/api/client/returns", response_model=ReturnListResponse, responses=ERRORS)
def list_own_returns(
    client: ClientDependency,
    db: Session = Depends(get_db),
    tipo: Literal["DEVOLUCION", "CAMBIO", "CANCELACION"] | None = None,
    estado: Literal["SOLICITADA", "ACEPTADA_INICIALMENTE", "PENDIENTE_ENTREGA", "RECIBIDA", "APROBADA", "RECHAZADA", "PROCESADA"] | None = None,
    id_venta: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
    modalidad_entrega: DeliveryModality | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return run(
        client,
        lambda: ReturnsService(db).list_client_returns(client, tipo, estado, id_venta, modalidad_entrega, limit, offset),
        ReturnListResponse,
    )


@router.get("/api/client/returns/{id_devolucion}", response_model=ReturnResponse, responses=ERRORS)
def get_own(id_devolucion: Id, client: ClientDependency, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).get_return(client, id_devolucion))


@router.post("/api/client/returns/{id_devolucion}/delivery-modality", response_model=ReturnResponse, responses=ERRORS)
def select_delivery_modality(id_devolucion: Id, payload: DeliveryModalitySelectionRequest, client: ClientDependency, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).select_delivery_modality(client, id_devolucion, payload))


@router.get("/api/staff/returns", response_model=ReturnListResponse, responses=ERRORS)
def list_returns(staff: Staff, db: Session = Depends(get_db),
                 estado: Literal["SOLICITADA", "ACEPTADA_INICIALMENTE", "PENDIENTE_ENTREGA", "RECIBIDA", "APROBADA", "RECHAZADA", "PROCESADA"] | None = None,
                 tipo: Literal["DEVOLUCION", "CAMBIO", "CANCELACION"] | None = None,
                 modalidad_entrega: DeliveryModality | None = None,
                 id_sucursal: Annotated[int | None, Query(gt=0)] = None,
                 limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    return run(staff, lambda: ReturnsService(db).list_returns(staff, estado, limit, offset, tipo, modalidad_entrega, id_sucursal), ReturnListResponse)


@router.get("/api/staff/returns/{id_devolucion}", response_model=ReturnResponse, responses=ERRORS)
def get_staff(id_devolucion: Id, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).get_return(staff, id_devolucion, True))


@router.post("/api/staff/returns/{id_devolucion}/initial-review", response_model=ReturnResponse, responses=ERRORS)
def initial_review(id_devolucion: Id, payload: InitialReviewRequest, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).initial_review(staff, id_devolucion, payload))


@router.post("/api/staff/returns/{id_devolucion}/receive", response_model=ReturnResponse, responses=ERRORS)
def receive_item(id_devolucion: Id, staff: Staff, payload: ReceiveItemRequest | None = None, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).receive_item(staff, id_devolucion, payload))


@router.post("/api/staff/returns/{id_devolucion}/inspect", response_model=ReturnResponse, responses=ERRORS)
def inspect_item(id_devolucion: Id, payload: InspectionRequest, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).inspect_item(staff, id_devolucion, payload))


@router.post("/api/staff/returns/{id_devolucion}/review", response_model=ReturnResponse, responses=ERRORS)
def review(id_devolucion: Id, payload: ReviewRequest, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).review(staff, id_devolucion, payload))


@router.post("/api/staff/returns/{id_devolucion}/process", response_model=ReturnResponse, responses=ERRORS)
def process(id_devolucion: Id, payload: ProcessRequest, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).process(staff, id_devolucion, payload))


@router.post("/api/staff/returns/{id_devolucion}/process-exchange", response_model=ReturnResponse, responses=ERRORS)
def process_exchange(id_devolucion: Id, payload: ProcessExchangeRequest, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).process_exchange(staff, id_devolucion, payload))


@router.post("/api/staff/returns/{id_devolucion}/confirm-difference", response_model=ReturnResponse, responses=ERRORS)
def confirm_exchange_difference(id_devolucion: Id, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).confirm_exchange_difference(staff, id_devolucion))


@router.post("/api/client/returns/{id_devolucion}/stripe-checkout", response_model=CheckoutSessionResponse, responses=ERRORS)
def create_exchange_stripe_checkout(id_devolucion: Id, client: ClientDependency, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).create_exchange_stripe_checkout(client, id_devolucion))


@router.post("/api/client/returns/{id_devolucion}/stripe-confirm", response_model=ReturnResponse, responses=ERRORS)
def confirm_exchange_stripe_client(id_devolucion: Id, client: ClientDependency, payload: StripeConfirmRequest | None = None, db: Session = Depends(get_db)):
    return run(client, lambda: ReturnsService(db).confirm_exchange_stripe_payment(client, id_devolucion, payload, staff=False))


@router.post("/api/staff/returns/{id_devolucion}/confirm-payment", response_model=ReturnResponse, responses=ERRORS)
def confirm_exchange_store_payment(id_devolucion: Id, payload: ConfirmPaymentRequest, staff: Staff, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).confirm_exchange_store_payment(staff, id_devolucion, payload))


@router.post("/api/staff/returns/{id_devolucion}/stripe-confirm", response_model=ReturnResponse, responses=ERRORS)
def confirm_exchange_stripe_staff(id_devolucion: Id, staff: Staff, payload: StripeConfirmRequest | None = None, db: Session = Depends(get_db)):
    return run(staff, lambda: ReturnsService(db).confirm_exchange_stripe_payment(staff, id_devolucion, payload, staff=True))
