"""Contratos administrativos del catálogo global talla."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SizeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=20)
    descripcion: str | None = Field(default=None, max_length=100)

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SizeUpdateRequest(SizeCreateRequest):
    nombre: str | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser null")
        return self


class SizeStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar una talla."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminSizeData(BaseModel):
    """Representación pública de una talla."""

    id_talla: int
    nombre: str
    descripcion: str | None
    created_at: datetime
    updated_at: datetime
    estado: bool


class SizePaginationData(BaseModel):
    """Metadatos del listado paginado de tallas."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminSizeListResponse(BaseModel):
    """Listado paginado de tallas."""

    success: Literal[True] = True
    data: list[AdminSizeData]
    pagination: SizePaginationData


class AdminSizeResponse(BaseModel):
    """Detalle de una talla."""

    success: Literal[True] = True
    data: AdminSizeData


class AdminSizeCreateResponse(AdminSizeResponse):
    """Respuesta de creación de una talla."""

    message: str = "Talla creada correctamente"


class AdminSizeUpdateResponse(AdminSizeResponse):
    """Respuesta de modificación de una talla."""

    message: str
