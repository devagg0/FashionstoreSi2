"""Contratos de CU18 para la atencion de reservas en sucursal."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.client_reservations import (
    ReservationBranchData,
    ReservationColorData,
    ReservationPaginationData,
    ReservationSizeData,
    ReservationState,
)


class StaffReservationClientData(BaseModel):
    id_cliente: int
    nombre: str
    apellido: str
    correo: str
    telefono: str | None


class StaffReservationItemData(BaseModel):
    id_variante_producto: int
    sku: str
    id_producto: int
    producto: str
    talla: ReservationSizeData
    color: ReservationColorData
    cantidad: int
    precio_reservado: Decimal
    subtotal: Decimal


class StaffReservationSummaryData(BaseModel):
    id_reserva: int
    codigo: str
    estado: ReservationState
    created_at: datetime
    fecha_atencion_programada: datetime
    fecha_expiracion: datetime
    fecha_atencion: datetime | None
    cliente: StaffReservationClientData
    sucursal: ReservationBranchData
    cantidad_prendas: int
    total: Decimal


class StaffReservationDetailData(StaffReservationSummaryData):
    prendas: list[StaffReservationItemData]


class StaffReservationResponse(BaseModel):
    success: Literal[True] = True
    data: StaffReservationDetailData
    message: str = "Reserva consultada correctamente"


class StaffReservationListResponse(BaseModel):
    success: Literal[True] = True
    data: list[StaffReservationSummaryData]
    pagination: ReservationPaginationData
    message: str = "Reservas consultadas correctamente"
