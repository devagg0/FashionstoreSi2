"""Persistencia CU22. Bloquear siempre venta antes de pago e inventarios."""
from sqlalchemy import select

from app.models.payment import Payment
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail


class PaymentsRepository:
    def __init__(self, db):
        self.db = db

    def lock_sale(self, sale_id):
        return self.db.scalar(select(Sale).where(Sale.id_venta == sale_id)
                              .with_for_update().execution_options(populate_existing=True))

    def payment(self, payment_id):
        return self.db.get(Payment, payment_id)

    def lock_payment(self, payment_id):
        return self.db.scalar(select(Payment).where(Payment.id_pago == payment_id)
                              .with_for_update().execution_options(populate_existing=True))

    def by_key(self, key):
        return self.db.scalar(select(Payment).where(Payment.clave_idempotencia == key))

    def active_payment(self, sale_id):
        return self.db.scalar(select(Payment).where(Payment.id_venta == sale_id,
                              Payment.estado.in_(("PENDIENTE", "APROBADO", "REEMBOLSADO"))))

    def conflicting_payment(self, sale_id, payment_id):
        return self.db.scalar(select(Payment).where(
            Payment.id_venta == sale_id, Payment.id_pago != payment_id,
            Payment.estado.in_(("PENDIENTE", "APROBADO", "REEMBOLSADO"))))

    def items(self, sale_id):
        return self.db.scalars(select(SaleDetail).where(SaleDetail.id_venta == sale_id)
                               .order_by(SaleDetail.id_variante_producto)).all()

    def lock_movement(self, sale_id):
        return self.db.scalar(select(InventoryMovement).where(InventoryMovement.id_venta == sale_id)
                              .with_for_update().execution_options(populate_existing=True))

    def movement_items(self, movement_id):
        return self.db.scalars(select(InventoryMovementDetail).where(
            InventoryMovementDetail.id_movimiento_inventario == movement_id)).all()

    def create_payment(self, **values):
        payment = Payment(**values)
        self.db.add(payment)
        self.db.flush()
        return payment

    def create_digital_movement(self, sale, items, now):
        movement = InventoryMovement(
            id_venta=sale.id_venta, id_sucursal_origen=sale.id_sucursal,
            id_sucursal_destino=None, id_empleado_sucursal=None,
            tipo_movimiento="VENTA", estado="PENDIENTE", motivo="Venta digital CU22",
            fecha_movimiento=now, created_at=now, updated_at=now,
        )
        self.db.add(movement)
        self.db.flush()
        self.db.add_all([InventoryMovementDetail(
            id_movimiento_inventario=movement.id_movimiento_inventario,
            id_variante_producto=item.id_variante_producto, cantidad=item.cantidad,
            costo_unitario=None,
        ) for item in items])
        return movement
