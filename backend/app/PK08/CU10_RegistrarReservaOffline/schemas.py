"""Contratos Pydantic para PK08 - CU10: Registrar reserva de prendas offline en FashionStore."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OfflineReservationDetailRequest(BaseModel):
    """Línea de prenda a reservar en la sucursal."""

    model_config = ConfigDict(from_attributes=True)

    id_variante_producto: int = Field(gt=0, description="ID de la variante comercializable")
    cantidad: int = Field(gt=0, description="Cantidad de prendas requeridas")
    precio_referencial: Decimal | None = Field(
        default=None, ge=0, description="Precio unitario capturado en modo offline"
    )


class OfflineReservationSyncRequest(BaseModel):
    """Solicitud de sincronización de reserva creada offline."""

    model_config = ConfigDict(from_attributes=True)

    uuid_reserva_offline: str = Field(
        ...,
        min_length=10,
        max_length=64,
        description="UUID idempotente generado por la PWA en IndexedDB",
    )
    id_sucursal: int = Field(gt=0, description="ID de la sucursal autorizada")
    id_cliente: int = Field(gt=0, description="ID del cliente que reserva")
    fecha_reserva_offline: datetime = Field(
        description="Fecha y hora de creación de la reserva en el dispositivo local",
    )
    fecha_atencion_programada: datetime = Field(
        description="Fecha y hora en que el cliente acudirá a la sucursal",
    )
    detalles: list[OfflineReservationDetailRequest] = Field(
        ..., min_length=1, description="Lista de prendas a reservar"
    )
    observaciones: str | None = Field(default=None, max_length=500)


class OfflineReservationSyncResponse(BaseModel):
    """Respuesta estructurada de sincronización idempotente de reserva offline."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    uuid_reserva_offline: str
    id_reserva: int | None = None
    codigo_reserva: str | None = None
    estado_sincronizacion: Literal["SINCRONIZADA", "RECHAZADA", "CONFLICTO"]
    motivo: str | None = None
    id_sucursal: int
    id_cliente: int
    id_usuario: int
    id_empresa: int
    fecha_sincronizacion: datetime
    mensaje: str

