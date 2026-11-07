"""Contratos Pydantic para PK08 - CU12: Consultar operaciones locales pendientes en FashionStore."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


OfflineOperationType = Literal["RESERVA", "COMPRA", "VENTA", "TRANSICION_RESERVA"]
OfflineSyncStatus = Literal[
    "PENDIENTE_SINCRONIZACION", "SINCRONIZADA", "RECHAZADA", "CONFLICTO"
]


class OfflineOperationItemSummary(BaseModel):
    """Información canónica y estructurada de una operación offline registrada o sincronizada."""

    model_config = ConfigDict(from_attributes=True)

    uuid_operacion: str = Field(
        ..., description="UUID local de la operación (reserva, venta, compra o transición)"
    )
    tipo_operacion: OfflineOperationType = Field(
        ..., description="Tipo de operación comercial offline"
    )
    id_sucursal: int = Field(gt=0, description="ID de la sucursal involucrada")
    sucursal_nombre: str | None = Field(default=None, description="Nombre legible de la sucursal")
    id_usuario: int = Field(gt=0, description="ID del usuario que originó la operación")
    rol_actor: str = Field(..., description="Rol del usuario ('CLIENTE', 'CAJERO', etc.)")
    id_cliente: int | None = Field(default=None, gt=0, description="ID del cliente si aplica")
    cliente_nombre: str | None = Field(
        default=None, description="Nombre descriptivo del cliente"
    )
    id_empleado: int | None = Field(default=None, gt=0, description="ID del empleado si aplica")
    fecha_operacion_offline: datetime | None = Field(
        default=None, description="Fecha y hora de registro en el dispositivo local"
    )
    fecha_sincronizacion: datetime | None = Field(
        default=None, description="Fecha y hora de persistencia en el servidor central"
    )
    estado_local: str | None = Field(
        default=None, description="Estado que mantenía en el dispositivo local"
    )
    estado_sincronizacion: OfflineSyncStatus = Field(
        ..., description="Estado de sincronización en el servidor central"
    )
    confirmada: bool = Field(
        default=False,
        description="True si la operación ya está persistida y aprobada en PostgreSQL",
    )
    id_servidor: int | None = Field(
        default=None, description="ID generado en base de datos central (id_reserva o id_venta)"
    )
    codigo_servidor: str | None = Field(
        default=None, description="Código oficial asignado por el servidor (codigo_reserva o numero_venta)"
    )
    estado_servidor: str | None = Field(
        default=None, description="Estado actual de la entidad en el servidor central"
    )
    monto_total: Decimal | None = Field(
        default=None, ge=0, description="Importe total de la operación"
    )
    moneda: str = Field(default="BOB", description="Moneda oficial de la operación")
    medio_pago: str | None = Field(
        default=None, description="Medio de pago ('EFECTIVO', 'QR', 'TARJETA')"
    )
    pago_simulado: bool | None = Field(
        default=None, description="Indica si el cobro fue simulado en el dispositivo"
    )
    motivo: str | None = Field(
        default=None, description="Motivo de rechazo o conflicto devuelto por el servidor"
    )
    detalles_resumen: list[dict[str, Any]] | None = Field(
        default=None, description="Líneas de prendas asociadas a la operación"
    )


class OfflineOperationStatusResponse(BaseModel):
    """Respuesta de consulta de estado de una operación offline específica."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    data: OfflineOperationItemSummary
    mensaje: str = "Estado de operación consultado correctamente"


class OfflineBatchStatusQueryRequest(BaseModel):
    """Consulta de estado en lote para una lista de UUIDs offline."""

    model_config = ConfigDict(from_attributes=True)

    uuids: list[str] = Field(
        ..., min_length=1, max_length=100, description="Lista de UUIDs locales a verificar"
    )


class OfflineBatchStatusQueryResponse(BaseModel):
    """Resultado de verificación en lote de estados de sincronización en servidor."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    operaciones: dict[str, OfflineOperationItemSummary] = Field(
        ..., description="Mapa de UUID -> Información del estado en el servidor"
    )
    total_consultados: int
    total_sincronizados: int
    mensaje: str = "Verificación de estados completada"


class OfflineOperationsListResponse(BaseModel):
    """Listado de operaciones offline sincronizadas en servidor para el actor/sucursal."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    data: list[OfflineOperationItemSummary]
    total: int
    empresa_id: int
    mensaje: str = "Operaciones consultadas correctamente"

