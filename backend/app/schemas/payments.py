from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PaymentStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    medio: Literal["EFECTIVO", "QR", "TARJETA"]


class ManualConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resultado: Literal["APROBADO", "RECHAZADO"]


class EmptyPaymentRequest(BaseModel):
    """El cliente no selecciona resultado, monto, referencias ni URLs."""
    model_config = ConfigDict(extra="forbid")


class PaymentData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_pago: int
    id_venta: int
    medio: str
    proveedor: str
    entorno: str
    estado: str
    monto: Decimal
    moneda: str
    referencia_externa: str | None
    clave_idempotencia: UUID
    fecha_aprobacion: datetime | None
    created_at: datetime
    updated_at: datetime
    estado_venta: str


class PaymentResponse(BaseModel):
    success: Literal[True] = True
    data: PaymentData


class CheckoutSessionData(BaseModel):
    payment: PaymentData
    session_id: str
    url: str


class CheckoutSessionResponse(BaseModel):
    success: Literal[True] = True
    data: CheckoutSessionData
