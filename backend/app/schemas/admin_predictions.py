"""Esquemas Pydantic para el CU22: Predicciones de demanda con Machine Learning."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ModelEvaluationMetrics(BaseModel):
    """Métricas reales de evaluación calculadas sobre el conjunto de test (sin fuga de datos)."""
    mae: float = Field(..., description="Error Absoluto Medio (unidades)")
    rmse: float = Field(..., description="Raíz del Error Cuadrático Medio")
    r2: float = Field(..., description="Coeficiente de determinación R²")


class ModelInfoResponse(BaseModel):
    """Metadatos del modelo supervisado entrenado."""
    algoritmo: str
    descripcion: str
    variables: List[str]
    total_variables: int
    dataset_size: int
    train_size: int
    test_size: int
    metricas: ModelEvaluationMetrics
    es_experimental: bool = True
    nota_metodologica: str
    entrenado_en: Optional[str] = None


class PredictionFilterItem(BaseModel):
    """Elemento para selectores de sucursal y producto."""
    id: int
    nombre: str
    codigo: Optional[str] = None
    extra: Optional[str] = None


class PredictionFiltersResponse(BaseModel):
    """Opciones de filtrado para generar predicciones."""
    productos: List[PredictionFilterItem]
    sucursales: List[PredictionFilterItem]
    horizontes_disponibles: List[int] = [7, 15, 30]


class PredictionRequest(BaseModel):
    """Solicitud de predicción de demanda supervisada."""
    id_producto: int = Field(..., description="ID del producto de la empresa")
    id_sucursal: int = Field(..., description="ID de la sucursal de la empresa")
    horizonte_dias: int = Field(
        ...,
        description="Horizonte de predicción en días (7, 15 o 30)",
    )


class HistoricalContext(BaseModel):
    """Variables históricas reales extraídas de la base de datos PostgreSQL."""
    ventas_ultimos_7d: int
    ventas_ultimos_14d: int
    ventas_ultimos_30d: int
    stock_actual: int
    stock_minimo: int
    precio_unitario: float
    seccion: str
    datos_suficientes: bool
    mensaje_suficiencia: str


class DailyTrendPoint(BaseModel):
    """Punto en la serie temporal para gráficos comparativos."""
    fecha: str
    dia_etiqueta: str
    tipo: str = Field(..., description="'REAL' o 'PROYECTADO'")
    unidades: float


class PredictionResult(BaseModel):
    """Resultado del modelo de aprendizaje supervisado."""
    demanda_estimada: int
    demanda_estimada_raw: float
    rango_minimo: int
    rango_maximo: int
    unidades_diarias_promedio: float
    cobertura_stock_dias: Optional[float] = None
    riesgo_desabastecimiento: bool
    nivel_riesgo: str = Field(..., description="BAJO, MEDIO, ALTO o CRITICO")
    confianza_estimacion: str = Field(..., description="ALTA, MEDIA o EXPERIMENTAL")
    explicacion: str


class PredictionResponse(BaseModel):
    """Respuesta completa de predicción CU22."""
    success: bool = True
    id_producto: int
    producto_nombre: str
    id_sucursal: int
    sucursal_nombre: str
    horizonte_dias: int
    prediccion: PredictionResult
    historico: HistoricalContext
    serie_temporal: List[DailyTrendPoint]
    modelo: ModelInfoResponse
    disclaimer: str

