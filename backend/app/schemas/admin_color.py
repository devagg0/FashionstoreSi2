"""Contratos administrativos del catálogo global color."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ColorCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=50)
    codigo_hex: str | None = Field(default=None, max_length=7)

    @field_validator("nombre", "codigo_hex", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ColorUpdateRequest(ColorCreateRequest):
    nombre: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser null")
        return self


class ColorStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar un color."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminColorData(BaseModel):
    """Representación pública de un color."""

    id_color: int
    nombre: str
    codigo_hex: str | None
    created_at: datetime
    updated_at: datetime
    estado: bool


class ColorPaginationData(BaseModel):
    """Metadatos del listado paginado de colores."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminColorListResponse(BaseModel):
    """Listado paginado de colores."""

    success: Literal[True] = True
    data: list[AdminColorData]
    pagination: ColorPaginationData


class AdminColorResponse(BaseModel):
    """Detalle de un color."""

    success: Literal[True] = True
    data: AdminColorData


class AdminColorCreateResponse(AdminColorResponse):
    """Respuesta de creación de un color."""

    message: str = "Color creado correctamente"


class AdminColorUpdateResponse(AdminColorResponse):
    """Respuesta de modificación de un color."""

    message: str
