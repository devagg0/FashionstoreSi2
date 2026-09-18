"""CU23: reutiliza autenticacion CLIENTE existente; endpoints GET solamente."""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.client_reservations import ClientDependency
from app.schemas.auth import ErrorResponse
from app.schemas.client_purchases import PurchaseChannel, PurchaseListResponse, PurchaseResponse, PurchaseState
from app.services.client_cart import CartAccessError, CartNotFoundError
from app.services.client_purchases import ClientPurchasesService

router = APIRouter(prefix="/api/client/purchases", tags=["Compras del cliente CU23"])
ERRORS = {code: {"model": ErrorResponse} for code in (401, 403, 404, 500)}


def _run(client, operation, response):
    if isinstance(client, JSONResponse):
        return client
    try:
        return response(data=operation())
    except (CartAccessError, CartNotFoundError) as error:
        return JSONResponse(status_code=403 if isinstance(error, CartAccessError) else 404,
            content={"success": False, "message": str(error)})
    except Exception:
        return JSONResponse(status_code=500, content={"success": False, "message": "No fue posible consultar las compras"})


@router.get("", response_model=PurchaseListResponse, responses=ERRORS)
def list_purchases(client: ClientDependency, db: Session = Depends(get_db),
    estado: Annotated[PurchaseState | None, Query()] = None,
    canal: Annotated[PurchaseChannel | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0):
    return _run(client, lambda: ClientPurchasesService(db).list(client.id_usuario, estado, canal, limit, offset), PurchaseListResponse)


@router.get("/{id_venta}", response_model=PurchaseResponse, responses=ERRORS)
def get_purchase(id_venta: Annotated[int, Path(gt=0, le=2147483647)],
    client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ClientPurchasesService(db).detail(client.id_usuario, id_venta), PurchaseResponse)
