"""Contratos administrativos del catálogo global categoría."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=200)

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CategoryUpdateRequest(CategoryCreateRequest):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser null")
        return self


class CategoryStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar una categoría."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminCategoryData(BaseModel):
    """Representación pública de una categoría."""

    id_categoria: int
    nombre: str
    descripcion: str | None
    created_at: datetime
    updated_at: datetime
    estado: bool


class CategoryPaginationData(BaseModel):
    """Metadatos del listado paginado de categorías."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminCategoryListResponse(BaseModel):
    """Listado paginado de categorías."""

    success: Literal[True] = True
    data: list[AdminCategoryData]
    pagination: CategoryPaginationData


class AdminCategoryResponse(BaseModel):
    """Detalle de una categoría."""

    success: Literal[True] = True
    data: AdminCategoryData


class AdminCategoryCreateResponse(AdminCategoryResponse):
    """Respuesta de creación de una categoría."""

    message: str = "Categoría creada correctamente"


class AdminCategoryUpdateResponse(AdminCategoryResponse):
    """Respuesta de modificación de una categoría."""

    message: str
