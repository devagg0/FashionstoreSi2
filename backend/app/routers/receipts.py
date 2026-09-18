"""CU25: comprobantes JSON, autenticacion y consultas de solo lectura."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.client_reservations import ClientDependency
from app.routers.staff_reservations import StaffDependency
from app.schemas.auth import ErrorResponse
from app.schemas.receipts import ReceiptResponse
from app.services.client_cart import CartAccessError, CartNotFoundError
from app.services.receipts import ReceiptConflictError, ReceiptsService

router = APIRouter(tags=['Comprobantes CU25'])
logger = logging.getLogger(__name__)
ERRORS = {code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 500)}
SaleId = Annotated[int, Path(gt=0, le=2147483647)]


def _run(user, operation):
    if isinstance(user, JSONResponse):
        return user
    try:
        return ReceiptResponse(data=operation())
    except (CartAccessError, CartNotFoundError, ReceiptConflictError) as error:
        status = 403 if isinstance(error, CartAccessError) else 404 if isinstance(error, CartNotFoundError) else 409
        return JSONResponse(status_code=status, content={'success': False, 'message': str(error)})
    except Exception:
        logger.exception('Error consultando comprobante CU25')
        return JSONResponse(status_code=500, content={'success': False, 'message': 'No fue posible consultar el comprobante'})


@router.get('/api/client/purchases/{id_venta}/receipt', response_model=ReceiptResponse, responses=ERRORS)
def client_receipt(id_venta: SaleId, client: ClientDependency, db: Session = Depends(get_db)):
    return _run(client, lambda: ReceiptsService(db).client_receipt(client.id_usuario, id_venta))


@router.get('/api/staff/sales/{id_venta}/receipt', response_model=ReceiptResponse, responses=ERRORS)
def staff_receipt(id_venta: SaleId, staff: StaffDependency, db: Session = Depends(get_db)):
    return _run(staff, lambda: ReceiptsService(db).staff_receipt(staff.id_usuario, id_venta))
