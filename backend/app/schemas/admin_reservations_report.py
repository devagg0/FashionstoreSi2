"""Contratos de lectura CU30; cantidades historicas, no stock actual."""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ReservationState = Literal["PENDIENTE", "CONFIRMADA", "ATENDIDA", "CANCELADA", "EXPIRADA"]
STATES = ("PENDIENTE", "CONFIRMADA", "ATENDIDA", "CANCELADA", "EXPIRADA")


class ReservationsReportFilters(BaseModel):
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    tipo_fecha: Literal["CREACION", "PROGRAMADA", "ATENCION"] = "CREACION"
    periodo: Literal["DIA", "SEMANA", "MES"] = "DIA"
    id_sucursal: int | None = Field(default=None, gt=0)
    estado: ReservationState | None = None
    id_categoria: int | None = Field(default=None, gt=0)
    id_producto: int | None = Field(default=None, gt=0)

    @field_validator("fecha_desde", "fecha_hasta", mode="before")
    @classmethod
    def validate_date_format(cls, value):
        if value is not None and not isinstance(value, date):
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("La fecha debe tener formato YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def validate_range(self):
        if self.fecha_desde and self.fecha_hasta and self.fecha_desde > self.fecha_hasta:
            raise ValueError("fecha_desde debe ser menor o igual a fecha_hasta")
        return self


class ReservationTotals(BaseModel):
    total_reservas: int
    unidades_reservadas: int


class ReservationsReportKPIs(ReservationTotals):
    reservas_pendientes: int
    reservas_confirmadas: int
    reservas_atendidas: int
    reservas_canceladas: int
    reservas_expiradas: int
    clientes_con_reservas: int


class StateBreakdown(ReservationTotals):
    estado: ReservationState


class BranchBreakdown(ReservationTotals):
    id_sucursal: int
    nombre_sucursal: str
    clientes_con_reservas: int


class PeriodBreakdown(ReservationTotals):
    inicio_periodo: date


class ProductBreakdown(ReservationTotals):
    id_producto: int
    nombre_producto: str


class CategoryBreakdown(ReservationTotals):
    id_categoria: int
    nombre_categoria: str


class ReportWarnings(BaseModel):
    reservas_vencidas_sin_actualizar: int


class ReservationsReportData(BaseModel):
    zona_horaria: Literal["America/La_Paz"] = "America/La_Paz"
    generado_en: datetime
    criterio_estado: Literal["PERSISTIDO"] = "PERSISTIDO"
    filtros: ReservationsReportFilters
    kpis: ReservationsReportKPIs
    por_estado: list[StateBreakdown]
    por_sucursal: list[BranchBreakdown]
    serie_periodica: list[PeriodBreakdown]
    productos_mas_reservados: list[ProductBreakdown]
    categorias_mas_reservadas: list[CategoryBreakdown]
    advertencias: ReportWarnings


class ReservationsReportResponse(BaseModel):
    success: Literal[True] = True
    data: ReservationsReportData
    message: str = "Reporte de reservas consultado correctamente"
