"""CU21: utiliza la autenticación y convenciones del carrito existente."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.client_cart import ERROR_RESPONSES
from app.routers.client_reservations import ClientDependency
from app.schemas.client_checkout import CheckoutRequest, DigitalSaleResponse
from app.services.client_cart import CartAccessError, CartConflictError, CartNotFoundError, CartValidationError
from app.services.client_checkout import ClientCheckoutService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/client", tags=["Compra digital"])


def _run(client, operation):
    if isinstance(client, JSONResponse):
        return client
    try:
        return DigitalSaleResponse(data=operation())
    except Exception as error:
        code = next((status for kind, status in (
            (CartAccessError, 403), (CartNotFoundError, 404),
            (CartConflictError, 409), (CartValidationError, 422),
        ) if isinstance(error, kind)), 500)
        if code == 500:
            logger.exception("Error interno de CU21")
        return JSONResponse(status_code=code, content={
            "success": False,
            "message": str(error) if code != 500 else "No fue posible procesar la compra digital.",
        })


@router.post("/cart/checkout", response_model=DigitalSaleResponse, responses=ERROR_RESPONSES)
def confirm_checkout(payload: CheckoutRequest, client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientCheckoutService(db).confirm(client.id_usuario, payload))


@router.get("/sales/{id_venta}", response_model=DigitalSaleResponse, responses=ERROR_RESPONSES)
def get_pending_sale(id_venta: Annotated[int, Path(gt=0, le=2147483647)],
                     client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientCheckoutService(db).get_pending_sale(client.id_usuario, id_venta))
