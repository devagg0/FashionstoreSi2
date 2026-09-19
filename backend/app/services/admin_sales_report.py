"""Reglas de consulta CU28; no modifica ventas ni sus relaciones."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.admin_sales_report import AdminSalesReportRepository
from app.schemas.admin_sales_report import SalesReportData, SalesReportFilters


class InvalidSalesReportFilter(ValueError):
    pass


class AdminSalesReportService:
    def __init__(self, db: Session):
        self.repository = AdminSalesReportRepository(db)

    def report(self, filters: SalesReportFilters) -> SalesReportData:
        zone = ZoneInfo("America/La_Paz")
        try:
            start = (
                datetime.combine(filters.fecha_desde, time.min, zone)
                .astimezone(timezone.utc).replace(tzinfo=None)
                if filters.fecha_desde else None
            )
            end = (
                datetime.combine(filters.fecha_hasta + timedelta(days=1), time.min, zone)
                .astimezone(timezone.utc).replace(tzinfo=None)
                if filters.fecha_hasta else None
            )
        except (ValueError, OverflowError) as exc:
            raise InvalidSalesReportFilter("Rango de fechas fuera de los limites soportados") from exc
        if filters.id_sucursal is not None and not self.repository.branch_exists(filters.id_sucursal):
            raise InvalidSalesReportFilter("Sucursal inexistente")
        if filters.id_categoria is not None and not self.repository.category_exists(filters.id_categoria):
            raise InvalidSalesReportFilter("Categoria inexistente")

        kpis, channels, branches, products, daily = self.repository.report(filters, start, end)
        return SalesReportData(
            kpis=self._with_average(kpis),
            por_canal=[self._with_average(row) for row in channels],
            por_sucursal=[self._with_average(row) for row in branches],
            productos_mas_vendidos=products,
            serie_diaria=[self._with_average(row) for row in daily],
        )

    @staticmethod
    def _with_average(row):
        return {
            **row,
            "ticket_promedio": (
                row["importe_vendido"] / row["cantidad_ventas"]
                if row["cantidad_ventas"] else None
            ),
        }
