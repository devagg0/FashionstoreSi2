"""Contratos de CU20: reportes empresariales mediante lenguaje natural."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ReportType = Literal["VENTAS", "STOCK", "DEVOLUCIONES", "RESERVAS", "NO_SOPORTADO", "AMBIGUO"]
Visualization = Literal["bar", "line", "pie", "table"]
ResultStatus = Literal["OK", "VACIO", "AMBIGUO", "NO_SOPORTADO"]


class NaturalLanguageReportRequest(BaseModel):
    consulta: str = Field(min_length=3, max_length=500)

    @field_validator("consulta")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("La consulta es demasiado corta")
        return value


class ReportIntent(BaseModel):
    """Interpretacion estructurada de la solicitud; la IA nunca genera SQL."""

    tipo: ReportType
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    sucursal: str | None = Field(default=None, max_length=100)
    categoria: str | None = Field(default=None, max_length=100)
    producto: str | None = Field(default=None, max_length=150)
    canal: Literal["DIGITAL", "PRESENCIAL"] | None = None
    estado: str | None = Field(default=None, max_length=30)
    tipo_solicitud: Literal["CAMBIO", "DEVOLUCION", "CANCELACION"] | None = None
    agrupacion: str | None = Field(default=None, max_length=30)
    visualizacion: Visualization = "bar"
    aclaracion: str | None = Field(default=None, max_length=300)


class ReportKpi(BaseModel):
    etiqueta: str
    valor: str
    unidad: str | None = None


class ReportColumn(BaseModel):
    clave: str
    etiqueta: str
    tipo: Literal["texto", "numero", "moneda"] = "texto"


class ReportTable(BaseModel):
    columnas: list[ReportColumn]
    filas: list[dict[str, Any]]
    total_filas: int
    truncada: bool = False


class ReportChartPoint(BaseModel):
    etiqueta: str
    valor: float


class ReportChart(BaseModel):
    tipo: Visualization
    titulo: str
    unidad: str | None = None
    puntos: list[ReportChartPoint]


class NaturalLanguageReportData(BaseModel):
    estado: ResultStatus
    tipo: ReportType
    titulo: str
    mensaje: str | None = None
    filtros_aplicados: dict[str, str] = {}
    kpis: list[ReportKpi] = []
    tabla: ReportTable | None = None
    grafico: ReportChart | None = None
    resumen: str | None = None
    modelo: str | None = None
    generado_en: datetime


class NaturalLanguageReportResponse(BaseModel):
    success: Literal[True] = True
    data: NaturalLanguageReportData
    id_reporte: int | None = None
    message: str = "Reporte generado correctamente"


class GeneratedReportSummary(BaseModel):
    id_reporte: int
    tipo: ReportType
    titulo: str
    consulta: str
    filtros_aplicados: dict[str, str] = {}
    creado_en: datetime
    nombre_usuario: str | None = None


class GeneratedReportDetail(BaseModel):
    id_reporte: int
    tipo: ReportType
    titulo: str
    consulta: str
    filtros_aplicados: dict[str, str] = {}
    creado_en: datetime
    nombre_usuario: str | None = None
    resultado: NaturalLanguageReportData


class GeneratedReportHistoryResponse(BaseModel):
    success: Literal[True] = True
    data: list[GeneratedReportSummary]
    total: int


class GeneratedReportDetailResponse(BaseModel):
    success: Literal[True] = True
    data: GeneratedReportDetail
