from sqlalchemy import select, func
from app.models.returns import Return, ReturnDetail, Refund

class ReturnsRepository:
    def __init__(self, db):
        self.db = db

    def lock(self, return_id):
        return self.db.scalar(select(Return).where(Return.id_devolucion == return_id)
            .with_for_update().execution_options(populate_existing=True))

    def details(self, return_id):
        return self.db.scalars(select(ReturnDetail).where(ReturnDetail.id_devolucion == return_id)
            .order_by(ReturnDetail.id_variante_producto)).all()

    def refunds(self, return_id):
        return self.db.scalars(select(Refund).where(Refund.id_devolucion == return_id)
            .with_for_update().execution_options(populate_existing=True)).all()

    def used(self, sale_id, variant_id):
        return self.db.scalar(select(func.coalesce(func.sum(ReturnDetail.cantidad), 0))
            .join(Return, Return.id_devolucion == ReturnDetail.id_devolucion)
            .where(Return.id_venta == sale_id, ReturnDetail.id_variante_producto == variant_id,
                   Return.estado != "RECHAZADA"))

    def reserved_money(self, payment_id, exclude=None):
        stmt = select(func.coalesce(func.sum(Refund.monto), 0)).where(
            Refund.id_pago == payment_id, Refund.estado.in_(("PENDIENTE", "APROBADO")))
        if exclude is not None:
            stmt = stmt.where(Refund.id_reembolso != exclude)
        return self.db.scalar(stmt)

    def add(self, model, **values):
        row = model(**values)
        self.db.add(row)
        self.db.flush()
        return row
