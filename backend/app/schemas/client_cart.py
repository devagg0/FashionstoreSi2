"""CU19: contratos del carrito autenticado; precios actuales, no persistidos."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.catalog import CatalogColorData, CatalogPromotionData, CatalogSizeData


class CartItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_variante_producto: int = Field(gt=0, le=2147483647, strict=True)
    cantidad: int = Field(ge=1, le=2147483647, strict=True)


class CartQuantityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cantidad: int = Field(ge=1, le=2147483647, strict=True)


class CartItemData(BaseModel):
    id_detalle_carrito: int
    id_variante_producto: int
    id_producto: int
    nombre_producto: str
    sku: str
    talla: CatalogSizeData
    color: CatalogColorData
    imagen_principal: str | None
    cantidad: int
    precio_base: Decimal
    precio_final: Decimal
    promocion: CatalogPromotionData | None
    subtotal_linea: Decimal
    disponibilidad_actual: int = Field(
        description="Máxima cantidad disponible en una sola sucursal activa; no suma sucursales ni garantiza disponibilidad conjunta."
    )
    estado_producto: bool
    estado_variante: bool


class CartData(BaseModel):
    id_carrito: int | None = None
    estado: Literal["ACTIVO"] | None = None
    items: list[CartItemData] = Field(default_factory=list)
    cantidad_items: int = 0
    cantidad_unidades: int = 0
    subtotal: Decimal = Decimal("0.00")
    descuento_total: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")


class CartResponse(BaseModel):
    success: Literal[True] = True
    data: CartData
    message: str = "Carrito consultado correctamente"
