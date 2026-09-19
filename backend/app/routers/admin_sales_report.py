"""Endpoint administrativo CU28."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_sales_report import SalesReportFilters, SalesReportResponse
from app.services.admin_sales_report import AdminSalesReportService, InvalidSalesReportFilter


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
