"""Contratos administrativos del catálogo global proveedor."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class SupplierCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=150)
    nit: str | None = Field(default=None, max_length=30)
    telefono: str | None = Field(default=None, max_length=30)
    correo: EmailStr | None = Field(default=None, max_length=150)
    direccion: str | None = Field(default=None, max_length=200)
    id_usuario: None = Field(
        default=None,
        description="CU09 no asocia usuarios; omitir o enviar null al crear.",
    )

    @field_validator("nombre", "nit", "telefono", "correo", "direccion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SupplierUpdateRequest(SupplierCreateRequest):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)

    @model_validator(mode="after")
    def validate_patch(self):
        if "id_usuario" in self.model_fields_set:
            raise ValueError("CU09 no modifica asociaciones de usuarios")
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser null")
        return self


class SupplierStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar un proveedor."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class AdminSupplierData(BaseModel):
    """Representación pública de un proveedor."""

    id_proveedor: int
    nombre: str
    id_usuario: int | None
    nit: str | None
    telefono: str | None
    correo: str | None
    direccion: str | None
    created_at: datetime
    updated_at: datetime
    estado: bool


class SupplierPaginationData(BaseModel):
    """Metadatos del listado paginado de proveedores."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminSupplierListResponse(BaseModel):
    """Listado paginado de proveedores."""

    success: Literal[True] = True
    data: list[AdminSupplierData]
    pagination: SupplierPaginationData


class AdminSupplierResponse(BaseModel):
    """Detalle de un proveedor."""

    success: Literal[True] = True
    data: AdminSupplierData


class AdminSupplierCreateResponse(AdminSupplierResponse):
    """Respuesta de creación de un proveedor."""

    message: str = "Proveedor creado correctamente"


class AdminSupplierUpdateResponse(AdminSupplierResponse):
    """Respuesta de modificación de un proveedor."""

    message: str
