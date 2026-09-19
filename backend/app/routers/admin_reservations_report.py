"""Endpoint administrativo de solo lectura CU30."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_reservations_report import ReservationsReportFilters, ReservationsReportResponse
from app.services.admin_reservations_report import AdminReservationsReportService, InvalidReservationsReportFilter


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
