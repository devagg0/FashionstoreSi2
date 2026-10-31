"""Contratos HTTP de CU01: registrar empresa contratante."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


COMPANY_CODE_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
NIT_PATTERN = r"^[0-9]{5,30}$"


class CompanyCreateRequest(BaseModel):
    """Campos permitidos por CU01; estado y relaciones son internos."""

    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(min_length=1, max_length=63, pattern=COMPANY_CODE_PATTERN)
    nombre: str = Field(min_length=1, max_length=150)
    nit: str | None = Field(default=None, max_length=30, pattern=NIT_PATTERN)
    zona_horaria: str = Field(default="America/La_Paz", min_length=1, max_length=50)

    @field_validator("codigo", "nombre", "zona_horaria", mode="before")
    @classmethod
    def trim_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("nit", mode="before")
    @classmethod
    def normalize_nit(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("zona_horaria")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("zona_horaria debe ser un identificador IANA vÃ¡lido") from error
        return value


class CompanyData(BaseModel):
    id_empresa: int
    codigo: str
    nombre: str
    nit: str | None
    zona_horaria: str
    estado: Literal["ACTIVA", "SUSPENDIDA", "CANCELADA"]
    created_at: datetime
    updated_at: datetime


class CompanyCreateResponse(BaseModel):
    success: Literal[True] = True
    message: str = "Empresa registrada correctamente"
    data: CompanyData
