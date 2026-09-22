"""Endpoint administrativo de solo lectura CU29."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_inventory_report import InventoryReportData, InventoryReportFilters, InventoryReportResponse
from app.schemas.admin_report_ai import ReportAIAnalysisData, ReportAIAnalysisResponse
from app.services.admin_inventory_report import AdminInventoryReportService, InvalidInventoryReportFilter
from app.services.report_ai_service import GEMINI_MODEL_LABEL, ReportAIService, ReportAIUnavailableError


router = APIRouter(prefix="/api/admin/inventory-report", tags=["Reporte de inventario"])


@router.get("", response_model=InventoryReportResponse, responses={
    **COMMON_ERROR_RESPONSES,
    422: {"description": "Filtros invalidos"},
    500: {"description": "Error de consulta"},
})
def inventory_report(
    administrator: AdminDependency,
    filters: Annotated[InventoryReportFilters, Query()],
    db: Session = Depends(get_db),
) -> InventoryReportResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data = AdminInventoryReportService(db).report(filters)
    except InvalidInventoryReportFilter as exc:
        return JSONResponse(status_code=422, content={"success": False, "message": str(exc)})
    except SQLAlchemyError:
        return JSONResponse(status_code=500, content={
            "success": False, "message": "No fue posible consultar el reporte de inventario",
        })
    return InventoryReportResponse(data=data)


@router.post(
    "/ai-analysis",
    response_model=ReportAIAnalysisResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_502_BAD_GATEWAY: {"description": "El servicio de IA no esta disponible"},
    },
)
def inventory_report_ai_analysis(
    administrator: AdminDependency,
    data: InventoryReportData,
    pregunta: Annotated[str | None, Query(max_length=500)] = None,
) -> ReportAIAnalysisResponse | JSONResponse:
    """Analiza con IA los datos de inventario ya calculados por el dashboard; no vuelve a consultarlos.

    `pregunta` es opcional: la consulta que el administrador dicto por voz y que el
    frontend ya convirtio a texto (reconocimiento de voz a texto en el navegador).
    """
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        analysis = ReportAIService().analyze_inventory(data, pregunta)
    except ReportAIUnavailableError as exc:
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "success": False, "message": str(exc),
        })
    return ReportAIAnalysisResponse(data=ReportAIAnalysisData(
        analisis=analysis, modelo=GEMINI_MODEL_LABEL, generado_en=datetime.now(timezone.utc),
    ))
