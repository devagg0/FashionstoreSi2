"""Contratos administrativos del catálogo global temporada."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SeasonCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=200)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SeasonUpdateRequest(SeasonCreateRequest):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser null")
        return self


class SeasonStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar una temporada."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminSeasonData(BaseModel):
    """Representación pública de una temporada."""

    id_temporada: int
    nombre: str
    descripcion: str | None
    fecha_inicio: date | None
    fecha_fin: date | None
    created_at: datetime
    updated_at: datetime
    estado: bool


class SeasonPaginationData(BaseModel):
    """Metadatos del listado paginado de temporadas."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminSeasonListResponse(BaseModel):
    """Listado paginado de temporadas."""

    success: Literal[True] = True
    data: list[AdminSeasonData]
    pagination: SeasonPaginationData


class AdminSeasonResponse(BaseModel):
    """Detalle de una temporada."""

    success: Literal[True] = True
    data: AdminSeasonData


class AdminSeasonCreateResponse(AdminSeasonResponse):
    """Respuesta de creación de una temporada."""

    message: str = "Temporada creada correctamente"


class AdminSeasonUpdateResponse(AdminSeasonResponse):
    """Respuesta de modificación de una temporada."""

    message: str
