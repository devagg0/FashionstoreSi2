"""Contratos de CU17 para las reservas del cliente autenticado."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReservationState = Literal[
    "PENDIENTE", "CONFIRMADA", "ATENDIDA", "CANCELADA", "EXPIRADA"
]


class ReservationItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_variante_producto: int = Field(gt=0)
    cantidad: int = Field(gt=0, strict=True)


class ReservationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_sucursal: int = Field(gt=0)
    fecha_atencion_programada: datetime
    items: list[ReservationItemCreate] = Field(min_length=1, max_length=50)


class ReservationCityData(BaseModel):
    id_ciudad: int
    nombre: str


class ReservationBranchData(BaseModel):
    id_sucursal: int
    nombre: str
    direccion: str
    ciudad: ReservationCityData


class ReservationSizeData(BaseModel):
    id_talla: int
    nombre: str


class ReservationColorData(BaseModel):
    id_color: int
    nombre: str
    codigo_hex: str | None


class ReservationItemData(BaseModel):
    id_variante_producto: int
    sku: str
    id_producto: int
    producto: str
    imagen_principal: str | None
    talla: ReservationSizeData
    color: ReservationColorData
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal


class ReservationSummaryData(BaseModel):
    id_reserva: int
    codigo: str
    estado: ReservationState
    created_at: datetime
    fecha_atencion_programada: datetime
    fecha_expiracion: datetime
    sucursal: ReservationBranchData
    cantidad_prendas: int
    total: Decimal
    cancelable: bool


class ReservationDetailData(ReservationSummaryData):
    items: list[ReservationItemData]


class ReservationPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ReservationResponse(BaseModel):
    success: Literal[True] = True
    data: ReservationDetailData
    message: str = "Reserva consultada correctamente"


class ReservationListResponse(BaseModel):
    success: Literal[True] = True
    data: list[ReservationSummaryData]
    pagination: ReservationPaginationData
    message: str = "Reservas consultadas correctamente"
