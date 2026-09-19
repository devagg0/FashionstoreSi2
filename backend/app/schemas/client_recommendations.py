"""CU26: contratos publicos del recomendador de prendas para el cliente."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


RecommendationOrigin = Literal["PERSONALIZADO", "FALLBACK"]
DiscountType = Literal["PORCENTAJE", "MONTO_FIJO"]


class RecommendationPromotionData(BaseModel):
    """Mejor promocion vigente aplicable al producto recomendado."""

    id_promocion: int
    nombre: str
    codigo: str | None
    descripcion: str | None
    tipo_descuento: DiscountType
    valor: Decimal
    fecha_inicio: datetime
    fecha_fin: datetime
    acumulable: bool


class RecommendationVariantData(BaseModel):
    """Variante concreta con stock que el cliente puede agregar al carrito."""

    id_variante_producto: int
    sku: str
    id_talla: int
    talla: str
    id_color: int
    color: str
    codigo_hex: str | None
    stock_disponible: int


class RecommendationItemData(BaseModel):
    """Prenda recomendada con su precio vigente y el motivo de la sugerencia."""

    id_producto: int
    nombre: str
    descripcion_corta: str | None
    seccion: Literal["HOMBRE", "MUJER", "UNISEX"]
    id_categoria: int
    categoria: str
    id_temporada: int | None
    temporada: str | None
    precio_base: Decimal
    precio_final: Decimal
    tiene_promocion: bool
    promocion: RecommendationPromotionData | None
    monto_descuento: Decimal | None
    porcentaje_descuento: Decimal | None
    imagen_principal: str | None
    variante_sugerida: RecommendationVariantData | None
    score: float
    motivo: str
    ya_comprado: bool


class RecommendationListResponse(BaseModel):
    """Envoltura de respuesta alineada con el resto de los CU del cliente."""

    success: Literal[True] = True
    data: list[RecommendationItemData]
    origen: RecommendationOrigin
    message: str = "Recomendaciones generadas correctamente"
