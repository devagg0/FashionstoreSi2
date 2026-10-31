"""Esquemas Pydantic para PK07 / CU07: Consultar plan, límites y funcionalidades habilitadas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FeatureItemData(BaseModel):
    """Información de funcionalidad individual y su límite parametrizado en el plan."""

    codigo: str
    nombre: str
    descripcion: str | None = None
    habilitada: bool = True
    limite: int | None = None


class BranchConsumptionSummary(BaseModel):
    """Métricas de consumo y disponibilidad de sucursales según el plan contratado."""

    limite_sucursales: int | None = Field(
        default=None,
        description="Límite máximo de sucursales activas según el plan (None si es ilimitado o sin plan)",
    )
    sucursales_activas: int = Field(default=0, description="Cantidad de sucursales activas actualmente")
    sucursales_inactivas: int = Field(default=0, description="Cantidad de sucursales inactivas")
    sucursales_totales: int = Field(default=0, description="Total histórico de sucursales registradas")
    disponibles_para_crear: int | None = Field(
        default=None,
        description="Cupos disponibles para crear o activar nuevas sucursales",
    )
    limite_alcanzado: bool = Field(
        default=False,
        description="Indica si se alcanzó o superó el cupo máximo de sucursales activas",
    )
    puede_crear_sucursal: bool = Field(
        default=False,
        description="Indica si el tenant cuenta con autorización y cupo disponible para crear o reactivar sucursales",
    )


class PlanSummaryData(BaseModel):
    """Resumen comercial del plan SaaS asociado a la suscripción activa."""

    id_plan_saas: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    precio: Decimal
    moneda: str
    periodo_meses: int


class SubscriptionSummaryData(BaseModel):
    """Resumen del estado y vigencia de la suscripción SaaS."""

    id_suscripcion: int
    estado: str
    fecha_inicio: datetime
    fecha_fin_periodo: datetime
    dias_restantes: int
    renovacion_automatica: bool = False
    proveedor: str | None = None


class CompanyPlanLimitsResponse(BaseModel):
    """Detalle consolidado del plan vigente, límites y funcionalidades para una empresa."""

    success: Literal[True] = True
    id_empresa: int
    empresa_codigo: str
    empresa_nombre: str
    tiene_suscripcion_activa: bool
    suscripcion: SubscriptionSummaryData | None = None
    plan: PlanSummaryData | None = None
    consumo_sucursales: BranchConsumptionSummary
    funcionalidades: list[FeatureItemData] = Field(default_factory=list)
    permisos: dict[str, bool] = Field(
        default_factory=dict,
        description="Diccionario de permisos clave-valor para verificación rápida por código de funcionalidad",
    )
    tiene_ia: bool = Field(default=False, description="Acceso a análisis e insights generativos con IA")
    puede_crear_sucursal: bool = Field(
        default=False,
        description="Acceso a creación/activación de sucursales según plan y cupo disponible",
    )


class CompanyBranchDetailItem(BaseModel):
    """Detalle de sucursal para consulta de consumo."""

    id_sucursal: int
    nombre: str
    direccion: str
    telefono: str | None = None
    estado: bool
    id_ciudad: int
    ciudad_nombre: str | None = None


class CompanyBranchConsumptionResponse(BaseModel):
    """Respuesta detallada del consumo y listado de sucursales para auditoría de límites."""

    success: Literal[True] = True
    id_empresa: int
    empresa_codigo: str
    empresa_nombre: str
    consumo: BranchConsumptionSummary
    sucursales: list[CompanyBranchDetailItem] = Field(default_factory=list)

