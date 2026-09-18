"""CU23: solo lectura; nunca llama a Stripe ni modifica ventas/inventario."""
from app.repositories.client_purchases import ClientPurchasesRepository
from app.schemas.client_purchases import PurchaseDetail, PurchaseListData, PurchaseSummary
from app.services.client_cart import CartAccessError, CartNotFoundError


class ClientPurchasesService:
    def __init__(self, db):
        self.repository = ClientPurchasesRepository(db)

    def _client(self, user_id):
        client = self.repository.get_client_by_user(user_id)
        if client is None:
            raise CartAccessError("La cuenta no tiene un perfil CLIENTE asociado")
        return client.id_cliente

    @staticmethod
    def _summary(sale, branch, payments):
        return PurchaseSummary.model_validate({
            **{field: getattr(sale, field) for field in (
                "id_venta", "numero_venta", "fecha_completada", "canal", "estado",
                "subtotal", "descuento_total", "total", "moneda")},
            "fecha": sale.fecha_venta,
            "sucursal": {"id_sucursal": branch.id_sucursal, "nombre": branch.nombre},
            "pago": payments[0] if payments else None,
        })

    def list(self, user_id, estado=None, canal=None, limit=20, offset=0):
        rows, total = self.repository.list_purchases(self._client(user_id), estado, canal, limit, offset)
        payments = self.repository.purchase_payments([sale.id_venta for sale, _ in rows])
        by_sale = {}
        for payment in payments:
            by_sale.setdefault(payment["id_venta"], []).append(payment)
        return PurchaseListData(items=[self._summary(sale, branch, by_sale.get(sale.id_venta, []))
            for sale, branch in rows], total=total, limit=limit, offset=offset)

    def detail(self, user_id, sale_id):
        row = self.repository.owned_purchase(sale_id, self._client(user_id))
        if row is None:
            # Igual respuesta para inexistente y ajena: no revela su existencia.
            raise CartNotFoundError("Compra no encontrada")
        sale, branch = row
        payments = self.repository.purchase_payments([sale.id_venta])
        return PurchaseDetail.model_validate({
            **self._summary(sale, branch, payments).model_dump(),
            "productos": self.repository.purchase_products(sale.id_venta), "pagos": payments,
            "devoluciones": self.repository.purchase_returns(sale.id_venta),
            "reembolsos": self.repository.purchase_refunds(sale.id_venta),
        })
