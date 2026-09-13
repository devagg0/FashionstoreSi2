"""CU19: API exclusiva para el carrito del cliente autenticado."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.client_reservations import ClientDependency
from app.schemas.auth import ErrorResponse
from app.schemas.client_cart import CartItemCreate, CartQuantityUpdate, CartResponse
from app.services.client_cart import (
    CartAccessError, CartConflictError, CartNotFoundError,
    CartValidationError, ClientCartService,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/client/cart", tags=["Carrito del cliente"])
ERROR_RESPONSES = {
    code: {"model": ErrorResponse, "description": description}
    for code, description in (
        (401, "Token inválido o expirado"), (403, "Se requiere cliente válido"),
        (404, "Variante o artículo inexistente"), (409, "Stock o concurrencia"),
        (500, "Error interno"),
    )
}
ERROR_RESPONSES[422] = {"description": "Request inválido o artículo inactivo"}
VariantId = Annotated[int, Path(gt=0, le=2147483647)]


def _run(client, operation, message="Carrito consultado correctamente"):
    if isinstance(client, JSONResponse):
        return client
    try:
        return CartResponse(data=operation(), message=message)
    except Exception as error:
        code = 500
        for error_type, status in (
            (CartAccessError, 403), (CartNotFoundError, 404),
            (CartConflictError, 409), (CartValidationError, 422),
        ):
            if isinstance(error, error_type):
                code = status
                break
        if code == 500:
            logger.exception("Error interno de CU19")
        return JSONResponse(status_code=code, content={
            "success": False,
            "message": str(error) if code != 500 else "No fue posible procesar el carrito.",
        })


@router.get("", response_model=CartResponse, responses=ERROR_RESPONSES)
def get_cart(client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientCartService(db).get_cart(client.id_usuario))


@router.post("/items", response_model=CartResponse, responses=ERROR_RESPONSES)
def add_item(payload: CartItemCreate, client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientCartService(db).add_item(client.id_usuario, payload), "Artículo agregado correctamente")


@router.patch("/items/{id_variante_producto}", response_model=CartResponse, responses=ERROR_RESPONSES)
def update_item(id_variante_producto: VariantId, payload: CartQuantityUpdate, client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientCartService(db).update_item(client.id_usuario, id_variante_producto, payload), "Cantidad actualizada correctamente")


@router.delete("/items/{id_variante_producto}", response_model=CartResponse, responses=ERROR_RESPONSES)
def delete_item(id_variante_producto: VariantId, client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientCartService(db).delete_item(client.id_usuario, id_variante_producto), "Artículo eliminado correctamente")


@router.delete("/items", response_model=CartResponse, responses=ERROR_RESPONSES)
def clear_cart(client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientCartService(db).clear_cart(client.id_usuario), "Carrito vaciado correctamente")
