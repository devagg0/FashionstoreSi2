"""Esquemas Pydantic para el CU23: Análisis de Patrones de Comportamiento No Supervisado."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PatternModelMetrics(BaseModel):
    """Métricas de evaluación del modelo de clustering."""
    silhouette_score: float = Field(..., description="Coeficiente de Silueta (-1 a 1)")
    inercia: float = Field(..., description="Suma de distancias al cuadrado a los centroides")


class PatternModelInfoResponse(BaseModel):
    """Metadatos del modelo no supervisado K-Means referencial."""
    algoritmo: str
    tipo_aprendizaje: str = "No supervisado"
    descripcion: str
    variables: List[str]
    n_clusters: int
    metricas: PatternModelMetrics
    es_experimental: bool = True
    nota_metodologica: str


class PatternFilterOption(BaseModel):
    """Opción para selectores de sucursal o categoría."""
    id: int
    nombre: str
    extra: Optional[str] = None


class PatternFiltersResponse(BaseModel):
    """Opciones de filtrado para el análisis de patrones."""
    sucursales: List[PatternFilterOption]
    categorias: List[PatternFilterOption]
    periodos_sugeridos_dias: List[int] = [30, 60, 90, 180]


class PatternAnalysisRequest(BaseModel):
    """Solicitud de análisis de patrones no supervisado."""
    dias_periodo: Optional[int] = Field(default=30, ge=7, le=365, description="Días hacia atrás")
    fecha_desde: Optional[str] = None
    fecha_hasta: Optional[str] = None
    id_sucursal: Optional[int] = Field(default=None, description="Sucursal específica o None para todas")
    id_categoria: Optional[int] = Field(default=None, description="Categoría específica o None para todas")


class ClusterAverages(BaseModel):
    """Medias reales de cada variable dentro del cluster."""
    unidades_vendidas: float
    ingresos_totales: float
    frecuencia_ventas: float
    precio_unitario: float
    stock_actual: float
    ratio_rotacion: float


class PatternSegment(BaseModel):
    """Segmento comercial descubierto empíricamente por K-Means."""
    id_cluster: int
    nombre: str
    descripcion: str
    estrategia: str
    color: str
    badge_class: str
    total_productos: int
    porcentaje_catalogo: float
    promedios: ClusterAverages


class ProductPatternItem(BaseModel):
    """Datos comerciales de una prenda con su clasificación de cluster."""
    id_producto: int
    nombre: str
    categoria_nombre: str
    seccion: str
    precio_unitario: float
    unidades_vendidas: int
    ingresos_totales: float
    frecuencia_ventas: int
    stock_actual: int
    ratio_rotacion: float
    id_cluster: int = 0
    cluster_nombre: str = "Sin Clasificar"
    cluster_color: str = "#64748b"
    cluster_badge: str = "badge-default"


class PatternAnalysisResponse(BaseModel):
    """Respuesta completa del análisis de patrones CU23."""
    success: bool = True
    datos_suficientes: bool
    mensaje: str
    filtros_aplicados: Dict[str, Any]
    total_productos_analizados: int
    total_unidades_vendidas: int
    total_ingresos_facturados: float
    n_clusters: int
    calidad_agrupamiento: str
    metricas: PatternModelMetrics
    segmentos: List[PatternSegment]
    productos: List[ProductPatternItem]
    modelo_referencial: PatternModelInfoResponse
    disclaimer: str

