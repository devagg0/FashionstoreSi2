"""Generacion de comprobantes CU25 exclusivamente en memoria."""
from app.repositories.receipts import ReceiptsRepository
from app.schemas.receipts import Receipt, ReceiptItem, ReceiptPayment
from app.services.client_cart import CartAccessError, CartNotFoundError


class ReceiptConflictError(Exception):
    pass


class ReceiptsService:
    def __init__(self, db):
        self.repository = ReceiptsRepository(db)

    def client_receipt(self, user_id, sale_id):
        client = self.repository.get_client_by_user(user_id)
        if client is None:
            raise CartAccessError('La cuenta no tiene un perfil CLIENTE asociado')
        return self._receipt(self.repository.owned_purchase(sale_id, client.id_cliente))

    def staff_receipt(self, user_id, sale_id):
        return self._receipt(self.repository.staff_purchase(sale_id, user_id))

    def _receipt(self, row):
        if row is None:
            raise CartNotFoundError('Venta no encontrada para consultar el comprobante')
        sale, branch = row
        if sale.estado != 'COMPLETADA' or sale.fecha_completada is None:
            raise ReceiptConflictError('El comprobante solo esta disponible para ventas COMPLETADAS')
        payments = self.repository.receipt_payments(sale.id_venta)
        if len(payments) != 1:
            raise ReceiptConflictError('La venta no tiene un unico pago aprobado registrado')
        payment = payments[0]
        if payment['moneda'] != sale.moneda or payment['monto'] != sale.total:
            raise ReceiptConflictError('El pago registrado no corresponde al importe de la venta')
        return Receipt(
            numero_venta=sale.numero_venta, fecha_completada=sale.fecha_completada,
            canal=sale.canal, sucursal={'nombre': branch.nombre, 'direccion': branch.direccion},
            cliente=self.repository.receipt_client(sale.id_cliente),
            productos=[ReceiptItem(**item) for item in self.repository.purchase_products(sale.id_venta)],
            subtotal=sale.subtotal, descuento_total=sale.descuento_total,
            total=sale.total, moneda=sale.moneda, pago=ReceiptPayment(**payment),
        )
