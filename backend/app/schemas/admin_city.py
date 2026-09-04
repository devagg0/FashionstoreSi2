"""Contratos de la API para la gestión administrativa de ciudades."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CityNameRequest(BaseModel):
    """Nombre normalizado usado al crear o modificar una ciudad."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=100)

    @field_validator("nombre", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        """Elimina espacios externos antes de validar la longitud."""
        return value.strip() if isinstance(value, str) else value


class CityCreateRequest(CityNameRequest):
    """Datos permitidos para crear una ciudad."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {"nombre": "Santa Cruz de la Sierra"},
        },
    )


class CityUpdateRequest(CityNameRequest):
    """Datos permitidos para modificar el nombre de una ciudad."""


class CityStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar una ciudad."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminCityData(BaseModel):
    """Representación pública de una ciudad."""

    id_ciudad: int
    nombre: str
    estado: bool


class CityPaginationData(BaseModel):
    """Metadatos del listado paginado de ciudades."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminCityListResponse(BaseModel):
    """Listado paginado de ciudades."""

    success: Literal[True] = True
    data: list[AdminCityData]
    pagination: CityPaginationData


class AdminCityResponse(BaseModel):
    """Detalle de una ciudad."""

    success: Literal[True] = True
    data: AdminCityData


class AdminCityCreateResponse(AdminCityResponse):
    """Respuesta de creación de una ciudad."""

    message: str = "Ciudad creada correctamente"


class AdminCityUpdateResponse(AdminCityResponse):
    """Respuesta de modificación de una ciudad."""

    message: str
