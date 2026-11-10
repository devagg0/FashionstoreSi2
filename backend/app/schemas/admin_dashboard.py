"""Esquemas Pydantic para el CU24: Dashboard Analítico Inteligente."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DashboardFilterItem(BaseModel):
    id: int
    nombre: str
    extra: Optional[str] = None


class DashboardFiltersResponse(BaseModel):
    sucursales: List[DashboardFilterItem]
    categorias: List[DashboardFilterItem]
    periodos_disponibles: List[int] = [7, 15, 30, 60, 90]


class DashboardAnalyticsRequest(BaseModel):
    dias_periodo: Optional[int] = Field(default=30, ge=7, le=365)
    fecha_desde: Optional[str] = None
    fecha_hasta: Optional[str] = None
    id_sucursal: Optional[int] = None
    id_categoria: Optional[int] = None


class KpiOverview(BaseModel):
    total_ventas: int
    ingresos_totales: float
    ticket_promedio: float
    unidades_vendidas: int
    stock_disponible: int
    total_reservas: int
    reservas_atendidas: int
    total_devoluciones: int
    tasa_devolucion_pct: float


class DailyMetricPoint(BaseModel):
    fecha: str
    dia_etiqueta: str
    unidades: int
    ingresos: float


class CategoryDistributionItem(BaseModel):
    categoria: str
    unidades: int
    ingresos: float
    porcentaje: float


class ChannelDistributionItem(BaseModel):
    canal: str
    unidades: int
    ingresos: float
    porcentaje: float


class SectionDistributionItem(BaseModel):
    seccion: str
    unidades: int
    ingresos: float
    porcentaje: float


class PredictionRiskItem(BaseModel):
    id_producto: int
    producto_nombre: str
    stock_actual: int
    demanda_estimada_15d: int
    cobertura_dias: Optional[float] = None
    nivel_riesgo: str


class PredictionsSummary(BaseModel):
    algoritmo: str
    mae: float
    rmse: float
    r2: float
    productos_con_riesgo_stock: int
    items_riesgo: List[PredictionRiskItem]
    disclaimer: str


class PatternSegmentSummary(BaseModel):
    id_cluster: int
    nombre: str
    color: str
    total_productos: int
    porcentaje_catalogo: float
    unidades_promedio: float


class PatternsSummary(BaseModel):
    algoritmo: str
    silhouette_score: float
    calidad_agrupamiento: str
    n_clusters: int
    segmentos: List[PatternSegmentSummary]
    disclaimer: str


class RecentReportItem(BaseModel):
    id_reporte: int
    tipo: str
    titulo: str
    creado_en: str
    consulta: str


class AiReportsSummary(BaseModel):
    total_reportes_guardados: int
    ultimos_reportes: List[RecentReportItem]


class DashboardAnalyticsResponse(BaseModel):
    success: bool = True
    filtros_aplicados: Dict[str, Any]
    kpis: KpiOverview
    tendencia_diaria: List[DailyMetricPoint]
    distribucion_categorias: List[CategoryDistributionItem]
    distribucion_canales: List[ChannelDistributionItem]
    distribucion_secciones: List[SectionDistributionItem]
    ml_predicciones: PredictionsSummary
    ml_patrones: PatternsSummary
    reportes_ia: AiReportsSummary

