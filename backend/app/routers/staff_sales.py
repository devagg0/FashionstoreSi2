"""API CU20 exclusiva para CAJERO. No expone operaciones de pago."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.auth import bearer_scheme
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.schemas.staff_sales import SaleBranchesResponse, SaleQuoteResponse, SaleRequest, SaleResponse
from app.services.auth_service import (
    AuthenticationConfigurationError, AuthService, InactiveAccountError, InvalidAccessTokenError,
)
from app.services.staff_sales import SaleError, StaffSalesService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/staff/sales", tags=["Ventas presenciales"])


def _error(status_code, message):
    return JSONResponse(status_code=status_code, content={"success": False, "message": message},
                        headers={"WWW-Authenticate": "Bearer"} if status_code == 401 else None)


def require_cashier(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error(401, "Token invalido o expirado")
    try:
        user = AuthService(db).get_current_user(credentials.credentials)
        if user.rol.upper() != "CAJERO":
            return _error(403, "Se requiere rol CAJERO")
        return user
    except InvalidAccessTokenError:
        return _error(401, "Token invalido o expirado")
    except InactiveAccountError:
        return _error(403, "La cuenta se encuentra inactiva")
    except AuthenticationConfigurationError:
        return _error(500, "Error de configuracion del sistema")
    except Exception:
        logger.exception("Error autenticando cajero de CU20")
        return _error(500, "No fue posible validar la autenticacion")


Cashier = Annotated[AuthenticatedUserData | JSONResponse, Depends(require_cashier)]
ERRORS = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 500)}


def _execute(cashier, operation, response):
    if isinstance(cashier, JSONResponse):
        return cashier
    try:
        return response(data=operation())
    except SaleError as error:
        if error.status_code == 500:
            logger.exception("Error interno de CU20")
        return _error(error.status_code, str(error))
    except Exception:
        logger.exception("Error inesperado de CU20")
        return _error(500, "No fue posible procesar la venta")


@router.get("/branches", response_model=SaleBranchesResponse, responses=ERRORS)
def branches(cashier: Cashier, db: Session = Depends(get_db)):
    return _execute(cashier, lambda: StaffSalesService(db).list_branches(cashier.id_usuario), SaleBranchesResponse)


@router.post("/quote", response_model=SaleQuoteResponse, responses=ERRORS)
def quote(payload: SaleRequest, cashier: Cashier, db: Session = Depends(get_db)):
    return _execute(cashier, lambda: StaffSalesService(db).quote(cashier.id_usuario, payload), SaleQuoteResponse)


@router.post("", response_model=SaleResponse, status_code=201, responses=ERRORS)
def create(
    payload: SaleRequest, cashier: Cashier,
    idempotency_key: Annotated[UUID, Header(description="UUID por intento de venta; reutilizar ante doble clic o reintento")],
    db: Session = Depends(get_db),
):
    return _execute(cashier, lambda: StaffSalesService(db).create(cashier.id_usuario, payload, idempotency_key), SaleResponse)


@router.get("/{id_venta}", response_model=SaleResponse, responses=ERRORS)
def get_sale(id_venta: Annotated[int, Path(gt=0)], cashier: Cashier, db: Session = Depends(get_db)):
    return _execute(cashier, lambda: StaffSalesService(db).get_sale(cashier.id_usuario, id_venta), SaleResponse)
