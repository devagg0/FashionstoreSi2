"""Endpoint administrativo CU28."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_report_ai import ReportAIAnalysisData, ReportAIAnalysisResponse
from app.schemas.admin_sales_report import SalesReportData, SalesReportFilters, SalesReportResponse
from app.services.admin_sales_report import AdminSalesReportService, InvalidSalesReportFilter
from app.services.report_ai_service import GEMINI_MODEL_LABEL, ReportAIService, ReportAIUnavailableError


router = APIRouter(prefix="/api/admin/sales-report", tags=["Reporte de ventas"])


@router.get("", response_model=SalesReportResponse, responses=COMMON_ERROR_RESPONSES)
def sales_report(
    administrator: AdminDependency,
    filters: Annotated[SalesReportFilters, Query()],
    db: Session = Depends(get_db),
) -> SalesReportResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data = AdminSalesReportService(db).report(filters)
    except InvalidSalesReportFilter as exc:
        return JSONResponse(status_code=422, content={"success": False, "message": str(exc)})
    except SQLAlchemyError:
        return JSONResponse(status_code=500, content={
            "success": False, "message": "No fue posible consultar el reporte de ventas",
        })
    return SalesReportResponse(data=data)


@router.post(
    "/ai-analysis",
    response_model=ReportAIAnalysisResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_502_BAD_GATEWAY: {"description": "El servicio de IA no esta disponible"},
    },
)
def sales_report_ai_analysis(
    administrator: AdminDependency,
    data: SalesReportData,
    pregunta: Annotated[str | None, Query(max_length=500)] = None,
) -> ReportAIAnalysisResponse | JSONResponse:
    """Analiza con IA los datos de ventas ya calculados por el dashboard; no vuelve a consultarlos.

    `pregunta` es opcional: la consulta que el administrador dicto por voz y que el
    frontend ya convirtio a texto (reconocimiento de voz a texto en el navegador).
    """
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        analysis = ReportAIService().analyze_sales(data, pregunta)
    except ReportAIUnavailableError as exc:
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "success": False, "message": str(exc),
        })
    return ReportAIAnalysisResponse(data=ReportAIAnalysisData(
        analisis=analysis, modelo=GEMINI_MODEL_LABEL, generado_en=datetime.now(timezone.utc),
    ))
