"""Contratos de CU14; las existencias solo se consultan."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InventoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_sucursal: int = Field(gt=0)
    id_variante_producto: int = Field(gt=0)
    stock_minimo: int = Field(default=0, ge=0, strict=True)


class InventoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_minimo: int = Field(ge=0, strict=True)


class InventoryData(BaseModel):
    id_inventario_sucursal: int
    id_sucursal: int
    sucursal: str
    sucursal_estado: bool
    id_ciudad: int
    ciudad: str
    id_producto: int
    producto: str
    producto_estado: bool
    id_variante_producto: int
    sku: str
    variante_estado: bool
    id_talla: int
    talla: str
    id_color: int
    color: str
    stock_actual: int
    stock_reservado: int
    stock_disponible: int
    stock_minimo: int
    created_at: datetime
    updated_at: datetime


class InventoryPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class InventoryResponse(BaseModel):
    success: Literal[True] = True
    data: InventoryData


class InventoryListResponse(BaseModel):
    success: Literal[True] = True
    data: list[InventoryData]
    pagination: InventoryPaginationData
