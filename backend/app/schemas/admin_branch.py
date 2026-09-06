"""Contratos de la API para la gestión administrativa de sucursales."""

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BranchFieldsRequest(BaseModel):
    """Campos editables de sucursal, con las longitudes del modelo."""

    model_config = ConfigDict(extra="forbid")

    id_ciudad: int = Field(gt=0)
    nombre: str = Field(min_length=1, max_length=150)
    direccion: str = Field(min_length=1, max_length=200)
    telefono: str | None = Field(default=None, max_length=30)
    hora_apertura: time | None = None
    hora_cierre: time | None = None

    @field_validator("nombre", "direccion", "telefono", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class BranchCreateRequest(BranchFieldsRequest):
    """Datos permitidos para crear una sucursal."""


class BranchUpdateRequest(BranchFieldsRequest):
    """Actualización parcial; los campos obligatorios no admiten null."""

    id_ciudad: int | None = Field(default=None, gt=0)
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    direccion: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        for field in ("id_ciudad", "nombre", "direccion"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} no admite null")
        return self


class BranchStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar una sucursal."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminBranchData(BaseModel):
    """Representación pública de una sucursal."""

    id_sucursal: int
    id_ciudad: int
    nombre: str
    direccion: str
    telefono: str | None
    hora_apertura: time | None
    hora_cierre: time | None
    estado: bool
    created_at: datetime
    updated_at: datetime


class BranchPaginationData(BaseModel):
    """Metadatos del listado paginado de sucursales."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminBranchListResponse(BaseModel):
    """Listado paginado de sucursales."""

    success: Literal[True] = True
    data: list[AdminBranchData]
    pagination: BranchPaginationData


class AdminBranchResponse(BaseModel):
    """Detalle de una sucursal."""

    success: Literal[True] = True
    data: AdminBranchData


class AdminBranchCreateResponse(AdminBranchResponse):
    """Respuesta de creación de una sucursal."""

    message: str = "Sucursal creada correctamente"


class AdminBranchUpdateResponse(AdminBranchResponse):
    """Respuesta de modificación de una sucursal."""

    message: str
