"""Contratos HTTP de CU02: gestionar empresas contratantes."""

from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.PK07.CU01_RegistrarEmpresa.schemas import (
    COMPANY_CODE_PATTERN,
    NIT_PATTERN,
    CompanyData,
)


CompanyState = Literal["ACTIVA", "SUSPENDIDA", "CANCELADA"]


class CompanyUpdateRequest(BaseModel):
    """Campos empresariales editables; relaciones, PK y estado quedan excluidos."""

    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(
        default=None,
        min_length=1,
        max_length=63,
        pattern=COMPANY_CODE_PATTERN,
    )
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    nit: str | None = Field(default=None, max_length=30, pattern=NIT_PATTERN)
    zona_horaria: str | None = Field(default=None, min_length=1, max_length=50)

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
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("zona_horaria debe ser un identificador IANA vÃ¡lido") from error
        return value

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Debe indicar al menos un campo")
        for field in ("codigo", "nombre", "zona_horaria"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} no admite null")
        return self


class CompanyStateUpdateRequest(BaseModel):
    """Cambio explÃ­cito de estado sin modificar otras relaciones SaaS."""

    model_config = ConfigDict(extra="forbid")

    estado: CompanyState


class CompanyPaginationData(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class CompanyListResponse(BaseModel):
    success: Literal[True] = True
    data: list[CompanyData]
    pagination: CompanyPaginationData


class CompanyDetailResponse(BaseModel):
    success: Literal[True] = True
    data: CompanyData


class CompanyUpdateResponse(CompanyDetailResponse):
    message: str
