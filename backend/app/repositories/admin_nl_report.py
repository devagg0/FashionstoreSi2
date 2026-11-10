"""Consultas SQLAlchemy cerradas y parametrizadas de CU20 (solo lectura, filtradas por empresa)."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.returns import Return, ReturnDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail


STOCK_ROW_LIMIT = 5000
LA_PAZ_OFFSET = timedelta(hours=4)


@dataclass(frozen=True)
class ReportFilters:
    company_id: int
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    branch_ids: tuple[int, ...] | None = None
    category_ids: tuple[int, ...] | None = None
    product_ids: tuple[int, ...] | None = None
    canal: str | None = None
    estado: str | None = None
    tipo_solicitud: str | None = None
    agrupacion: str | None = None


def _pattern(text: str) -> str:
    escaped = text.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _utc_range(desde: date | None, hasta: date | None):
    """Dias de negocio America/La_Paz (UTC-4) convertidos a UTC para columnas naive."""
    start = datetime.combine(desde, time.min) + LA_PAZ_OFFSET if desde else None
    end = datetime.combine(hasta + timedelta(days=1), time.min) + LA_PAZ_OFFSET if hasta else None
    return start, end


class AdminNaturalLanguageReportRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- Resolucion de nombres (siempre dentro de la empresa) -------------------------
    def branch_ids(self, company_id: int, text: str) -> tuple[int, ...]:
        rows = self.db.scalars(select(Branch.id_sucursal).where(
            Branch.empresa_id == company_id,
            func.lower(Branch.nombre).like(_pattern(text), escape="\\"),
        )).all()
        return tuple(rows)

    def category_ids(self, company_id: int, text: str) -> tuple[int, ...]:
        rows = self.db.scalars(select(Category.id_categoria).where(
            Category.empresa_id == company_id,
            func.lower(Category.nombre).like(_pattern(text), escape="\\"),
        )).all()
        return tuple(rows)

    def product_ids(self, company_id: int, text: str) -> tuple[int, ...]:
        rows = self.db.scalars(select(Product.id_producto).where(
            Product.empresa_id == company_id,
            func.lower(Product.nombre).like(_pattern(text), escape="\\"),
        )).all()
        return tuple(rows)

    def _day(self, column):
        if self.db.get_bind().dialect.name == "sqlite":
            return func.date(column, "-4 hours")
        return cast(func.timezone("America/La_Paz", func.timezone("UTC", column)), Date)

    # --- 1. Ventas por canal / sucursal / dia / producto / categoria ------------------
    def sales(self, f: ReportFilters) -> list[dict]:
        group = f.agrupacion or "canal"
        start, end = _utc_range(f.fecha_desde, f.fecha_hasta)
        conditions = [Sale.empresa_id == f.company_id, Sale.estado == "COMPLETADA"]
        if start is not None:
            conditions.append(Sale.fecha_completada >= start)
        if end is not None:
            conditions.append(Sale.fecha_completada < end)
        if f.branch_ids is not None:
            conditions.append(Sale.id_sucursal.in_(f.branch_ids))
        if f.canal:
            conditions.append(Sale.canal == f.canal)

        line_level = group in {"producto", "categoria"} or f.category_ids is not None or f.product_ids is not None
        if line_level:
            label = {
                "producto": Product.nombre,
                "categoria": Category.nombre,
                "sucursal": Branch.nombre,
                "dia": self._day(Sale.fecha_completada),
            }.get(group, Sale.canal)
            query = (
                select(
                    label.label("grupo"),
                    func.count(distinct(Sale.id_venta)).label("cantidad"),
                    func.coalesce(func.sum(SaleDetail.cantidad), 0).label("unidades"),
                    func.coalesce(func.sum(SaleDetail.subtotal_linea), 0).label("importe"),
                )
                .select_from(Sale)
                .join(SaleDetail, SaleDetail.id_venta == Sale.id_venta)
                .join(ProductVariant, ProductVariant.id_variante_producto == SaleDetail.id_variante_producto)
                .join(Product, Product.id_producto == ProductVariant.id_producto)
                .join(Category, Category.id_categoria == Product.id_categoria)
                .join(Branch, Branch.id_sucursal == Sale.id_sucursal)
                .where(*conditions)
            )
            if f.category_ids is not None:
                query = query.where(Product.id_categoria.in_(f.category_ids))
            if f.product_ids is not None:
                query = query.where(Product.id_producto.in_(f.product_ids))
        else:
            units = (
                select(func.coalesce(func.sum(SaleDetail.cantidad), 0))
                .where(SaleDetail.id_venta == Sale.id_venta).scalar_subquery()
            )
            label = {
                "sucursal": Branch.nombre,
                "dia": self._day(Sale.fecha_completada),
            }.get(group, Sale.canal)
            query = (
                select(
                    label.label("grupo"),
                    func.count(Sale.id_venta).label("cantidad"),
                    func.coalesce(func.sum(units), 0).label("unidades"),
                    func.coalesce(func.sum(Sale.total), 0).label("importe"),
                )
                .select_from(Sale)
                .join(Branch, Branch.id_sucursal == Sale.id_sucursal)
                .where(*conditions)
            )
        query = query.group_by(label)
        query = query.order_by(label if group == "dia" else func.sum(
            SaleDetail.subtotal_linea if line_level else Sale.total).desc())
        return [dict(row) for row in self.db.execute(query).mappings().all()]

    # --- 2. Stock bajo o agotado ------------------------------------------------------
    def stock(self, f: ReportFilters) -> list[dict]:
        available = BranchInventory.stock_actual - BranchInventory.stock_reservado
        query = (
            select(
                Product.nombre.label("producto"), ProductVariant.sku.label("sku"),
                Category.nombre.label("categoria"), Branch.nombre.label("sucursal"),
                BranchInventory.stock_actual.label("actual"),
                BranchInventory.stock_reservado.label("reservado"),
                available.label("disponible"), BranchInventory.stock_minimo.label("minimo"),
            )
            .select_from(BranchInventory)
            .join(Branch, Branch.id_sucursal == BranchInventory.id_sucursal)
            .join(ProductVariant, ProductVariant.id_variante_producto == BranchInventory.id_variante_producto)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Category, Category.id_categoria == Product.id_categoria)
            .where(
                BranchInventory.empresa_id == f.company_id,
                Branch.estado.is_(True), Product.estado.is_(True), ProductVariant.estado.is_(True),
            )
        )
        if f.branch_ids is not None:
            query = query.where(BranchInventory.id_sucursal.in_(f.branch_ids))
        if f.category_ids is not None:
            query = query.where(Product.id_categoria.in_(f.category_ids))
        if f.product_ids is not None:
            query = query.where(Product.id_producto.in_(f.product_ids))
        depleted = available <= 0
        low = (available > 0) & (BranchInventory.stock_minimo > 0) & (available < BranchInventory.stock_minimo)
        status = f.estado or "ALERTA"
        if status == "AGOTADO":
            query = query.where(depleted)
        elif status == "BAJO":
            query = query.where(low)
        elif status == "ALERTA":
            query = query.where(depleted | low)
        query = query.order_by(available, Product.nombre, Branch.nombre).limit(STOCK_ROW_LIMIT)
        rows = []
        for row in self.db.execute(query).mappings().all():
            item = dict(row)
            item["estado"] = "AGOTADO" if item["disponible"] <= 0 else "BAJO"
            rows.append(item)
        return rows

    # --- 3. Cambios / devoluciones por motivo -----------------------------------------
    def returns(self, f: ReportFilters) -> list[dict]:
        group = f.agrupacion or "motivo"
        start, end = _utc_range(f.fecha_desde, f.fecha_hasta)
        conditions = [Return.empresa_id == f.company_id]
        if start is not None:
            conditions.append(Return.created_at >= start)
        if end is not None:
            conditions.append(Return.created_at < end)
        if f.estado:
            conditions.append(Return.estado == f.estado)
        if f.tipo_solicitud:
            conditions.append(Return.tipo == f.tipo_solicitud)
        if f.canal:
            conditions.append(Sale.canal == f.canal)
        needs_product = group in {"producto", "categoria"} or f.category_ids is not None or f.product_ids is not None
        label = {
            "tipo": Return.tipo, "estado": Return.estado, "sucursal": Branch.nombre,
            "producto": Product.nombre, "categoria": Category.nombre,
            "dia": self._day(Return.created_at),
        }.get(group, Return.motivo)
        query = (
            select(
                label.label("grupo"),
                func.count(distinct(Return.id_devolucion)).label("cantidad"),
                func.coalesce(func.sum(ReturnDetail.cantidad), 0).label("unidades"),
            )
            .select_from(Return)
            .join(Sale, Sale.id_venta == Return.id_venta)
            .join(Branch, Branch.id_sucursal == Sale.id_sucursal)
            .outerjoin(ReturnDetail, ReturnDetail.id_devolucion == Return.id_devolucion)
            .where(*conditions)
        )
        if f.branch_ids is not None:
            query = query.where(Sale.id_sucursal.in_(f.branch_ids))
        if needs_product:
            query = (
                query.join(ProductVariant, ProductVariant.id_variante_producto == ReturnDetail.id_variante_producto)
                .join(Product, Product.id_producto == ProductVariant.id_producto)
                .join(Category, Category.id_categoria == Product.id_categoria)
            )
            if f.category_ids is not None:
                query = query.where(Product.id_categoria.in_(f.category_ids))
            if f.product_ids is not None:
                query = query.where(Product.id_producto.in_(f.product_ids))
        query = query.group_by(label).order_by(
            label if group == "dia" else func.count(distinct(Return.id_devolucion)).desc()
        )
        return [dict(row) for row in self.db.execute(query).mappings().all()]

    # --- 4. Reservas por estado -------------------------------------------------------
    def reservations(self, f: ReportFilters) -> list[dict]:
        group = f.agrupacion or "estado"
        start, end = _utc_range(f.fecha_desde, f.fecha_hasta)
        conditions = [Reservation.empresa_id == f.company_id]
        if start is not None:
            conditions.append(Reservation.created_at >= start)
        if end is not None:
            conditions.append(Reservation.created_at < end)
        if f.branch_ids is not None:
            conditions.append(Reservation.id_sucursal.in_(f.branch_ids))
        if f.estado:
            conditions.append(Reservation.estado == f.estado)
        needs_product = group in {"producto", "categoria"} or f.category_ids is not None or f.product_ids is not None
        label = {
            "sucursal": Branch.nombre, "producto": Product.nombre, "categoria": Category.nombre,
            "dia": self._day(Reservation.created_at),
        }.get(group, Reservation.estado)
        query = (
            select(
                label.label("grupo"),
                func.count(distinct(Reservation.id_reserva)).label("cantidad"),
                func.coalesce(func.sum(ReservationDetail.cantidad), 0).label("unidades"),
            )
            .select_from(Reservation)
            .join(Branch, Branch.id_sucursal == Reservation.id_sucursal)
            .outerjoin(ReservationDetail, ReservationDetail.id_reserva == Reservation.id_reserva)
            .where(*conditions)
        )
        if needs_product:
            query = (
                query.join(ProductVariant, ProductVariant.id_variante_producto == ReservationDetail.id_variante_producto)
                .join(Product, Product.id_producto == ProductVariant.id_producto)
                .join(Category, Category.id_categoria == Product.id_categoria)
            )
            if f.category_ids is not None:
                query = query.where(Product.id_categoria.in_(f.category_ids))
            if f.product_ids is not None:
                query = query.where(Product.id_producto.in_(f.product_ids))
        query = query.group_by(label).order_by(
            label if group == "dia" else func.count(distinct(Reservation.id_reserva)).desc()
        )
        return [dict(row) for row in self.db.execute(query).mappings().all()]
