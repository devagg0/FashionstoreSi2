"""CU21: conversión atómica del carrito, sin pago ni salida de inventario."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.core.config import settings
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.repositories.client_checkout import ClientCheckoutRepository
from app.schemas.client_checkout import DigitalSaleData, DigitalSaleItem
from app.services.catalog import CatalogService
from app.services.client_cart import (
    ClientCartService, CartAccessError, CartConflictError, CartNotFoundError,
    CartValidationError,
)


class ClientCheckoutService(ClientCartService):
    def __init__(self, db):
        super().__init__(db)
        self.checkout = ClientCheckoutRepository(db)

    def _sale_data(self, sale):
        return DigitalSaleData.model_validate(sale).model_copy(update={
            "items": [DigitalSaleItem.model_validate(item)
                      for item in self.checkout.sale_items(sale.id_venta)],
        })

    def confirm(self, user_id, payload):
        def operation():
            # Mismo bloqueo de cliente que CU19: serializa edición/conversión.
            client = self.repository.get_client(user_id, for_update=True)
            if client is None:
                raise CartAccessError("Se requiere un perfil de cliente válido.")
            cart = self.checkout.lock_cart(payload.id_carrito, client.id_cliente)
            if cart is None:
                raise CartNotFoundError("Carrito no encontrado.")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            existing = self.checkout.sale_for_cart(cart.id_carrito)
            if existing is not None:
                if (cart.estado == "CONVERTIDO" and existing.canal == "DIGITAL"
                        and existing.estado == "PENDIENTE" and existing.stock_comprometido
                        and existing.id_reserva is None
                        and existing.id_sucursal == payload.id_sucursal
                        and existing.fecha_expiracion_pago > now):
                    return self._sale_data(existing)
                raise CartConflictError("El carrito ya fue convertido; no se puede reservar nuevamente.")
            if cart.estado != "ACTIVO":
                raise CartConflictError("El carrito no está activo.")
            branch = self.checkout.lock_branch(payload.id_sucursal)
            if branch is None:
                raise CartNotFoundError("Sucursal no encontrada.")
            if not branch.estado:
                raise CartValidationError("La sucursal está inactiva.")
            items = self.checkout.lock_items(cart.id_carrito)
            if not items:
                raise CartValidationError("El carrito está vacío.")
            details, prices = [], {}
            for item in items:
                row = self.checkout.lock_variant(item.id_variante_producto)
                if row is None:
                    raise CartNotFoundError("Variante no encontrada.")
                variant, product = row
                if not variant.estado or not product.estado or item.cantidad <= 0:
                    raise CartValidationError("Producto, variante o cantidad inválidos.")
                if product.id_producto not in prices:
                    base = CatalogService._money(product.precio)
                    promotions = self.catalog_repository.list_current_promotions(product.id_producto)
                    promotion = CatalogService._to_promotion(promotions[0], base) if promotions else None
                    final = promotion.precio_resultante if promotion else base
                    prices[product.id_producto] = base, final, promotion
                base, final, promotion = prices[product.id_producto]
                details.append(dict(
                    id_variante_producto=item.id_variante_producto, cantidad=item.cantidad,
                    precio_unitario=base, descuento_unitario=base - final,
                    subtotal_linea=CatalogService._money(item.cantidad * final),
                    id_promocion=promotion.id_promocion if promotion else None,
                ))
            inventories = self.checkout.lock_inventories(
                branch.id_sucursal, sorted(item.id_variante_producto for item in items),
            )
            by_variant = {row.id_variante_producto: row for row in inventories}
            for item in items:
                inventory = by_variant.get(item.id_variante_producto)
                if inventory is None or item.cantidad > inventory.stock_actual - inventory.stock_reservado:
                    raise CartConflictError("Stock disponible insuficiente para completar la compra.")
            subtotal = sum((d["cantidad"] * d["precio_unitario"] for d in details), Decimal("0.00"))
            total = sum((d["subtotal_linea"] for d in details), Decimal("0.00"))
            sale = Sale(
                numero_venta=f"DIG-{uuid4().hex.upper()}", id_cliente=client.id_cliente,
                id_carrito=cart.id_carrito, id_sucursal=branch.id_sucursal,
                id_empleado=None, id_reserva=None, canal="DIGITAL", moneda="BOB",
                estado="PENDIENTE", fecha_completada=None, stock_comprometido=True,
                fecha_expiracion_pago=now + timedelta(minutes=settings.DIGITAL_CHECKOUT_TTL_MINUTES),
                subtotal=subtotal, descuento_total=subtotal - total, total=total,
                fecha_venta=now, created_at=now, updated_at=now,
            )
            self.db.add(sale)
            self.db.flush()
            self.db.add_all([SaleDetail(id_venta=sale.id_venta, **d) for d in details])
            for item in items:
                inventory = by_variant[item.id_variante_producto]
                inventory.stock_reservado += item.cantidad
                inventory.updated_at = now
            cart.estado = "CONVERTIDO"
            cart.updated_at = now
            self.db.flush()
            return self._sale_data(sale)
        return self._operation(operation, write=True)

    def get_pending_sale(self, user_id, sale_id):
        def operation():
            client = self.repository.get_client(user_id)
            if client is None:
                raise CartAccessError("Se requiere un perfil de cliente válido.")
            sale = self.checkout.owned_sale(sale_id, client.id_cliente)
            if sale is None:
                raise CartNotFoundError("Venta digital pendiente no encontrada.")
            return self._sale_data(sale)
        return self._operation(operation)
