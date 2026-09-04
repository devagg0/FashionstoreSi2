"""Contratos seguros para la administración de usuarios y roles."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import ClientRegisterRequest


InternalRoleName = Literal[
    "CAJERO",
    "ENCARGADO_SUCURSAL",
]


class AdminUserCreateRequest(ClientRegisterRequest):
    """Datos permitidos para crear una cuenta interna desde CU03."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "nombre": "Andrea",
                "apellido": "Flores",
                "correo": "andrea@fashionstore.com",
                "telefono": "70000000",
                "rol": "CAJERO",
                "password": "Fashion@2026",
                "confirm_password": "Fashion@2026",
            }
        },
    )

    rol: InternalRoleName

    @field_validator("rol", mode="before")
    @classmethod
    def normalize_internal_role(cls, value: object) -> object:
        """Normaliza el rol antes de restringirlo a los roles internos."""
        if not isinstance(value, str):
            return value

        normalized_role = value.strip().upper()
        if normalized_role not in {"CAJERO", "ENCARGADO_SUCURSAL"}:
            raise ValueError(
                "Solo se permite crear usuarios con rol CAJERO o "
                "ENCARGADO_SUCURSAL"
            )
        return normalized_role


class UserStatusUpdateRequest(BaseModel):
    """Estado permitido para activar o desactivar una cuenta."""

    model_config = ConfigDict(extra="forbid")

    estado: bool


class UserRoleUpdateRequest(BaseModel):
    """Nombre del rol que se asignará consultando siempre t_rol."""

    model_config = ConfigDict(extra="forbid")

    rol: str = Field(min_length=1, max_length=50)

    @field_validator("rol", mode="before")
    @classmethod
    def normalize_role_name(cls, value: object) -> object:
        """Elimina espacios externos y normaliza el nombre del rol."""
        return value.strip().upper() if isinstance(value, str) else value


class AdminUserData(BaseModel):
    """Campos públicos de un usuario; excluye explícitamente credenciales."""

    id_usuario: int
    nombre: str
    apellido: str
    correo: EmailStr
    estado: bool
    rol: str


class PaginationData(BaseModel):
    """Metadatos de una página de resultados."""

    page: int
    page_size: int
    total: int
    total_pages: int


class AdminUserListResponse(BaseModel):
    """Listado paginado de usuarios."""

    success: Literal[True] = True
    data: list[AdminUserData]
    pagination: PaginationData


class AdminUserResponse(BaseModel):
    """Detalle seguro de un usuario."""

    success: Literal[True] = True
    data: AdminUserData


class AdminUserUpdateResponse(BaseModel):
    """Resultado de un cambio administrativo sobre un usuario."""

    success: Literal[True] = True
    message: str
    data: AdminUserData


class AdminUserCreateResponse(BaseModel):
    """Respuesta segura de creación de una cuenta interna."""

    success: Literal[True] = True
    message: str = "Usuario creado correctamente"
    data: AdminUserData


class AdminRoleData(BaseModel):
    """Datos públicos de un rol configurado en t_rol."""

    id_rol: int
    nombre: str
    descripcion: str | None
    estado: bool


class AdminRoleListResponse(BaseModel):
    """Roles existentes disponibles para la administración."""

    success: Literal[True] = True
    data: list[AdminRoleData]
