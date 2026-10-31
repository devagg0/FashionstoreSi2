"""Contratos Pydantic de entrada y salida para PK07 / CU05: Gestionar planes SaaS."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanFeatureItemRequest(BaseModel):
    """Configuración individual de funcionalidad para un plan."""

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "codigo": "SUCURSALES",
                "habilitada": True,
                "limite": 2,
            }
        },
    )

    id_funcionalidad_saas: int | None = Field(default=None, gt=0)
    codigo: str | None = Field(default=None, max_length=80)
    habilitada: bool = Field(default=True)
    limite: int | None = Field(default=None, ge=0)

    @field_validator("codigo", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class PlanFeatureDetailData(BaseModel):
    """Detalle de una funcionalidad asignada a un plan."""

    id_funcionalidad_saas: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    habilitada: bool
    limite: int | None = None


class SaasPlanDetailData(BaseModel):
    """Representación pública detallada de un plan SaaS."""

    id_plan_saas: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    precio: Decimal
    moneda: str
    periodo_meses: int
    estado: bool
    suscripciones_activas: int = 0
    funcionalidades: list[PlanFeatureDetailData] = []
    created_at: datetime
    updated_at: datetime


class CreateSaasPlanRequest(BaseModel):
    """Datos requeridos para dar de alta un nuevo plan SaaS."""

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "codigo": "EMPRENDEDOR",
                "nombre": "Plan Emprendedor",
                "descripcion": "Plan inicial para negocios de una sola sede",
                "precio": 99.00,
                "moneda": "BOB",
                "periodo_meses": 1,
                "estado": True,
                "funcionalidades": [
                    {"codigo": "SUCURSALES", "habilitada": True, "limite": 1},
                    {"codigo": "PRODUCTOS", "habilitada": True, "limite": None},
                ],
            }
        },
    )

    codigo: str = Field(min_length=1, max_length=50, description="Código identificador único del plan")
    nombre: str = Field(min_length=1, max_length=100, description="Nombre comercial del plan")
    descripcion: str | None = Field(default=None, max_length=300)
    precio: Decimal = Field(ge=0, description="Precio periódico del plan")
    moneda: str = Field(default="BOB", min_length=3, max_length=3)
    periodo_meses: int = Field(default=1, gt=0, description="Duración del periodo facturable en meses")
    estado: bool = Field(default=True)
    funcionalidades: list[PlanFeatureItemRequest] = []

    @field_validator("codigo", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        if isinstance(value, str):
            val = value.strip().upper()
            if not val:
                raise ValueError("El código del plan no puede estar vacío")
            return val
        return value

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("moneda", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class UpdateSaasPlanRequest(BaseModel):
    """Campos editables de un plan SaaS."""

    model_config = ConfigDict(extra="ignore")

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=300)
    precio: Decimal | None = Field(default=None, ge=0)
    periodo_meses: int | None = Field(default=None, gt=0)

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class UpdateSaasPlanStatusRequest(BaseModel):
    """Activación o desactivación de un plan SaaS."""

    model_config = ConfigDict(extra="ignore")

    estado: bool


class ConfigurePlanFeaturesRequest(BaseModel):
    """Asignación y parametrización de funcionalidades y límites para un plan."""

    model_config = ConfigDict(extra="ignore")

    funcionalidades: list[PlanFeatureItemRequest]


class SaasFeatureData(BaseModel):
    """Representación pública de una funcionalidad del catálogo SaaS."""

    id_funcionalidad_saas: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    estado: bool
    created_at: datetime
    updated_at: datetime


class SaasPlanListResponse(BaseModel):
    """Listado paginado/filtrado de planes SaaS."""

    success: Literal[True] = True
    data: list[SaasPlanDetailData]
    total: int


class SaasPlanDetailResponse(BaseModel):
    """Respuesta con el detalle de un plan individual."""

    success: Literal[True] = True
    message: str = "Plan SaaS procesado correctamente"
    data: SaasPlanDetailData


class SaasFeaturesListResponse(BaseModel):
    """Catálogo de funcionalidades SaaS disponibles."""

    success: Literal[True] = True
    data: list[SaasFeatureData]
    total: int


class MessageResponse(BaseModel):
    """Mensaje estándar de confirmación."""

    success: Literal[True] = True
    message: str

