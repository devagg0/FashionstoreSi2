"""CU21: solo identificadores; nunca precios proporcionados por el cliente."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_carrito: int = Field(gt=0, le=2147483647, strict=True)
    id_sucursal: int = Field(gt=0, le=2147483647, strict=True)


class DigitalSaleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_variante_producto: int
    id_promocion: int | None
    cantidad: int
    precio_unitario: Decimal
    descuento_unitario: Decimal
    subtotal_linea: Decimal


class DigitalSaleData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_venta: int
    numero_venta: str
    id_cliente: int
    id_carrito: int
    id_sucursal: int
    canal: Literal["DIGITAL"]
    moneda: Literal["BOB"]
    estado: Literal["PENDIENTE"]
    stock_comprometido: bool
    fecha_expiracion_pago: datetime
    subtotal: Decimal
    descuento_total: Decimal
    total: Decimal
    items: list[DigitalSaleItem] = Field(default_factory=list)


class DigitalSaleResponse(BaseModel):
    success: Literal[True] = True
    data: DigitalSaleData
    message: str = "Venta digital pendiente consultada correctamente"
