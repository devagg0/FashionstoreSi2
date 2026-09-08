"""Contratos publicos de CU12 para consultar el catalogo."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


CatalogSort = Literal["recientes", "precio_asc", "precio_desc", "nombre"]
AvailabilityStatus = Literal["DISPONIBLE", "AGOTADO"]
DiscountType = Literal["PORCENTAJE", "MONTO_FIJO"]


class CatalogColorData(BaseModel):
    id_color: int
    nombre: str
    codigo_hex: str | None


class CatalogSizeData(BaseModel):
    id_talla: int
    nombre: str


class CatalogCollectionData(BaseModel):
    id_coleccion: int
    nombre: str


class CatalogImageData(BaseModel):
    id_imagen_producto: int
    url_imagen: str
    es_principal: bool


class CatalogPromotionData(BaseModel):
    id_promocion: int
    nombre: str
    codigo: str | None
    descripcion: str | None
    tipo_descuento: DiscountType
    valor: Decimal
    porcentaje_descuento: Decimal | None
    monto_descuento: Decimal
    precio_resultante: Decimal
    fecha_inicio: datetime
    fecha_fin: datetime
    acumulable: bool


class CatalogProductAvailabilityData(BaseModel):
    id_sucursal: int
    sucursal: str
    estado: AvailabilityStatus
    cantidad_disponible: int


class CatalogVariantAvailabilityData(BaseModel):
    id_sucursal: int
    estado: AvailabilityStatus
    cantidad_disponible: int


class CatalogProductData(BaseModel):
    id_producto: int
    nombre: str
    descripcion_corta: str | None
    seccion: Literal["HOMBRE", "MUJER", "UNISEX"]
    id_categoria: int
    categoria: str
    precio_base: Decimal
    precio_final: Decimal
    tiene_promocion: bool
    promocion_destacada: CatalogPromotionData | None
    porcentaje_descuento: Decimal | None
    monto_descuento: Decimal | None
    imagen_principal: str | None
    colores_disponibles: list[CatalogColorData]
    tallas_disponibles: list[CatalogSizeData]
    disponibilidad_sucursal: CatalogProductAvailabilityData | None = None


class CatalogVariantData(BaseModel):
    id_variante_producto: int
    sku: str
    talla: CatalogSizeData
    color: CatalogColorData
    disponibilidad_sucursal: CatalogVariantAvailabilityData | None = None


class CatalogProductDetailData(BaseModel):
    id_producto: int
    nombre: str
    descripcion: str | None
    seccion: Literal["HOMBRE", "MUJER", "UNISEX"]
    id_categoria: int
    categoria: str
    id_temporada: int | None
    temporada: str | None
    precio_base: Decimal
    precio_final: Decimal
    tiene_promocion: bool
    promociones_vigentes: list[CatalogPromotionData]
    promocion_destacada: CatalogPromotionData | None
    porcentaje_descuento: Decimal | None
    monto_descuento: Decimal | None
    imagen_principal: str | None
    galeria: list[CatalogImageData]
    variantes: list[CatalogVariantData]
    tallas: list[CatalogSizeData]
    colores: list[CatalogColorData]
    colecciones: list[CatalogCollectionData]


class CatalogPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class CatalogProductListResponse(BaseModel):
    success: Literal[True] = True
    data: list[CatalogProductData]
    pagination: CatalogPaginationData


class CatalogProductResponse(BaseModel):
    success: Literal[True] = True
    data: CatalogProductDetailData
