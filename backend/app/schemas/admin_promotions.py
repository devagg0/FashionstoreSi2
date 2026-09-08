"""Contratos de CU11 para la gestion administrativa de promociones."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DiscountType = Literal["PORCENTAJE", "MONTO_FIJO"]
Validity = Literal["PROGRAMADA", "VIGENTE", "EXPIRADA"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _PromotionTextFields(_StrictModel):
    @field_validator("nombre", "descripcion", mode="before", check_fields=False)
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("codigo", mode="before", check_fields=False)
    @classmethod
    def normalize_code(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().upper()
            return value or None
        return value

    @field_validator("fecha_inicio", "fecha_fin", mode="after", check_fields=False)
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        """Normaliza offsets a UTC para las columnas DateTime sin zona horaria."""
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


def _validate_discount(discount_type: DiscountType, value: Decimal) -> None:
    if discount_type == "PORCENTAJE" and value > Decimal("100"):
        raise ValueError("El porcentaje no puede ser mayor a 100")


class PromotionCreateRequest(_PromotionTextFields):
    nombre: str = Field(min_length=1, max_length=150)
    codigo: str | None = Field(default=None, min_length=1, max_length=50)
    descripcion: str | None = Field(default=None, max_length=200)
    tipo_descuento: DiscountType
    valor: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    fecha_inicio: datetime
    fecha_fin: datetime
    acumulable: bool = False

    @model_validator(mode="after")
    def validate_business_rules(self) -> "PromotionCreateRequest":
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("La fecha fin debe ser igual o posterior a la fecha inicio")
        _validate_discount(self.tipo_descuento, self.valor)
        return self


class PromotionUpdateRequest(_PromotionTextFields):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    codigo: str | None = Field(default=None, min_length=1, max_length=50)
    descripcion: str | None = Field(default=None, max_length=200)
    tipo_descuento: DiscountType | None = None
    valor: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None
    acumulable: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "PromotionUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar")
        required = {
            "nombre",
            "tipo_descuento",
            "valor",
            "fecha_inicio",
            "fecha_fin",
            "acumulable",
        }
        if any(getattr(self, field) is None for field in self.model_fields_set & required):
            raise ValueError("Los campos obligatorios no aceptan null")
        if self.fecha_inicio is not None and self.fecha_fin is not None:
            if self.fecha_fin < self.fecha_inicio:
                raise ValueError(
                    "La fecha fin debe ser igual o posterior a la fecha inicio"
                )
        if self.tipo_descuento is not None and self.valor is not None:
            _validate_discount(self.tipo_descuento, self.valor)
        return self


class PromotionStatusUpdateRequest(_StrictModel):
    estado: bool


class PromotionProductsRequest(_StrictModel):
    id_productos: list[int] = Field(min_length=1, max_length=100)

    @field_validator("id_productos")
    @classmethod
    def validate_product_ids(cls, value: list[int]) -> list[int]:
        if any(product_id <= 0 for product_id in value):
            raise ValueError("Los identificadores de producto deben ser positivos")
        if len(set(value)) != len(value):
            raise ValueError("No se permiten productos repetidos")
        return value


class PromotionProductData(BaseModel):
    id_promocion_producto: int
    id_producto: int
    nombre: str
    seccion: str
    precio: Decimal
    estado: bool


class AdminPromotionData(BaseModel):
    id_promocion: int
    nombre: str
    codigo: str | None
    descripcion: str | None
    tipo_descuento: DiscountType
    valor: Decimal
    fecha_inicio: datetime
    fecha_fin: datetime
    acumulable: bool
    estado: bool
    vigencia: Validity
    total_productos: int
    created_at: datetime
    updated_at: datetime


class AdminPromotionDetailData(AdminPromotionData):
    productos: list[PromotionProductData]


class PromotionPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class AdminPromotionListResponse(BaseModel):
    success: Literal[True] = True
    data: list[AdminPromotionData]
    pagination: PromotionPaginationData


class AdminPromotionResponse(BaseModel):
    success: Literal[True] = True
    data: AdminPromotionDetailData


class AdminPromotionCreateResponse(AdminPromotionResponse):
    message: str = "Promocion creada correctamente"


class AdminPromotionUpdateResponse(AdminPromotionResponse):
    message: str


class PromotionProductListResponse(BaseModel):
    success: Literal[True] = True
    data: list[PromotionProductData]


class PromotionProductsResponse(PromotionProductListResponse):
    message: str
