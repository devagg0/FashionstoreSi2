"""Contratos de la respuesta de analisis con IA, comunes a CU28, CU29 y CU30."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ReportAIAnalysisData(BaseModel):
    analisis: str
    modelo: str
    generado_en: datetime


class ReportAIAnalysisResponse(BaseModel):
    success: Literal[True] = True
    data: ReportAIAnalysisData
    message: str = "Analisis generado correctamente"
