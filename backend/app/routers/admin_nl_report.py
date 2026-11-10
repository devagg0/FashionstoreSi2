"""Endpoint administrativo CU20 y CU21: reportes empresariales con IA, historial y exportación."""

import io
import logging
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.deepseek import DeepSeekError
from app.models.generated_report import GeneratedReport
from app.models.user import User
from app.routers.admin_users import AdminDependency, COMMON_ERROR_RESPONSES
from app.schemas.admin_nl_report import (
    GeneratedReportDetail,
    GeneratedReportDetailResponse,
    GeneratedReportHistoryResponse,
    GeneratedReportSummary,
    NaturalLanguageReportData,
    NaturalLanguageReportRequest,
    NaturalLanguageReportResponse,
)
from app.services.admin_nl_report import NaturalLanguageReportService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/reports", tags=["Reportes con IA CU20/CU21"])


def _generate_excel_bytes(
    titulo: str,
    consulta: str,
    resumen: str | None,
    kpis: list,
    tabla: dict | None,
    filtros: dict | None,
) -> bytes:
    wb = openpyxl.Workbook()
    ws_summary = wb.active
    ws_summary.title = "Resumen"

    title_font = Font(name="Calibri", size=15, bold=True, color="1F2937")
    subtitle_font = Font(name="Calibri", size=10, italic=True, color="6B7280")
    header_fill = PatternFill(start_color="C1563A", end_color="C1563A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    kpi_fill = PatternFill(start_color="F5EFEB", end_color="F5EFEB", fill_type="solid")
    kpi_val_font = Font(name="Calibri", size=13, bold=True, color="1F2937")
    kpi_lbl_font = Font(name="Calibri", size=9, bold=True, color="6B7280")
    border_thin = Border(
        left=Side(style="thin", color="E5E7EB"),
        right=Side(style="thin", color="E5E7EB"),
        top=Side(style="thin", color="E5E7EB"),
        bottom=Side(style="thin", color="E5E7EB"),
    )

    ws_summary.append(["FASHIONSTORE · REPORTE EMPRESARIAL"])
    ws_summary.cell(row=1, column=1).font = title_font
    ws_summary.append([titulo])
    ws_summary.cell(row=2, column=1).font = Font(name="Calibri", size=13, bold=True, color="C1563A")

    if consulta:
        ws_summary.append([f"Consulta: {consulta}"])
        ws_summary.cell(row=3, column=1).font = subtitle_font
    ws_summary.append([f"Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    ws_summary.cell(row=4, column=1).font = subtitle_font
    ws_summary.append([])

    if resumen:
        ws_summary.append(["Resumen Ejecutivo (IA):"])
        ws_summary.cell(row=ws_summary.max_row, column=1).font = Font(name="Calibri", size=11, bold=True, color="1F2937")
        ws_summary.append([resumen])
        ws_summary.cell(row=ws_summary.max_row, column=1).alignment = Alignment(wrap_text=True)
        ws_summary.append([])

    if kpis:
        ws_summary.append(["Indicadores Clave (KPIs):"])
        ws_summary.cell(row=ws_summary.max_row, column=1).font = Font(name="Calibri", size=11, bold=True, color="1F2937")
        start_row = ws_summary.max_row + 1
        for i, k in enumerate(kpis):
            lbl = k.get("etiqueta") if isinstance(k, dict) else getattr(k, "etiqueta", "")
            val = k.get("valor") if isinstance(k, dict) else getattr(k, "valor", "")
            ws_summary.cell(row=start_row, column=i + 1, value=lbl).font = kpi_lbl_font
            ws_summary.cell(row=start_row + 1, column=i + 1, value=str(val)).font = kpi_val_font
            ws_summary.cell(row=start_row, column=i + 1).fill = kpi_fill
            ws_summary.cell(row=start_row + 1, column=i + 1).fill = kpi_fill
            ws_summary.cell(row=start_row, column=i + 1).border = border_thin
            ws_summary.cell(row=start_row + 1, column=i + 1).border = border_thin

    if tabla and tabla.get("columnas") and tabla.get("filas"):
        ws_data = wb.create_sheet(title="Detalle")
        cols = tabla["columnas"]
        headers = [c.get("etiqueta", "") if isinstance(c, dict) else getattr(c, "etiqueta", "") for c in cols]
        ws_data.append(headers)
        for col_num in range(1, len(headers) + 1):
            cell = ws_data.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for r in tabla["filas"]:
            ws_data.append([
                r.get(c.get("clave", "") if isinstance(c, dict) else getattr(c, "clave", ""), "")
                for c in cols
            ])

        for row in ws_data.iter_rows(min_row=2, max_row=ws_data.max_row, min_col=1, max_col=len(headers)):
            for cell in row:
                cell.border = border_thin

        for col in ws_data.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws_data.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class DirectExcelExportRequest(BaseModel):
    titulo: str
    consulta: str = ""
    resumen: str | None = None
    kpis: list[dict] = []
    tabla: dict | None = None
    filtros: dict | None = None


@router.post(
    "/natural-language",
    response_model=NaturalLanguageReportResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_502_BAD_GATEWAY: {"description": "El servicio de IA no esta disponible"},
    },
)
def natural_language_report(
    administrator: AdminDependency,
    payload: NaturalLanguageReportRequest,
    db: Session = Depends(get_db),
) -> NaturalLanguageReportResponse | JSONResponse:
    """Interpreta la solicitud con IA, responde y guarda automáticamente en el historial (CU20/CU21)."""
    if isinstance(administrator, JSONResponse):
        return administrator

    company_id = getattr(administrator, "id_empresa", None) or getattr(db, "info", {}).get("empresa_id")
    if not company_id:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={
            "success": False, "message": "No se pudo determinar la empresa del administrador",
        })

    from app.PK07.CU07_ConsultarPlanLimites.service import (
        FeatureNotEnabledError,
        NoActiveSubscriptionError,
        SaasPlanLimitsService,
    )

    try:
        SaasPlanLimitsService(db).validate_feature_enabled(company_id, "REPORTES_IA")
    except (NoActiveSubscriptionError, FeatureNotEnabledError) as exc:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={
            "success": False, "message": str(exc),
        })

    try:
        data = NaturalLanguageReportService(db).generate(payload.consulta, int(company_id))
    except DeepSeekError:
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "success": False, "message": "No fue posible interpretar la solicitud con el servicio de IA",
        })
    except SQLAlchemyError:
        logger.exception("Error de base de datos en CU20")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={
            "success": False, "message": "No fue posible consultar el reporte solicitado",
        })

    # Guardado automático en PostgreSQL para CU21 cuando el estado es OK
    report_id = None
    if data.estado == "OK":
        try:
            user_id = getattr(administrator, "id_usuario", None) or 1
            record = GeneratedReport(
                empresa_id=int(company_id),
                id_usuario=int(user_id),
                tipo=data.tipo,
                titulo=data.titulo,
                consulta=payload.consulta,
                filtros_aplicados=data.filtros_aplicados or {},
                resultado=data.model_dump(mode="json"),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            report_id = record.id_reporte
        except Exception:
            logger.exception("Error al guardar reporte en historial CU21")
            db.rollback()

    return NaturalLanguageReportResponse(data=data, id_reporte=report_id)


@router.get(
    "/history",
    response_model=GeneratedReportHistoryResponse,
    responses=COMMON_ERROR_RESPONSES,
)
def list_report_history(
    administrator: AdminDependency,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> GeneratedReportHistoryResponse | JSONResponse:
    """Lista el historial de reportes generados para la empresa (CU21)."""
    if isinstance(administrator, JSONResponse):
        return administrator

    company_id = getattr(administrator, "id_empresa", None) or getattr(db, "info", {}).get("empresa_id")
    if not company_id:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={
            "success": False, "message": "No se pudo determinar la empresa del administrador",
        })

    stmt = (
        select(GeneratedReport, User)
        .outerjoin(User, GeneratedReport.id_usuario == User.id_usuario)
        .where(GeneratedReport.empresa_id == int(company_id))
        .order_by(GeneratedReport.creado_en.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    items = [
        GeneratedReportSummary(
            id_reporte=rep.id_reporte,
            tipo=rep.tipo,
            titulo=rep.titulo,
            consulta=rep.consulta,
            filtros_aplicados=rep.filtros_aplicados or {},
            creado_en=rep.creado_en,
            nombre_usuario=f"{user.nombre} {user.apellido}".strip() if user else None,
        )
        for rep, user in rows
    ]
    return GeneratedReportHistoryResponse(data=items, total=len(items))


@router.get(
    "/history/{report_id}",
    response_model=GeneratedReportDetailResponse,
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"description": "Reporte no encontrado"},
    },
)
def get_saved_report_detail(
    report_id: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> GeneratedReportDetailResponse | JSONResponse:
    """Consulta el detalle y datos completos de un reporte guardado (CU21)."""
    if isinstance(administrator, JSONResponse):
        return administrator

    company_id = getattr(administrator, "id_empresa", None) or getattr(db, "info", {}).get("empresa_id")
    if not company_id:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={
            "success": False, "message": "No se pudo determinar la empresa del administrador",
        })

    stmt = (
        select(GeneratedReport, User)
        .outerjoin(User, GeneratedReport.id_usuario == User.id_usuario)
        .where(
            GeneratedReport.id_reporte == report_id,
            GeneratedReport.empresa_id == int(company_id),
        )
    )
    row = db.execute(stmt).first()
    if not row:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={
            "success": False, "message": "Reporte no encontrado o no pertenece a tu empresa",
        })

    rep, user = row
    detail = GeneratedReportDetail(
        id_reporte=rep.id_reporte,
        tipo=rep.tipo,
        titulo=rep.titulo,
        consulta=rep.consulta,
        filtros_aplicados=rep.filtros_aplicados or {},
        creado_en=rep.creado_en,
        nombre_usuario=f"{user.nombre} {user.apellido}".strip() if user else None,
        resultado=NaturalLanguageReportData.model_validate(rep.resultado),
    )
    return GeneratedReportDetailResponse(data=detail)


