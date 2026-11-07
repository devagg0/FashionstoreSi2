"""Contratos Pydantic para PK08 - CU10: Registrar reserva de prendas offline en FashionStore."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OfflineReservationDetailRequest(BaseModel):
    """Línea de prenda seleccionada por el CLIENTE en el catálogo offline."""

    model_config = ConfigDict(from_attributes=True)

    id_variante_producto: int = Field(gt=0, description="ID de la variante comercializable")
    cantidad: int = Field(gt=0, description="Cantidad de prendas requeridas")
    id_producto: int | None = Field(
        default=None, gt=0, description="ID del producto (opcional para validación cruzada)"
    )
    id_talla: int | None = Field(
        default=None, gt=0, description="ID de la talla (opcional para validación cruzada)"
    )
    id_color: int | None = Field(
        default=None, gt=0, description="ID del color (opcional para validación cruzada)"
    )
    precio_referencial: Decimal | None = Field(
        default=None, ge=0, description="Precio unitario referencial capturado en modo offline"
    )


class OfflineReservationSyncRequest(BaseModel):
    """Solicitud de sincronización de reserva de prendas creada offline por el CLIENTE."""

    model_config = ConfigDict(from_attributes=True)

    uuid_reserva_offline: str = Field(
        ...,
        min_length=10,
        max_length=64,
        description="UUID idempotente generado localmente por la PWA en IndexedDB",
    )
    id_sucursal: int = Field(gt=0, description="ID de la sucursal de recogida")
    id_cliente: int | None = Field(
        default=None,
        gt=0,
        description="Opcional; el backend resuelve siempre el cliente desde la sesión autenticada",
    )
    id_empresa: int | None = Field(
        default=None,
        gt=0,
        description="Opcional; el backend resuelve siempre la empresa desde la sesión autenticada",
    )
    id_usuario: int | None = Field(
        default=None,
        gt=0,
        description="Opcional; el backend resuelve siempre el usuario desde la sesión autenticada",
    )
    fecha_reserva_offline: datetime | None = Field(
        default=None,
        description="Fecha y hora de creación de la reserva en el dispositivo local",
    )
    fecha_atencion_programada: datetime = Field(
        description="Fecha y hora elegida por el cliente para recoger las prendas en la sucursal",
    )
    detalles: list[OfflineReservationDetailRequest] = Field(
        ..., min_length=1, max_length=50, description="Lista de prendas a reservar"
    )
    observaciones: str | None = Field(default=None, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def _normalize_items_alias(cls, data: Any) -> Any:
        """Permite recibir 'items' (contrato CU17) o 'detalles' (contrato cola offline CU10)."""
        if isinstance(data, dict) and "detalles" not in data and "items" in data:
            copied = dict(data)
            copied["detalles"] = copied.pop("items")
            return copied
        return data


class OfflineReservationSyncResponse(BaseModel):
    """Respuesta estructurada de sincronización idempotente de reserva offline del CLIENTE."""

    model_config = ConfigDict(from_attributes=True)

    success: bool
    confirmada: bool = Field(
        description="True únicamente cuando la reserva quedó persistida y confirmada en el servidor central"
    )
    uuid_reserva_offline: str
    id_reserva: int | None = None
    codigo_reserva: str | None = None
    estado_sincronizacion: Literal["SINCRONIZADA", "RECHAZADA", "CONFLICTO"]
    estado_resultado: Literal["CONFIRMADA", "RECHAZADA", "EN_CONFLICTO"]
    estado_reserva: Literal[
        "PENDIENTE", "CONFIRMADA", "ATENDIDA", "CANCELADA", "EXPIRADA"
    ] | None = None
    motivo: str | None = None
    id_sucursal: int
    id_cliente: int
    id_usuario: int
    id_empresa: int
    fecha_sincronizacion: datetime
    mensaje: str
