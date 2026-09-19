"""Contratos CU28; todos los importes se expresan en BOB con dos decimales."""

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer, field_validator, model_validator


Money = Annotated[
    Decimal,
    PlainSerializer(
        lambda value: format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f"),
        return_type=str,
        when_used="json",
    ),
]
Channel = Literal["PRESENCIAL", "DIGITAL"]


class SalesReportFilters(BaseModel):
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    id_sucursal: int | None = Field(default=None, gt=0)
    canal: Channel | None = None
    id_categoria: int | None = Field(default=None, gt=0)

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


class SalesReportKPIs(BaseModel):
    cantidad_ventas: int
    importe_antes_descuentos: Money
    descuentos: Money
    importe_vendido: Money
    ticket_promedio: Money | None
    unidades_vendidas: int
    clientes_identificados: int
    ventas_sin_cliente: int


class ChannelBreakdown(SalesReportKPIs):
    canal: Channel


class BranchBreakdown(SalesReportKPIs):
    id_sucursal: int
    nombre_sucursal: str


class DailyBreakdown(SalesReportKPIs):
    fecha: date


class ProductBreakdown(BaseModel):
    id_producto: int
    nombre_producto: str
    unidades_vendidas: int
    importe_antes_descuentos: Money
    descuentos: Money
    importe_vendido: Money


class SalesReportData(BaseModel):
    moneda: Literal["BOB"] = "BOB"
    zona_horaria: Literal["America/La_Paz"] = "America/La_Paz"
    kpis: SalesReportKPIs
    por_canal: list[ChannelBreakdown]
    por_sucursal: list[BranchBreakdown]
    productos_mas_vendidos: list[ProductBreakdown]
    serie_diaria: list[DailyBreakdown]


class SalesReportResponse(BaseModel):
    success: Literal[True] = True
    data: SalesReportData
    message: str = "Reporte de ventas consultado correctamente"
