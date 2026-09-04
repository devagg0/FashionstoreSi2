"""Contratos de entrada y salida para autenticación."""

import re
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


def _validate_password_strength(value: SecretStr) -> SecretStr:
    """Aplica la política de complejidad compartida por autenticación."""
    password = value.get_secret_value()
    requirements = (
        (any(character.isupper() for character in password), "una mayúscula"),
        (any(character.islower() for character in password), "una minúscula"),
        (any(character.isdigit() for character in password), "un número"),
        (
            any(
                not character.isalnum() and not character.isspace()
                for character in password
            ),
            "un carácter especial",
        ),
    )
    missing = [
        description for is_valid, description in requirements if not is_valid
    ]

    if missing:
        raise ValueError(
            "La contraseña debe contener al menos " + ", ".join(missing)
        )

    return value


class ClientRegisterRequest(BaseModel):
    """Datos permitidos para registrar una cuenta de cliente."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "nombre": "Andres",
                "apellido": "Garcia",
                "correo": "andres@gmail.com",
                "telefono": "70000000",
                "password": "Fashion@2026",
                "confirm_password": "Fashion@2026",
            }
        },
    )

    nombre: str = Field(min_length=2, max_length=100)
    apellido: str = Field(min_length=2, max_length=100)
    correo: EmailStr
    telefono: str | None = Field(default=None, min_length=5, max_length=30)
    password: SecretStr = Field(min_length=8, max_length=128)
    confirm_password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def trim_required_text(cls, value: object) -> object:
        """Elimina espacios externos antes de validar la longitud."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("correo", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        """Normaliza el correo para comparar y almacenar un valor canónico."""
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("telefono", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        """Acepta la ausencia del teléfono y elimina espacios externos."""
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        return normalized or None

    @field_validator("telefono")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        """Permite formatos telefónicos internacionales de uso habitual."""
        if value is None:
            return None

        if not re.fullmatch(r"[0-9+().\-\s]+", value) or not any(
            character.isdigit() for character in value
        ):
            raise ValueError("El teléfono contiene caracteres inválidos")

        return value

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: SecretStr) -> SecretStr:
        """Aplica la política de complejidad del registro."""
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def passwords_match(self) -> Self:
        """Comprueba que la confirmación coincida exactamente."""
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("Las contraseñas no coinciden")

        return self


class RegisteredClientData(BaseModel):
    """Datos públicos del cliente recién registrado."""

    id_usuario: int
    nombre: str
    apellido: str
    correo: EmailStr


class ClientRegisterResponse(BaseModel):
    """Respuesta exitosa de registro."""

    success: Literal[True] = True
    message: str = "Cliente registrado correctamente"
    data: RegisteredClientData


class ErrorResponse(BaseModel):
    """Formato seguro y consistente para errores de autenticación."""

    success: Literal[False] = False
    message: str


class LoginRequest(BaseModel):
    """Credenciales mínimas requeridas para iniciar sesión."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "correo": "cliente@correo.com",
                "password": "Fashion@2026",
            }
        },
    )

    correo: EmailStr
    password: SecretStr = Field(min_length=1)

    @field_validator("correo", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        """Elimina espacios externos y normaliza el correo a minúsculas."""
        return value.strip().lower() if isinstance(value, str) else value


class AuthenticatedUserData(BaseModel):
    """Información pública del usuario autenticado."""

    id_usuario: int
    nombre: str
    apellido: str
    correo: EmailStr
    rol: str


class LoginResponse(BaseModel):
    """Respuesta exitosa del inicio de sesión."""

    success: Literal[True] = True
    message: str = "Inicio de sesión exitoso"
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    usuario: AuthenticatedUserData


class CurrentUserResponse(BaseModel):
    """Respuesta del endpoint técnico que valida el Bearer JWT."""

    success: Literal[True] = True
    data: AuthenticatedUserData


class ChangePasswordRequest(BaseModel):
    """Contraseñas requeridas para actualizar la credencial autenticada."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "current_password": "Actual@2026",
                "new_password": "Nueva@2026",
                "confirm_password": "Nueva@2026",
            }
        },
    )

    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=128)
    confirm_password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: SecretStr) -> SecretStr:
        """Aplica a la contraseña nueva la misma política del registro."""
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def new_passwords_match(self) -> Self:
        """Comprueba que la confirmación de la contraseña nueva coincida."""
        if (
            self.new_password.get_secret_value()
            != self.confirm_password.get_secret_value()
        ):
            raise ValueError("Las contraseñas no coinciden")

        return self


class ChangePasswordResponse(BaseModel):
    """Respuesta segura después de cambiar la contraseña."""

    success: Literal[True] = True
    message: str = "Contraseña actualizada correctamente"


class PasswordRecoveryEmailRequest(BaseModel):
    """Correo para iniciar una recuperación sin revelar si existe."""

    model_config = ConfigDict(extra="forbid")

    correo: EmailStr

    @field_validator("correo", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        """Normaliza el correo antes de buscarlo."""
        return value.strip().lower() if isinstance(value, str) else value


class PasswordRecoveryRequestResponse(BaseModel):
    """Respuesta indistinguible para correos existentes y desconocidos."""

    success: Literal[True] = True
    message: str = (
        "Si el correo está registrado, recibirás un código de recuperación"
    )


class PasswordRecoveryVerifyRequest(BaseModel):
    """Correo y código temporal que deben verificarse juntos."""

    model_config = ConfigDict(extra="forbid")

    correo: EmailStr
    codigo: SecretStr = Field(min_length=6, max_length=6)

    @field_validator("correo", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        """Normaliza el correo antes de buscarlo."""
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("codigo")
    @classmethod
    def validate_six_digit_code(cls, value: SecretStr) -> SecretStr:
        """Acepta exactamente seis dígitos decimales."""
        if not re.fullmatch(r"\d{6}", value.get_secret_value()):
            raise ValueError("El código debe contener exactamente 6 dígitos")
        return value


class PasswordRecoveryVerifyResponse(BaseModel):
    """Reset token temporal emitido después de verificar el código."""

    success: Literal[True] = True
    message: str = "Código verificado correctamente"
    reset_token: str


class PasswordRecoveryResetRequest(BaseModel):
    """Reset token y contraseña nueva para finalizar la recuperación."""

    model_config = ConfigDict(extra="forbid")

    reset_token: SecretStr = Field(min_length=1)
    new_password: SecretStr = Field(min_length=8, max_length=128)
    confirm_password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, value: SecretStr) -> SecretStr:
        """Reutiliza la política de complejidad de autenticación."""
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def new_passwords_match(self) -> Self:
        """Comprueba que ambas contraseñas nuevas coincidan."""
        if (
            self.new_password.get_secret_value()
            != self.confirm_password.get_secret_value()
        ):
            raise ValueError("Las contraseñas no coinciden")
        return self


class PasswordRecoveryResetResponse(BaseModel):
    """Respuesta segura después del restablecimiento."""

    success: Literal[True] = True
    message: str = "Contraseña restablecida correctamente"
