"""CU21: bloqueos y persistencia, sin commits propios."""
from sqlalchemy import select

from app.models.branch import Branch
from app.models.cart import Cart
from app.models.cart_detail import CartDetail
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.repositories.client_reservations import ClientReservationRepository


class ClientCheckoutRepository(ClientReservationRepository):
    def lock_cart(self, cart_id, client_id):
        return self.db.scalar(select(Cart).where(
            Cart.id_carrito == cart_id, Cart.id_cliente == client_id,
        ).with_for_update())

    def lock_branch(self, branch_id):
        return self.db.scalar(select(Branch).where(
            Branch.id_sucursal == branch_id,
        ).with_for_update(read=True))

    def lock_items(self, cart_id):
        return self.db.scalars(select(CartDetail).where(
            CartDetail.id_carrito == cart_id,
        ).order_by(CartDetail.id_variante_producto).with_for_update()).all()

    def lock_variant(self, variant_id):
        return self.db.execute(select(ProductVariant, Product).join(
            Product, Product.id_producto == ProductVariant.id_producto,
        ).where(ProductVariant.id_variante_producto == variant_id)
            .with_for_update(read=True)).one_or_none()

    def sale_for_cart(self, cart_id):
        return self.db.scalar(select(Sale).where(Sale.id_carrito == cart_id).with_for_update())

    def owned_sale(self, sale_id, client_id):
        return self.db.scalar(select(Sale).where(
            Sale.id_venta == sale_id, Sale.id_cliente == client_id,
            Sale.canal == "DIGITAL", Sale.estado == "PENDIENTE",
        ))

    def sale_items(self, sale_id):
        return self.db.scalars(select(SaleDetail).where(
            SaleDetail.id_venta == sale_id,
        ).order_by(SaleDetail.id_variante_producto)).all()
