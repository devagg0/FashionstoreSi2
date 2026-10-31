"""Contratos Pydantic de entrada y salida para PK07 / CU04."""

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


ALLOWED_CU04_ROLES = {"CAJERO", "ENCARGADO_SUCURSAL", "CLIENTE", "PROVEEDOR"}


class AssociateUserRequest(BaseModel):
    """Datos permitidos para asociar un usuario a una empresa."""

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "id_usuario": 10,
                "rol": "CAJERO",
                "estado": "ACTIVO",
                "es_propietario": False,
            }
        },
    )

    id_usuario: int = Field(gt=0, description="Identificador del usuario existente")
    rol: str = Field(min_length=1, max_length=50, description="Nombre del rol empresarial a asignar")
    estado: str = Field(
        default="ACTIVO",
        pattern="^(INVITADO|ACTIVO|SUSPENDIDO|RETIRADO)$",
        description="Estado de la membresía en la empresa",
    )
    es_propietario: bool = Field(
        default=False,
        description="En CU04 no se permite asignar la condición de Titular / Propietario",
    )

    @field_validator("rol", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> object:
        if isinstance(value, str):
            val = value.strip().upper()
            if val == "ADMINISTRADOR":
                raise ValueError("La asignación del rol ADMINISTRADOR corresponde exclusivamente a CU03.")
            if val not in ALLOWED_CU04_ROLES:
                raise ValueError(
                    f"El rol '{val}' no está permitido en CU04. Roles permitidos: {', '.join(sorted(ALLOWED_CU04_ROLES))}."
                )
            return val
        return value

    @field_validator("es_propietario", mode="before")
    @classmethod
    def validate_not_propietario(cls, value: object) -> object:
        if bool(value):
            raise ValueError("En CU04 no se permite asignar la condición de Titular / Propietario; corresponde exclusivamente a CU03.")
        return False

    @field_validator("estado", mode="before")
    @classmethod
    def normalize_state(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class CompanyUserData(BaseModel):
    """Representación pública de un usuario asociado a la empresa."""

    id_empresa: int
    id_usuario: int
    nombre: str
    apellido: str
    correo: EmailStr
    telefono: str | None = None
    id_rol: int
    rol: str
    estado: str
    es_propietario: bool
    created_at: datetime
    updated_at: datetime


class CompanyUserResponse(BaseModel):
    """Respuesta de asociación individual de usuario."""

    success: Literal[True] = True
    message: str = "Usuario asociado correctamente a la empresa"
    data: CompanyUserData


class CompanyUsersListResponse(BaseModel):
    """Listado de usuarios asociados a la empresa."""

    success: Literal[True] = True
    data: list[CompanyUserData]
    total: int


class CreateCompanyBranchRequest(BaseModel):
    """Datos requeridos para crear una sucursal directamente dentro de una empresa."""

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "id_ciudad": 1,
                "nombre": "Sucursal Central",
                "direccion": "Av. San Martín #123",
                "telefono": "78901234",
                "hora_apertura": "08:30:00",
                "hora_cierre": "20:00:00",
            }
        },
    )

    id_ciudad: int = Field(gt=0, description="Identificador de la ciudad asociada")
    nombre: str = Field(min_length=1, max_length=150, description="Nombre descriptivo de la sucursal")
    direccion: str = Field(min_length=1, max_length=200, description="Dirección física")
    telefono: str | None = Field(default=None, max_length=30)
    hora_apertura: time | None = None
    hora_cierre: time | None = None

    @field_validator("id_ciudad", mode="before")
    @classmethod
    def coerce_city_id(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return value

    @field_validator("nombre", "direccion", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("telefono", mode="before")
    @classmethod
    def clean_phone(cls, value: object) -> object:
        if isinstance(value, str):
            val = value.strip()
            return val if val else None
        return value

    @field_validator("hora_apertura", "hora_cierre", mode="before")
    @classmethod
    def normalize_time(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            val = value.strip()
            if not val:
                return None
            parts = val.split(":")
            if len(parts) == 2:
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
            if len(parts) == 3:
                return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
            return val
        return value


class AssociateExistingBranchRequest(BaseModel):
    """Petición para asociar una sucursal existente a la empresa."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "id_sucursal": 5,
            }
        },
    )

    id_sucursal: int = Field(gt=0, description="Identificador de la sucursal a asociar")


class CompanyBranchData(BaseModel):
    """Representación pública de una sucursal perteneciente a la empresa."""

    id_sucursal: int
    empresa_id: int
    id_ciudad: int
    ciudad_nombre: str | None = None
    nombre: str
    direccion: str
    telefono: str | None = None
    hora_apertura: time | None = None
    hora_cierre: time | None = None
    estado: bool
    created_at: datetime
    updated_at: datetime


class CompanyBranchResponse(BaseModel):
    """Respuesta de creación o asociación de sucursal."""

    success: Literal[True] = True
    message: str = "Sucursal asociada correctamente a la empresa"
    data: CompanyBranchData


class CompanyBranchesListResponse(BaseModel):
    """Listado de sucursales asociadas a la empresa."""

    success: Literal[True] = True
    data: list[CompanyBranchData]
    total: int


class CompanyResourcesData(BaseModel):
    """Vista consolidada de los recursos (usuarios y sucursales) de una empresa."""

    id_empresa: int
    empresa_nombre: str
    empresa_codigo: str
    usuarios: list[CompanyUserData]
    sucursales: list[CompanyBranchData]


class CompanyResourcesResponse(BaseModel):
    """Respuesta consolidada de recursos de una empresa."""

    success: Literal[True] = True
    data: CompanyResourcesData

