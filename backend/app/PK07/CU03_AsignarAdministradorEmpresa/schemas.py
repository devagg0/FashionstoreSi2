"""Contratos HTTP de CU03: asignar administrador de empresa."""

from datetime import datetime
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


def _validate_password_strength(value: SecretStr) -> SecretStr:
    """Aplica la política de contraseñas seguras."""
    password = value.get_secret_value()
    requirements = (
        (any(c.isupper() for c in password), "una mayúscula"),
        (any(c.islower() for c in password), "una minúscula"),
        (any(c.isdigit() for c in password), "un número"),
        (any(not c.isalnum() and not c.isspace() for c in password), "un carácter especial"),
    )
    missing = [desc for is_valid, desc in requirements if not is_valid]
    if missing:
        raise ValueError("La contraseña debe contener al menos " + ", ".join(missing))
    return value


class AssignCompanyAdminRequest(BaseModel):
    """Payload para asignar un usuario existente como administrador de empresa."""

    model_config = ConfigDict(extra="forbid")

    id_usuario: int = Field(gt=0, description="Identificador único del usuario a asignar")
    estado: Literal["ACTIVO", "INVITADO"] = Field(
        default="ACTIVO",
        description="Estado de la membresía en la empresa",
    )


class CreateAndAssignCompanyAdminRequest(BaseModel):
    """Payload para crear un usuario nuevo con rol ADMINISTRADOR y asignarlo directamente."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=100, description="Nombre(s) del nuevo administrador")
    apellido: str = Field(min_length=1, max_length=100, description="Apellido(s) del nuevo administrador")
    correo: EmailStr = Field(description="Correo electrónico único del usuario")
    password: SecretStr = Field(min_length=8, max_length=128, description="Contraseña segura")
    telefono: str | None = Field(default=None, max_length=30, description="Teléfono de contacto opcional")
    estado: Literal["ACTIVO", "INVITADO"] = Field(
        default="ACTIVO",
        description="Estado de la membresía inicial en la empresa",
    )

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("El campo no puede estar vacío")
        return value

    @field_validator("telefono", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        return _validate_password_strength(value)


class CompanyAdminData(BaseModel):
    """Datos del administrador asignado a una empresa."""

    id_empresa: int
    id_usuario: int
    nombre: str
    apellido: str
    correo: str
    telefono: str | None = None
    rol: str = "ADMINISTRADOR"
    estado: str = "ACTIVO"
    es_propietario: bool = True
    created_at: datetime
    updated_at: datetime


class CompanyAdminResponse(BaseModel):
    """Respuesta al consultar el administrador de una empresa."""

    success: Literal[True] = True
    message: str = "Administrador consultado correctamente"
    data: CompanyAdminData


class AssignCompanyAdminResponse(BaseModel):
    """Respuesta al asignar el administrador de una empresa."""

    success: Literal[True] = True
    message: str = "Administrador asignado correctamente"
    data: CompanyAdminData


class AvailableUserData(BaseModel):
    """Datos de un usuario elegible para ser asignado como administrador."""

    id_usuario: int
    nombre: str
    apellido: str
    correo: str
    telefono: str | None = None
    rol_global: str
    estado: bool
    created_at: datetime


class AvailableUsersPaginationData(BaseModel):
    """Metadatos de paginación para búsqueda de usuarios disponibles."""

    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def create(cls, *, page: int, page_size: int, total: int) -> "AvailableUsersPaginationData":
        total_pages = ceil(total / page_size) if total > 0 else 0
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )


class AvailableUsersResponse(BaseModel):
    """Respuesta al buscar usuarios disponibles."""

    success: Literal[True] = True
    message: str = "Usuarios disponibles obtenidos correctamente"
    data: list[AvailableUserData]
    pagination: AvailableUsersPaginationData
