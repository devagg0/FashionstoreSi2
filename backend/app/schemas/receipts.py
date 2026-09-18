"""Contrato publico del comprobante CU25, sin referencias de proveedores."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ReceiptBranch(BaseModel):
    nombre: str
    direccion: str


class ReceiptClient(BaseModel):
    nombre: str
    apellido: str


class ReceiptItem(BaseModel):
    nombre: str | None
    talla: str | None
    color: str | None
    cantidad: int
    precio_unitario: Decimal
    descuento_unitario: Decimal
    subtotal_linea: Decimal


class ReceiptPayment(BaseModel):
    medio: Literal['TARJETA', 'EFECTIVO', 'QR']
    estado: Literal['APROBADO', 'REEMBOLSADO']
    monto: Decimal


class Receipt(BaseModel):
    numero_venta: str
    fecha_completada: datetime
    canal: Literal['DIGITAL', 'PRESENCIAL']
    sucursal: ReceiptBranch
    cliente: ReceiptClient | None
    productos: list[ReceiptItem]
    subtotal: Decimal
    descuento_total: Decimal
    total: Decimal
    moneda: Literal['BOB']
    pago: ReceiptPayment


class ReceiptResponse(BaseModel):
    success: Literal[True] = True
    data: Receipt
