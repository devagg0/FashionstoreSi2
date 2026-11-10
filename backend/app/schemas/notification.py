"""Esquemas Pydantic para el CU29: Notificaciones de reservas y compras."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    """Contrato individual de notificación, compatible con Flutter y Angular."""

    model_config = ConfigDict(from_attributes=True)

    id_notificacion: int
    usuario_id: int = Field(..., description="ID del usuario cliente destinatario")
    empresa_id: int
    tipo: str = Field(..., description="Tipo de evento: RESERVA_CREADA, COMPRA_CONFIRMADA, etc.")
    titulo: str
    mensaje: str
    referencia_origen: Optional[str] = None
    referencia_id: Optional[int] = None
    codigo_referencia: Optional[str] = None
    leido: bool = False
    fecha_lectura: Optional[datetime] = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Listado paginado de notificaciones del cliente autenticado."""

    items: List[NotificationResponse]
    total: int
    no_leidas: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class UnreadCountResponse(BaseModel):
    """Contador de notificaciones pendientes/no leídas para insignia o badges."""

    no_leidas: int


class MarkReadResponse(BaseModel):
    """Resultado de marcar notificaciones como leídas."""

    success: bool = True
    marcadas: int
    mensaje: str = "Notificación(es) actualizada(s) correctamente."

