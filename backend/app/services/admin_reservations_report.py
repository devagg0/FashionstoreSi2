"""Validacion CU30 y limites locales; no realiza escrituras ni commits."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.category import Category
from app.models.product import Product
from app.repositories.admin_reservations_report import AdminReservationsReportRepository
from app.schemas.admin_reservations_report import STATES, ReservationsReportData, ReservationsReportFilters


class InvalidReservationsReportFilter(ValueError):
    pass


class AdminReservationsReportService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminReservationsReportRepository(db)

    def report(self, filters: ReservationsReportFilters) -> ReservationsReportData:
        zone = ZoneInfo("America/La_Paz")
        try:
            start = (datetime.combine(filters.fecha_desde, time.min, zone)
                     .astimezone(timezone.utc).replace(tzinfo=None) if filters.fecha_desde else None)
            end = (datetime.combine(filters.fecha_hasta + timedelta(days=1), time.min, zone)
                   .astimezone(timezone.utc).replace(tzinfo=None) if filters.fecha_hasta else None)
        except (ValueError, OverflowError) as exc:
            raise InvalidReservationsReportFilter("Rango de fechas fuera de los limites soportados") from exc
        # Evita autoflush incluso si el servicio recibe una Session con autoflush=True.
        with self.db.no_autoflush:
            for column, value, name in (
                (Branch.id_sucursal, filters.id_sucursal, "Sucursal"),
                (Category.id_categoria, filters.id_categoria, "Categoria"),
                (Product.id_producto, filters.id_producto, "Producto"),
            ):
                if value is not None and not self.repository.exists(column, value):
                    raise InvalidReservationsReportFilter(f"{name} inexistente")
            now = datetime.now(timezone.utc)
            data = self.repository.report(filters, start, end, now.replace(tzinfo=None))
        by_state = {row["estado"]: row for row in data["por_estado"]}
        data["por_estado"] = [by_state.get(state, {
            "estado": state, "total_reservas": 0, "unidades_reservadas": 0,
        }) for state in STATES]
        return ReservationsReportData(generado_en=now, filtros=filters, **data)
