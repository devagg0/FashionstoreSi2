"""CU30: Endpoints REST para la consulta unificada de operaciones del cliente."""

import logging
from datetime import datetime
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.routers.client_reservations import ClientDependency
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.schemas.client_operations import (
    ClientOperationDetailResponse,
    ClientOperationsListResponse,
    ClientOperationsSummaryResponse,
)
from app.services.client_operations import (
    ClientOperationAccessError,
    ClientOperationNotFoundError,
    ClientOperationsService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/client/operations",
    tags=["Operaciones del cliente CU30"],
)

ERRORS = {
    401: {"model": ErrorResponse, "description": "Token inválido o expirado"},
    403: {"model": ErrorResponse, "description": "Acceso denegado o no es CLIENTE"},
    404: {"model": ErrorResponse, "description": "Operación no encontrada"},
    500: {"model": ErrorResponse, "description": "Error interno del servidor"},
}


def _resolve_tenant_company_id(client: AuthenticatedUserData, db: Session) -> int:
    """Obtiene el id de empresa del cliente autenticado desde su sesión JWT o contexto de BD."""
    company_id = (
        getattr(client, "id_empresa", None)
        or getattr(client, "empresa_id", None)
        or getattr(db, "info", {}).get("empresa_id")
    )
    if not company_id:
        cl = db.scalar(select(Client).where(Client.id_usuario == client.id_usuario))
        if cl is not None:
            company_id = cl.empresa_id
    if not company_id:
        raise ClientOperationAccessError(
            "El usuario autenticado no tiene una empresa asociada en su sesión"
        )
    return int(company_id)


@router.get("", response_model=ClientOperationsListResponse, responses=ERRORS)
def list_operations(
    client: ClientDependency,
    db: Session = Depends(get_db),
    tipo: Annotated[
        Optional[Literal["COMPRA", "RESERVA", "PAGO"]],
        Query(description="Filtrar por tipo de operación"),
    ] = None,
    estado: Annotated[
        Optional[str],
        Query(description="Filtrar por estado (ej. PENDIENTE, CONFIRMADA, RECHAZADA)"),
    ] = None,
    desde: Annotated[
        Optional[datetime],
        Query(description="Fecha inicio (ISO 8601)"),
    ] = None,
    hasta: Annotated[
        Optional[datetime],
        Query(description="Fecha fin (ISO 8601)"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Número de página")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Registros por página")] = 20,
):
    """Consulta cronológica unificada de compras, reservas y pagos del cliente autenticado."""
    if isinstance(client, JSONResponse):
        return client

    try:
        empresa_id = _resolve_tenant_company_id(client, db)
        service = ClientOperationsService(db)
        return service.list_operations(
            user_id=client.id_usuario,
            empresa_id=empresa_id,
            tipo=tipo,
            estado=estado,
            desde=desde,
            hasta=hasta,
            page=page,
            page_size=page_size,
        )
    except ClientOperationAccessError as exc:
        return JSONResponse(status_code=403, content={"success": False, "message": str(exc)})
    except Exception as exc:
        logger.exception("Error listando operaciones del cliente: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "No fue posible consultar las operaciones"},
        )


@router.get("/summary", response_model=ClientOperationsSummaryResponse, responses=ERRORS)
def get_operations_summary(
    client: ClientDependency,
    db: Session = Depends(get_db),
):
    """Resumen consolidado y contadores de compras, reservas y pagos del cliente."""
    if isinstance(client, JSONResponse):
        return client

    try:
        empresa_id = _resolve_tenant_company_id(client, db)
        service = ClientOperationsService(db)
        return service.get_summary(
            user_id=client.id_usuario,
            empresa_id=empresa_id,
        )
    except ClientOperationAccessError as exc:
        return JSONResponse(status_code=403, content={"success": False, "message": str(exc)})
    except Exception as exc:
        logger.exception("Error obteniendo resumen de operaciones: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "No fue posible obtener el resumen analítico"},
        )


@router.get("/{tipo}/{id_referencia}", response_model=ClientOperationDetailResponse, responses=ERRORS)
def get_operation_detail(
    tipo: Annotated[
        str,
        Path(description="Tipo de operación: COMPRA, RESERVA o PAGO"),
    ],
    id_referencia: Annotated[
        int,
        Path(gt=0, le=2147483647, description="ID o referencia de la operación"),
    ],
    client: ClientDependency,
    db: Session = Depends(get_db),
):
    """Detalle exhaustivo de una compra, reserva o pago específico del cliente."""
    if isinstance(client, JSONResponse):
        return client

    try:
        empresa_id = _resolve_tenant_company_id(client, db)
        service = ClientOperationsService(db)
        return service.get_operation_detail(
            user_id=client.id_usuario,
            empresa_id=empresa_id,
            tipo=tipo,
            id_referencia=id_referencia,
        )
    except ClientOperationAccessError as exc:
        return JSONResponse(status_code=403, content={"success": False, "message": str(exc)})
    except ClientOperationNotFoundError as exc:
        return JSONResponse(status_code=404, content={"success": False, "message": str(exc)})
    except Exception as exc:
        logger.exception("Error obteniendo detalle de operación: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "No fue posible consultar el detalle de la operación"},
        )
