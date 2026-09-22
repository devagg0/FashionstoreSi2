"""Endpoint administrativo de solo lectura CU30."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_report_ai import ReportAIAnalysisData, ReportAIAnalysisResponse
from app.schemas.admin_reservations_report import (
    ReservationsReportData,
    ReservationsReportFilters,
    ReservationsReportResponse,
)
from app.services.admin_reservations_report import AdminReservationsReportService, InvalidReservationsReportFilter
from app.services.report_ai_service import GEMINI_MODEL_LABEL, ReportAIService, ReportAIUnavailableError


router = APIRouter(prefix="/api/admin/reservations-report", tags=["Reporte de reservas"])


@router.get("", response_model=ReservationsReportResponse, responses=COMMON_ERROR_RESPONSES)
def reservations_report(
    administrator: AdminDependency,
    filters: Annotated[ReservationsReportFilters, Query()],
    db: Session = Depends(get_db),
) -> ReservationsReportResponse | JSONResponse:
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        data = AdminReservationsReportService(db).report(filters)
    except InvalidReservationsReportFilter as exc:
        return JSONResponse(status_code=422, content={"success": False, "message": str(exc)})
    except SQLAlchemyError:
        return JSONResponse(status_code=500, content={
            "success": False, "message": "No fue posible consultar el reporte de reservas",
        })
    return ReservationsReportResponse(data=data)


@router.post(
    "/ai-analysis",
    response_model=ReportAIAnalysisResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_502_BAD_GATEWAY: {"description": "El servicio de IA no esta disponible"},
    },
)
def reservations_report_ai_analysis(
    administrator: AdminDependency,
    data: ReservationsReportData,
    pregunta: Annotated[str | None, Query(max_length=500)] = None,
) -> ReportAIAnalysisResponse | JSONResponse:
    """Analiza con IA los datos de reservas ya calculados por el dashboard; no vuelve a consultarlos.

    `pregunta` es opcional: la consulta que el administrador dicto por voz y que el
    frontend ya convirtio a texto (reconocimiento de voz a texto en el navegador).
    """
    if isinstance(administrator, JSONResponse):
        return administrator
    try:
        analysis = ReportAIService().analyze_reservations(data, pregunta)
    except ReportAIUnavailableError as exc:
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "success": False, "message": str(exc),
        })
    return ReportAIAnalysisResponse(data=ReportAIAnalysisData(
        analisis=analysis, modelo=GEMINI_MODEL_LABEL, generado_en=datetime.now(timezone.utc),
    ))
