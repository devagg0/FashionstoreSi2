"""Lectura CU23 sobre tablas existentes, sin bloqueos, DDL ni persistencia."""
from sqlalchemy import DateTime, Integer, Numeric, String, column, func, select, table

from app.models.branch import Branch
from app.models.color import Color
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.repositories.client_checkout import ClientCheckoutRepository

# Proyecciones Core de tablas ya creadas por Ciclo 3. No se registran modelos
# parciales en Base ni se refleja/escribe el esquema de la base de datos.
returns = table("t_devolucion", column("id_devolucion", Integer), column("id_venta", Integer),
    column("tipo", String), column("estado", String), column("motivo", String),
    column("created_at", DateTime), column("fecha_resolucion", DateTime), column("fecha_procesamiento", DateTime))
refunds = table("t_reembolso", column("id_reembolso", Integer), column("id_venta", Integer),
    column("id_devolucion", Integer), column("id_pago", Integer), column("estado", String),
    column("monto", Numeric(12, 2)), column("created_at", DateTime), column("fecha_aprobacion", DateTime))


class ClientPurchasesRepository(ClientCheckoutRepository):
    def purchase_query(self, client_id, estado=None, canal=None):
        query = select(Sale, Branch).join(Branch, Branch.id_sucursal == Sale.id_sucursal).where(Sale.id_cliente == client_id)
        if estado is not None:
            query = query.where(Sale.estado == estado)
        if canal is not None:
            query = query.where(Sale.canal == canal)
        return query

    def list_purchases(self, client_id, estado, canal, limit, offset):
        query = self.purchase_query(client_id, estado, canal)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.execute(query.order_by(Sale.fecha_venta.desc(), Sale.id_venta.desc()).limit(limit).offset(offset)).all()
        return rows, total

    def owned_purchase(self, sale_id, client_id):
        return self.db.execute(self.purchase_query(client_id).where(Sale.id_venta == sale_id)).one_or_none()

    def purchase_payments(self, sale_ids):
        if not sale_ids:
            return []
        # Seleccionar solo columnas publicas evita cargar secretos/referencias.
        return self.db.execute(select(Payment.id_pago, Payment.id_venta, Payment.medio, Payment.estado,
            Payment.monto, Payment.moneda, Payment.fecha_aprobacion).where(Payment.id_venta.in_(sale_ids))
            .order_by(Payment.created_at.desc(), Payment.id_pago.desc())).mappings().all()

    def purchase_products(self, sale_id):
        return self.db.execute(select(SaleDetail.id_detalle_venta, SaleDetail.id_variante_producto,
            Product.nombre, Size.nombre.label("talla"), Color.nombre.label("color"), SaleDetail.cantidad,
            SaleDetail.precio_unitario, SaleDetail.descuento_unitario, SaleDetail.subtotal_linea)
            .outerjoin(ProductVariant, ProductVariant.id_variante_producto == SaleDetail.id_variante_producto)
            .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
            .outerjoin(Size, Size.id_talla == ProductVariant.id_talla)
            .outerjoin(Color, Color.id_color == ProductVariant.id_color)
            .where(SaleDetail.id_venta == sale_id).order_by(SaleDetail.id_detalle_venta)).mappings().all()

    def purchase_returns(self, sale_id):
        return self.db.execute(select(returns.c.id_devolucion, returns.c.tipo, returns.c.estado, returns.c.motivo,
            returns.c.created_at.label("fecha"), returns.c.fecha_resolucion, returns.c.fecha_procesamiento)
            .where(returns.c.id_venta == sale_id).order_by(returns.c.created_at.desc(), returns.c.id_devolucion.desc())).mappings().all()

    def purchase_refunds(self, sale_id):
        return self.db.execute(select(refunds.c.id_reembolso, refunds.c.id_devolucion, refunds.c.id_pago,
            refunds.c.estado, refunds.c.monto, refunds.c.created_at.label("fecha"), refunds.c.fecha_aprobacion)
            .where(refunds.c.id_venta == sale_id).order_by(refunds.c.created_at.desc(), refunds.c.id_reembolso.desc())).mappings().all()
