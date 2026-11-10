"""Esquemas Pydantic para el CU30: Consultar estado de compras, reservas y pagos."""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class OperationPaymentSummary(BaseModel):
    """Resumen transaccional del pago asociado a una compra u operación."""

    model_config = ConfigDict(from_attributes=True)

    id_pago: int
    id_venta: Optional[int] = None
    medio: str = Field(..., description="TARJETA, QR o EFECTIVO")
    proveedor: str = Field(..., description="STRIPE o MANUAL")
    entorno: str = Field(..., description="TEST o LOCAL")
    estado: str = Field(..., description="PENDIENTE, APROBADO, RECHAZADO, CANCELADO, EXPIRADO, REEMBOLSADO")
    confirmado: bool = Field(..., description="True exclusivamente si el estado es APROBADO")
    monto: Decimal
    moneda: str = "BOB"
    referencia_externa: Optional[str] = None
    fecha_aprobacion: Optional[datetime] = None
    created_at: Optional[datetime] = None


class OperationItemDetail(BaseModel):
    """Detalle de producto o prenda dentro de una compra o reserva."""

    model_config = ConfigDict(from_attributes=True)

    id_producto: Optional[int] = None
    producto: str
    sku: Optional[str] = None
    talla: Optional[str] = None
    color: Optional[str] = None
    codigo_hex: Optional[str] = None
    cantidad: int
    precio_unitario: Decimal
    subtotal: Decimal
    imagen_principal: Optional[str] = None


class ClientOperationItem(BaseModel):
    """Elemento individual unificado de operación comercial para el cliente."""

    model_config = ConfigDict(from_attributes=True)

    id_operacion: str = Field(..., description="Identificador compuesto único ej. COMPRA:12, RESERVA:34, PAGO:56")
    tipo: Literal["COMPRA", "RESERVA", "PAGO"]
    id_referencia: int
    codigo: str
    codigo_referencia: Optional[str] = None
    fecha: datetime
    importe: Decimal
    moneda: str = "BOB"
    estado: str
    estado_etiqueta: str
    confirmada: bool
    origen: Literal["ONLINE", "OFFLINE_SYNC"]
    sucursal: Optional[str] = None
    id_sucursal: Optional[int] = None
    cantidad_prendas: int = 0
    pago: Optional[OperationPaymentSummary] = None
    detalles: Optional[List[OperationItemDetail]] = None
    motivo: Optional[str] = None
    uuid_offline: Optional[str] = None
    fecha_atencion_programada: Optional[datetime] = None
    fecha_expiracion: Optional[datetime] = None


class ClientOperationsListResponse(BaseModel):
    """Respuesta paginada del listado unificado de operaciones del cliente."""

    success: bool = True
    items: List[ClientOperationItem]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
    totales_por_tipo: Dict[str, int]
    totales_por_estado: Dict[str, int]


class ClientOperationDetailResponse(BaseModel):
    """Respuesta con el detalle exhaustivo de una operación específica."""

    success: bool = True
    data: ClientOperationItem


class ClientOperationsSummaryResponse(BaseModel):
    """Métricas y contadores globales de compras, reservas y pagos del cliente."""

    success: bool = True
    total_operaciones: int
    total_compras: int
    total_reservas: int
    total_pagos: int
    pendientes: int
    confirmadas: int
    rechazadas: int
    importe_total_compras: Decimal