@router.get("/history/{report_id}/export/excel")
def export_saved_report_excel(
    report_id: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
):
    """Exporta un reporte guardado en formato Excel .xlsx (CU21)."""
    if isinstance(administrator, JSONResponse):
        return administrator

    company_id = getattr(administrator, "id_empresa", None) or getattr(db, "info", {}).get("empresa_id")
    if not company_id:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={
            "success": False, "message": "No se pudo determinar la empresa del administrador",
        })

    rep = db.scalar(
        select(GeneratedReport).where(
            GeneratedReport.id_reporte == report_id,
            GeneratedReport.empresa_id == int(company_id),
        )
    )
    if not rep:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={
            "success": False, "message": "Reporte no encontrado",
        })

    res = rep.resultado or {}
    excel_bytes = _generate_excel_bytes(
        titulo=rep.titulo,
        consulta=rep.consulta,
        resumen=res.get("resumen"),
        kpis=res.get("kpis", []),
        tabla=res.get("tabla"),
        filtros=rep.filtros_aplicados,
    )
    slug = rep.titulo.lower().replace(" ", "_").replace("/", "_")
    timestamp = rep.creado_en.strftime("%Y%m%d_%H%M")
    filename = f"{slug}_{timestamp}.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/excel")
def export_direct_report_excel(
    payload: DirectExcelExportRequest,
    administrator: AdminDependency,
):
    """Exporta directamente un reporte en formato Excel .xlsx (CU21)."""
    if isinstance(administrator, JSONResponse):
        return administrator

    excel_bytes = _generate_excel_bytes(
        titulo=payload.titulo,
        consulta=payload.consulta,
        resumen=payload.resumen,
        kpis=payload.kpis,
        tabla=payload.tabla,
        filtros=payload.filtros,
    )
    slug = payload.titulo.lower().replace(" ", "_").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{slug}_{timestamp}.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
