"""Contratos administrativos de CU15, sin cambios al esquema persistido."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MovementType = Literal["ENTRADA", "SALIDA", "TRANSFERENCIA", "AJUSTE_POSITIVO", "AJUSTE_NEGATIVO"]
MovementState = Literal["PENDIENTE", "CONFIRMADO", "ANULADO"]


class MovementDetailCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_variante_producto: int = Field(gt=0)
    cantidad: int = Field(gt=0, strict=True)
    costo_unitario: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class MovementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_movimiento: MovementType
    id_sucursal_origen: int | None = Field(default=None, gt=0)
    id_sucursal_destino: int | None = Field(default=None, gt=0)
    id_empleado_sucursal: int = Field(gt=0)
    motivo: str | None = Field(default=None, max_length=200)
    detalles: list[MovementDetailCreate] = Field(min_length=1)


class MovementData(BaseModel):
    id_movimiento_inventario: int
    tipo_movimiento: MovementType
    estado: MovementState
    fecha_movimiento: datetime
    motivo: str | None
    id_sucursal_origen: int | None
    sucursal_origen: str | None
    id_sucursal_destino: int | None
    sucursal_destino: str | None
    id_empleado_sucursal: int
    id_empleado: int
    nombre_empleado: str
    rol: str
    created_at: datetime
    updated_at: datetime


class MovementDetailData(BaseModel):
    id_variante_producto: int
    sku: str
    producto: str
    talla: str
    color: str
    cantidad: int
    costo_unitario: Decimal | None


class MovementFullData(MovementData):
    detalles: list[MovementDetailData]


class MovementPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class MovementResponse(BaseModel):
    success: Literal[True] = True
    data: MovementFullData


class MovementListResponse(BaseModel):
    success: Literal[True] = True
    data: list[MovementData]
    pagination: MovementPaginationData
