"""Router para el CU29: Notificaciones de reservas y compras para clientes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.routers.client_reservations import ClientDependency, ERROR_RESPONSES
from app.schemas.auth import ErrorResponse
from app.schemas.notification import (
    MarkReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/client/notifications",
    tags=["Notificaciones del Cliente CU29"],
)


def _get_tenant_company_id(client: ClientDependency, db: Session) -> int:
    """Obtiene el identificador de la empresa para el cliente autenticado."""
    company_id = getattr(client, "id_empresa", None) or getattr(db, "info", {}).get("empresa_id")
    if not company_id:
        cl = db.query(Client).filter(Client.id_usuario == client.id_usuario).first()
        if cl:
            company_id = cl.empresa_id
    return int(company_id or 1)


@router.get(
    "",
    response_model=NotificationListResponse,
    responses=ERROR_RESPONSES,
)
def list_client_notifications(
    client: ClientDependency,
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    unread_only: Annotated[bool, Query()] = False,
) -> NotificationListResponse | JSONResponse:
    """Devuelve el listado paginado de notificaciones del cliente autenticado."""
    if isinstance(client, JSONResponse):
        return client

    empresa_id = _get_tenant_company_id(client, db)
    return NotificationService.list_notifications(
        db,
        empresa_id=empresa_id,
        usuario_id=client.id_usuario,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    responses=ERROR_RESPONSES,
)
def get_unread_count(
    client: ClientDependency,
    db: Session = Depends(get_db),
) -> UnreadCountResponse | JSONResponse:
    """Devuelve el contador de notificaciones no leídas para el cliente."""
    if isinstance(client, JSONResponse):
        return client

    empresa_id = _get_tenant_company_id(client, db)
    return NotificationService.get_unread_count(
        db,
        empresa_id=empresa_id,
        usuario_id=client.id_usuario,
    )


@router.patch(
    "/{id_notificacion}/read",
    response_model=NotificationResponse,
    responses=ERROR_RESPONSES,
)
def mark_notification_as_read(
    id_notificacion: Annotated[int, Path(gt=0)],
    client: ClientDependency,
    db: Session = Depends(get_db),
) -> NotificationResponse | JSONResponse:
    """Marca una notificación específica como leída."""
    if isinstance(client, JSONResponse):
        return client

    empresa_id = _get_tenant_company_id(client, db)
    return NotificationService.mark_as_read(
        db,
        empresa_id=empresa_id,
        usuario_id=client.id_usuario,
        notification_id=id_notificacion,
    )


@router.post(
    "/mark-all-read",
    response_model=MarkReadResponse,
    responses=ERROR_RESPONSES,
)
def mark_all_notifications_as_read(
    client: ClientDependency,
    db: Session = Depends(get_db),
) -> MarkReadResponse | JSONResponse:
    """Marca todas las notificaciones pendientes del cliente como leídas."""
    if isinstance(client, JSONResponse):
        return client

    empresa_id = _get_tenant_company_id(client, db)
    return NotificationService.mark_all_as_read(
        db,
        empresa_id=empresa_id,
        usuario_id=client.id_usuario,
    )

