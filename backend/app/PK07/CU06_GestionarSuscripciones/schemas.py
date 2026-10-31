"""Esquemas Pydantic para PK07 / CU06: Gestionar suscripciones empresariales."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanFeatureSummary(BaseModel):
    """Resumen de funcionalidad de un plan SaaS."""

    codigo: str
    nombre: str
    habilitada: bool
    limite: int | None = None


class CommercialPlanData(BaseModel):
    """Detalle de un plan SaaS comercial disponible para contratación."""

    id_plan_saas: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    precio: Decimal
    moneda: str
    periodo_meses: int
    limite_sucursales: int | None = None
    tiene_ia: bool = False
    funcionalidades: list[PlanFeatureSummary] = Field(default_factory=list)


class CommercialPlansListResponse(BaseModel):
    """Respuesta al listar planes comerciales para suscripción."""

    success: Literal[True] = True
    total: int
    data: list[CommercialPlanData]


class ScheduledChangeData(BaseModel):
    """Información de un cambio de plan programado para ejecutarse al vencer el ciclo actual."""

    id_plan_saas: int
    codigo_plan: str
    nombre_plan: str
    fecha_programada: datetime
    monto_pagado: Decimal
    moneda: str
    estado: str = "PROGRAMADA"


class SubscriptionDetailData(BaseModel):
    """Detalle completo de una suscripción SaaS con plan y condiciones actuales."""

    id_suscripcion: int
    id_empresa: int
    empresa_codigo: str | None = None
    empresa_nombre: str | None = None
    id_plan_saas: int
    plan_codigo: str
    plan_nombre: str
    plan_precio: Decimal
    plan_moneda: str
    plan_periodo_meses: int
    limite_sucursales: int | None = None
    tiene_ia: bool = False
    estado: str
    fecha_inicio: datetime
    fecha_fin_periodo: datetime
    fecha_cancelacion: datetime | None = None
    dias_restantes: int
    renovacion_automatica: bool
    proveedor: str | None = None
    referencia_externa: str | None = None
    cambio_programado: ScheduledChangeData | None = None


class CurrentSubscriptionResponse(BaseModel):
    """Respuesta con la suscripción vigente de la empresa."""

    success: Literal[True] = True
    tiene_suscripcion_activa: bool
    data: SubscriptionDetailData | None = None


class SubscriptionHistoryItem(BaseModel):
    """Registro histórico de suscripción."""

    id_suscripcion: int
    id_plan_saas: int
    plan_codigo: str
    plan_nombre: str
    estado: str
    fecha_inicio: datetime
    fecha_fin_periodo: datetime
    fecha_cancelacion: datetime | None = None
    proveedor: str | None = None
    referencia_externa: str | None = None
    created_at: datetime


class SubscriptionHistoryResponse(BaseModel):
    """Historial completo de suscripciones de la empresa."""

    success: Literal[True] = True
    total: int
    data: list[SubscriptionHistoryItem]


class CreateCheckoutRequest(BaseModel):
    """Solicitud para iniciar sesión de pago Stripe Checkout (tarjeta o QR)."""

    model_config = ConfigDict(extra="forbid")

    id_plan_saas: int = Field(gt=0, description="Identificador único del plan SaaS a contratar o renovar")
    tipo_operacion: Literal["CONTRATACION", "RENOVACION", "CAMBIO_PLAN"] = Field(
        default="CONTRATACION",
        description="Tipo de operación SaaS a ejecutar",
    )
    empresa_id: int | None = Field(
        default=None,
        gt=0,
        description="Identificador de empresa (permitido únicamente para SUPERADMIN)",
    )
    success_url: str | None = Field(
        default=None,
        description="URL de retorno exitoso tras el checkout de Stripe",
    )
    cancel_url: str | None = Field(
        default=None,
        description="URL de cancelación tras el checkout de Stripe",
    )


class CheckoutSessionResponse(BaseModel):
    """Respuesta al crear una sesión de Stripe Checkout."""

    success: Literal[True] = True
    message: str = "Sesión de Checkout creada exitosamente"
    id_sesion: str
    url_checkout: str
    qr_data: str | None = None
    tipo_operacion: str
    metodo_pago: str
    monto: Decimal
    moneda: str
    id_plan_saas: int
    plan_codigo: str
    plan_nombre: str


class VerifyPaymentResponse(BaseModel):
    """Respuesta al verificar y sincronizar el pago de Stripe Checkout."""

    success: Literal[True] = True
    message: str
    id_suscripcion: int
    estado: str
    plan_codigo: str
    tipo_operacion: str
    fecha_inicio: datetime
    fecha_fin_periodo: datetime
    dias_restantes: int
    referencia_pago: str | None = None
    cambio_programado: ScheduledChangeData | None = None


class UpdateSubscriptionStatusRequest(BaseModel):
    """Solicitud administrativa (SUPERADMIN) para modificar el estado de una suscripción."""

    model_config = ConfigDict(extra="forbid")

    nuevo_estado: Literal["ACTIVA", "SUSPENDIDA", "CANCELADA", "EXPIRADA"]
    motivo: str | None = Field(default=None, max_length=255)


class SubscriptionAdminListResponse(BaseModel):
    """Respuesta administrativa para listar todas las suscripciones."""

    success: Literal[True] = True
    total: int
    data: list[SubscriptionDetailData]

