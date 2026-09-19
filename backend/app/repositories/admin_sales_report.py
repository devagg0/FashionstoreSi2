"""Agregaciones CU28 sin joins a pagos, reembolsos ni precios del catalogo."""

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail


class AdminSalesReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def branch_exists(self, branch_id):
        return self.db.scalar(select(Branch.id_sucursal).where(Branch.id_sucursal == branch_id)) is not None

    def category_exists(self, category_id):
        return self.db.scalar(select(Category.id_categoria).where(Category.id_categoria == category_id)) is not None

    def report(self, filters, start_utc, end_utc):
        sales = select(
            Sale.id_venta, Sale.id_sucursal, Sale.id_cliente, Sale.canal,
            Sale.fecha_completada, Sale.subtotal, Sale.descuento_total, Sale.total,
        ).where(Sale.estado == "COMPLETADA")
        if start_utc is not None:
            sales = sales.where(Sale.fecha_completada >= start_utc)
        if end_utc is not None:
            sales = sales.where(Sale.fecha_completada < end_utc)
        if filters.id_sucursal is not None:
            sales = sales.where(Sale.id_sucursal == filters.id_sucursal)
        if filters.canal is not None:
            sales = sales.where(Sale.canal == filters.canal)
        sales = sales.cte("ventas_filtradas")

        lines = (
            select(
                SaleDetail.id_venta, Product.id_producto,
                Product.nombre.label("nombre_producto"),
                SaleDetail.cantidad.label("unidades"),
                (SaleDetail.cantidad * SaleDetail.precio_unitario).label("bruto"),
                (SaleDetail.cantidad * SaleDetail.descuento_unitario).label("descuento"),
                SaleDetail.subtotal_linea.label("neto"),
            )
            .join(sales, sales.c.id_venta == SaleDetail.id_venta)
            .join(ProductVariant, ProductVariant.id_variante_producto == SaleDetail.id_variante_producto)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
        )
        if filters.id_categoria is not None:
            lines = lines.where(Product.id_categoria == filters.id_categoria)
        lines = lines.cte("lineas_filtradas")
        details = select(
            lines.c.id_venta,
            func.sum(lines.c.unidades).label("unidades"),
            func.sum(lines.c.bruto).label("bruto"),
            func.sum(lines.c.descuento).label("descuento"),
            func.sum(lines.c.neto).label("neto"),
        ).group_by(lines.c.id_venta).cte("detalles_por_venta")

        # Una fila por venta: los importes de cabecera nunca se multiplican.
        category = filters.id_categoria is not None
        base = select(
            sales.c.id_venta, sales.c.id_sucursal, sales.c.id_cliente,
            sales.c.canal, sales.c.fecha_completada,
            (details.c.bruto if category else sales.c.subtotal).label("bruto"),
            (details.c.descuento if category else sales.c.descuento_total).label("descuento"),
            (details.c.neto if category else sales.c.total).label("neto"),
            func.coalesce(details.c.unidades, 0).label("unidades"),
        ).select_from(sales).join(
            details, details.c.id_venta == sales.c.id_venta, isouter=not category,
        ).cte("reporte_ventas")

        aggregates = (
            func.count().label("cantidad_ventas"),
            func.coalesce(func.sum(base.c.bruto), 0).label("importe_antes_descuentos"),
            func.coalesce(func.sum(base.c.descuento), 0).label("descuentos"),
            func.coalesce(func.sum(base.c.neto), 0).label("importe_vendido"),
            func.coalesce(func.sum(base.c.unidades), 0).label("unidades_vendidas"),
            func.count(func.distinct(base.c.id_cliente)).label("clientes_identificados"),
            func.coalesce(func.sum(case((base.c.id_cliente.is_(None), 1), else_=0)), 0).label("ventas_sin_cliente"),
        )
        kpis = self.db.execute(select(*aggregates).select_from(base)).mappings().one()
        channels = self.db.execute(
            select(base.c.canal, *aggregates).group_by(base.c.canal).order_by(base.c.canal)
        ).mappings().all()
        branches = self.db.execute(
            select(base.c.id_sucursal, Branch.nombre.label("nombre_sucursal"), *aggregates)
            .join(Branch, Branch.id_sucursal == base.c.id_sucursal)
            .group_by(base.c.id_sucursal, Branch.nombre).order_by(base.c.id_sucursal)
        ).mappings().all()
        products = self.db.execute(
            select(
                lines.c.id_producto, lines.c.nombre_producto,
                func.sum(lines.c.unidades).label("unidades_vendidas"),
                func.sum(lines.c.bruto).label("importe_antes_descuentos"),
                func.sum(lines.c.descuento).label("descuentos"),
                func.sum(lines.c.neto).label("importe_vendido"),
            ).group_by(lines.c.id_producto, lines.c.nombre_producto)
            .order_by(func.sum(lines.c.unidades).desc(), func.sum(lines.c.neto).desc(), lines.c.id_producto)
        ).mappings().all()
        if self.db.get_bind().dialect.name == "sqlite":
            day = func.date(base.c.fecha_completada, "-4 hours")
        else:
            # fecha_completada es TIMESTAMP WITHOUT TIME ZONE almacenado en UTC.
            day = cast(func.timezone("America/La_Paz", func.timezone("UTC", base.c.fecha_completada)), Date)
        daily = self.db.execute(
            select(day.label("fecha"), *aggregates).group_by(day).order_by(day)
        ).mappings().all()
        return kpis, channels, branches, products, daily
