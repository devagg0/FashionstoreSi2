"""Contratos administrativos del catálogo global coleccion."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CollectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=200)

    @field_validator("nombre", "descripcion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CollectionUpdateRequest(CollectionCreateRequest):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser null")
        return self


class CollectionStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar una coleccion."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminCollectionData(BaseModel):
    """Representación pública de una coleccion."""

    id_coleccion: int
    nombre: str
    descripcion: str | None
    created_at: datetime
    updated_at: datetime
    estado: bool


class CollectionPaginationData(BaseModel):
    """Metadatos del listado paginado de colecciones."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminCollectionListResponse(BaseModel):
    """Listado paginado de colecciones."""

    success: Literal[True] = True
    data: list[AdminCollectionData]
    pagination: CollectionPaginationData


class AdminCollectionResponse(BaseModel):
    """Detalle de una coleccion."""

    success: Literal[True] = True
    data: AdminCollectionData


class AdminCollectionCreateResponse(AdminCollectionResponse):
    """Respuesta de creación de una coleccion."""

    message: str = "Coleccion creada correctamente"


class AdminCollectionUpdateResponse(AdminCollectionResponse):
    """Respuesta de modificación de una coleccion."""

    message: str
