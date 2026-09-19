"""Endpoint administrativo de solo lectura CU29."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_inventory_report import InventoryReportFilters, InventoryReportResponse
from app.services.admin_inventory_report import AdminInventoryReportService, InvalidInventoryReportFilter


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
