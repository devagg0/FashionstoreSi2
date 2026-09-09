"""Contratos de consulta CU16."""

from typing import Literal

from pydantic import BaseModel


class ProductData(BaseModel):
    id_producto: int
    nombre: str
    estado: bool


class CategoryData(BaseModel):
    id_categoria: int
    nombre: str


class VariantData(BaseModel):
    id_variante_producto: int
    sku: str
    estado: bool


class SizeData(BaseModel):
    id_talla: int
    nombre: str


class ColorData(BaseModel):
    id_color: int
    nombre: str


class GlobalInventoryData(BaseModel):
    producto: ProductData
    categoria: CategoryData
    variante: VariantData
    talla: SizeData
    color: ColorData
    total_stock_actual: int
    total_stock_reservado: int
    total_stock_disponible: int
    cantidad_sucursales: int
    cantidad_sucursales_con_stock: int


class BranchInventoryData(BaseModel):
    id_sucursal: int
    nombre_sucursal: str
    estado_sucursal: bool
    id_ciudad: int
    nombre_ciudad: str
    id_inventario_sucursal: int
    stock_actual: int
    stock_reservado: int
    stock_disponible: int
    stock_minimo: int


class GlobalInventoryDetailData(GlobalInventoryData):
    sucursales: list[BranchInventoryData]


class GlobalInventoryPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class GlobalInventoryListResponse(BaseModel):
    success: Literal[True] = True
    data: list[GlobalInventoryData]
    message: str = "Inventario global consultado correctamente"
    pagination: GlobalInventoryPaginationData


class GlobalInventoryResponse(BaseModel):
    success: Literal[True] = True
    data: GlobalInventoryDetailData
    message: str = "Detalle de inventario global consultado correctamente"
