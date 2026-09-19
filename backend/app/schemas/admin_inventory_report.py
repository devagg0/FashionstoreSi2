"""Contratos CU29. Los estados negativos se informan sin corregir el saldo."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


StockState = Literal["AGOTADO", "BAJO_STOCK", "NORMAL"]


class InventoryReportFilters(BaseModel):
    id_sucursal: int | None = Field(default=None, gt=0)
    id_categoria: int | None = Field(default=None, gt=0)
    id_producto: int | None = Field(default=None, gt=0)
    estado_stock: StockState | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class InventoryReportKPIs(BaseModel):
    total_productos: int
    total_variantes: int
    total_registros_inventario: int
    unidades_actuales: int
    unidades_reservadas: int
    unidades_disponibles: int
    registros_agotados: int
    registros_bajo_stock: int
    productos_con_agotados: int
    productos_con_bajo_stock: int
    registros_con_stock_minimo_cero: int


class BranchBreakdown(InventoryReportKPIs):
    id_sucursal: int
    nombre: str
    estado: bool


class CategoryBreakdown(InventoryReportKPIs):
    id_categoria: int
    nombre: str
    estado: bool


class BranchData(BaseModel):
    id_sucursal: int
    nombre: str
    estado: bool


class CategoryData(BaseModel):
    id_categoria: int
    nombre: str
    estado: bool


class ProductData(BaseModel):
    id_producto: int
    nombre: str
    estado: bool


class VariantData(BaseModel):
    id_variante_producto: int
    sku: str
    talla: str
    color: str
    estado: bool


class InventoryReportItem(BaseModel):
    id_inventario_sucursal: int
    sucursal: BranchData
    categoria: CategoryData
    producto: ProductData
    variante: VariantData
    stock_actual: int
    stock_reservado: int
    stock_disponible: int
    stock_minimo: int
    estado_stock: StockState | None
    faltante_hasta_minimo: int


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class InventoryReportDetail(BaseModel):
    items: list[InventoryReportItem]
    pagination: Pagination


class InventoryWarning(BaseModel):
    codigo: Literal["STOCK_DISPONIBLE_NEGATIVO"] = "STOCK_DISPONIBLE_NEGATIVO"
    mensaje: str = "Hay inventarios con stock reservado mayor al actual; se conserva el saldo real."
    registros: int
    alcance: Literal["FILTROS_SIN_ESTADO_STOCK"] = "FILTROS_SIN_ESTADO_STOCK"


class InventoryReportData(BaseModel):
    generado_en: datetime
    filtros: InventoryReportFilters
    kpis: InventoryReportKPIs
    por_sucursal: list[BranchBreakdown]
    por_categoria: list[CategoryBreakdown]
    detalle: InventoryReportDetail
    advertencias: list[InventoryWarning]


class InventoryReportResponse(BaseModel):
    success: Literal[True] = True
    data: InventoryReportData
    message: str = "Reporte de inventario consultado correctamente"
