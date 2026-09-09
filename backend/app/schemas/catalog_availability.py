"""Contrato publico de CU13, sin paginacion ni datos administrativos."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.catalog import CatalogColorData, CatalogSizeData


class AvailabilityProductData(BaseModel):
    id_producto: int
    nombre: str
    estado: bool


class AvailabilityVariantData(BaseModel):
    id_variante_producto: int
    sku: str
    talla: CatalogSizeData
    color: CatalogColorData
    estado: bool


class BranchAvailabilityData(BaseModel):
    variante: AvailabilityVariantData
    id_sucursal: int
    nombre_sucursal: str
    id_ciudad: int
    nombre_ciudad: str
    stock_actual: int
    stock_reservado: int
    stock_disponible: int = Field(ge=0)


class CatalogAvailabilityData(BaseModel):
    producto: AvailabilityProductData
    disponibilidad: list[BranchAvailabilityData]


class CatalogAvailabilityResponse(BaseModel):
    success: Literal[True] = True
    data: CatalogAvailabilityData
    message: str = "Disponibilidad consultada correctamente"
