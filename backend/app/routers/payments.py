"""CU22: CLIENTE propietario digital o CAJERO de sucursal presencial."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.auth import bearer_scheme
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.schemas.payments import CheckoutSessionResponse, EmptyPaymentRequest, ManualConfirmationRequest, PaymentResponse, PaymentStartRequest
from app.services.auth_service import AuthService, InactiveAccountError, InvalidAccessTokenError
from app.services.payments import PaymentError, PaymentsService


router = APIRouter(prefix="/api", tags=["Pagos CU22 TEST"])


def error_response(code, message):
    return JSONResponse(status_code=code, content={"success": False, "message": message},
                        headers={"WWW-Authenticate": "Bearer"} if code == 401 else None)


def require_payment_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return error_response(401, "Token invalido o expirado")
    try:
        user = AuthService(db).get_current_user(credentials.credentials)
        if user.rol.upper() not in {"CAJERO", "CLIENTE"}:
            return error_response(403, "Se requiere rol CAJERO o CLIENTE")
        return user
    except InvalidAccessTokenError:
        return error_response(401, "Token invalido o expirado")
    except InactiveAccountError:
        return error_response(403, "La cuenta se encuentra inactiva")
    except Exception:
        return error_response(500, "No fue posible validar la autenticacion")


PaymentUser = Annotated[AuthenticatedUserData | JSONResponse, Depends(require_payment_user)]
Identifier = Annotated[int, Path(gt=0, le=2147483647)]
ERRORS = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500, 503)}


def execute(user, operation, response=PaymentResponse):
    if isinstance(user, JSONResponse):
        return user
    try:
        return response(data=operation())
    except PaymentError as error:
        return error_response(error.status_code, str(error))
    except Exception:
        # No registrar trazas de proveedor, datos bancarios ni secretos.
        return error_response(500, "No fue posible procesar el pago")


@router.post("/sales/{id_venta}/payments", response_model=PaymentResponse, responses=ERRORS)
def start_payment(id_venta: Identifier, payload: PaymentStartRequest, user: PaymentUser,
                  idempotency_key: Annotated[UUID, Header(description="UUID estable por intento; reutilizar en reintentos")],
                  db: Session = Depends(get_db)):
    return execute(user, lambda: PaymentsService(db).start(user, id_venta, payload, idempotency_key))


@router.get("/payments/{id_pago}", response_model=PaymentResponse, responses=ERRORS)
def get_payment(id_pago: Identifier, user: PaymentUser, db: Session = Depends(get_db)):
    return execute(user, lambda: PaymentsService(db).get(user, id_pago))


@router.post("/payments/{id_pago}/manual/confirm", response_model=PaymentResponse, responses=ERRORS)
def confirm_manual(id_pago: Identifier, payload: ManualConfirmationRequest, user: PaymentUser,
                   db: Session = Depends(get_db)):
    return execute(user, lambda: PaymentsService(db).confirm_manual(user, id_pago, payload))


@router.post("/payments/{id_pago}/qr/confirm", response_model=PaymentResponse, responses=ERRORS)
def confirm_qr(id_pago: Identifier, user: PaymentUser, payload: EmptyPaymentRequest | None = None,
               db: Session = Depends(get_db)):
    return execute(user, lambda: PaymentsService(db).confirm_qr(user, id_pago))


@router.post("/payments/{id_pago}/stripe/checkout-session", response_model=CheckoutSessionResponse, responses=ERRORS)
def checkout_session(id_pago: Identifier, user: PaymentUser, payload: EmptyPaymentRequest | None = None,
                     db: Session = Depends(get_db)):
    return execute(
        user,
        lambda: PaymentsService(db).checkout_session(
            user, id_pago, return_target=payload.return_target if payload else "web",
        ),
        CheckoutSessionResponse,
    )


@router.post("/payments/{id_pago}/stripe/sync", response_model=PaymentResponse, responses=ERRORS)
def sync_stripe(id_pago: Identifier, user: PaymentUser, payload: EmptyPaymentRequest | None = None, db: Session = Depends(get_db)):
    return execute(user, lambda: PaymentsService(db).stripe_sync(user, id_pago))
