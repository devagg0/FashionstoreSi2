"""Contratos CU20. Los importes y responsables siempre salen del backend."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PositiveInt = Annotated[int, Field(strict=True, gt=0, le=2147483647)]


class SaleItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_variante_producto: PositiveInt
    cantidad: PositiveInt


class SaleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_sucursal: PositiveInt | None = None
    id_reserva: PositiveInt | None = None
    items: list[SaleItemRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_variants(self):
        ids = [item.id_variante_producto for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("La variante esta repetida en la venta")
        return self


class SaleBranchData(BaseModel):
    id_sucursal: int
    nombre: str
    ciudad: str
    direccion: str
    id_empleado_sucursal: int


class SalePersonData(BaseModel):
    id_usuario: int
    nombre: str
    apellido: str


class SaleCashierData(SalePersonData):
    id_empleado: int


class SaleClientData(SalePersonData):
    id_cliente: int


class SaleReservationData(BaseModel):
    id_reserva: int
    codigo: str
    estado: str


class SaleLineData(BaseModel):
    id_variante_producto: int
    sku: str
    producto: str
    talla: str
    color: str
    cantidad: int
    precio_unitario: Decimal
    descuento_unitario: Decimal
    id_promocion: int | None
    subtotal_linea: Decimal


class SaleReleaseData(BaseModel):
    id_variante_producto: int
    cantidad_reservada: int
    cantidad_compra: int
    cantidad_liberar: int


class SaleQuoteLineData(SaleLineData):
    cantidad_disponible: int


class SaleQuoteData(BaseModel):
    sucursal: SaleBranchData
    id_empleado: int
    id_cliente: int | None
    id_reserva: int | None
    detalles: list[SaleQuoteLineData]
    liberaciones: list[SaleReleaseData]
    subtotal: Decimal
    descuento_total: Decimal
    total: Decimal


class SaleMovementData(BaseModel):
    id_movimiento_inventario: int
    id_empleado_sucursal: int
    tipo_movimiento: Literal["VENTA"]
    estado: Literal["PENDIENTE", "CONFIRMADO", "ANULADO"]


class SaleData(BaseModel):
    id_venta: int
    numero_venta: str
    estado: Literal["PENDIENTE", "COMPLETADA", "ANULADA"]
    id_sucursal: int
    id_empleado: int
    id_cliente: int | None
    id_reserva: int | None
    sucursal: SaleBranchData
    cajero: SaleCashierData
    cliente: SaleClientData | None
    reserva: SaleReservationData | None
    fecha_venta: datetime
    detalles: list[SaleLineData]
    subtotal: Decimal
    descuento_total: Decimal
    total: Decimal
    movimiento: SaleMovementData


class SaleResponse(BaseModel):
    success: Literal[True] = True
    data: SaleData


class SaleQuoteResponse(BaseModel):
    success: Literal[True] = True
    data: SaleQuoteData


class SaleBranchesResponse(BaseModel):
    success: Literal[True] = True
    data: list[SaleBranchData]
