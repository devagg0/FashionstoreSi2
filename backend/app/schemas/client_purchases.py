"""CU23: proyecciones publicas; importes historicos y ninguna referencia Stripe."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PurchaseState = Literal["PENDIENTE", "COMPLETADA", "ANULADA"]
PurchaseChannel = Literal["DIGITAL", "PRESENCIAL"]


class PurchaseBranch(BaseModel):
    id_sucursal: int
    nombre: str


class PurchasePayment(BaseModel):
    id_pago: int
    medio: Literal["EFECTIVO", "QR", "TARJETA"]
    estado: Literal["PENDIENTE", "APROBADO", "RECHAZADO", "CANCELADO", "EXPIRADO", "REEMBOLSADO"]
    monto: Decimal
    moneda: str
    fecha_aprobacion: datetime | None


class PurchaseSummary(BaseModel):
    id_venta: int
    numero_venta: str
    fecha: datetime
    fecha_completada: datetime | None
    canal: PurchaseChannel
    estado: PurchaseState
    subtotal: Decimal
    descuento_total: Decimal
    total: Decimal
    moneda: str
    sucursal: PurchaseBranch
    pago: PurchasePayment | None


class PurchaseItem(BaseModel):
    id_detalle_venta: int
    id_variante_producto: int
    nombre: str | None
    talla: str | None
    color: str | None
    cantidad: int
    precio_unitario: Decimal
    descuento_unitario: Decimal
    subtotal_linea: Decimal


class PurchaseReturn(BaseModel):
    id_devolucion: int
    tipo: Literal["DEVOLUCION", "CANCELACION"]
    estado: Literal["SOLICITADA", "APROBADA", "RECHAZADA", "PROCESADA"]
    motivo: str
    fecha: datetime
    fecha_resolucion: datetime | None
    fecha_procesamiento: datetime | None


class PurchaseRefund(BaseModel):
    id_reembolso: int
    id_devolucion: int
    id_pago: int
    estado: Literal["PENDIENTE", "APROBADO", "RECHAZADO"]
    monto: Decimal
    fecha: datetime
    fecha_aprobacion: datetime | None


class PurchaseDetail(PurchaseSummary):
    productos: list[PurchaseItem] = Field(default_factory=list)
    pagos: list[PurchasePayment] = Field(default_factory=list)
    devoluciones: list[PurchaseReturn] = Field(default_factory=list)
    reembolsos: list[PurchaseRefund] = Field(default_factory=list)


class PurchaseListData(BaseModel):
    items: list[PurchaseSummary]
    total: int
    limit: int
    offset: int


class PurchaseListResponse(BaseModel):
    success: Literal[True] = True
    data: PurchaseListData


class PurchaseResponse(BaseModel):
    success: Literal[True] = True
    data: PurchaseDetail
