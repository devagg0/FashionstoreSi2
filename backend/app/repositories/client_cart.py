"""CU19: únicamente Cart/CartDetail se escriben. Sin commits ni stock retenido."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.cart import Cart
from app.models.cart_detail import CartDetail
from app.models.client import Client
from app.models.color import Color
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.size import Size
from app.repositories.catalog import CatalogRepository
from app.repositories.catalog_availability import CatalogAvailabilityRepository


class ClientCartRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_client(self, user_id: int, *, for_update=False):
        statement = select(Client).where(Client.id_usuario == user_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_active_cart(self, client_id: int, *, for_update=False):
        statement = select(Cart).where(
            Cart.id_cliente == client_id, Cart.estado == "ACTIVO"
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create_cart(self, client_id: int):
        cart = Cart(id_cliente=client_id, estado="ACTIVO")
        self.db.add(cart)
        self.db.flush()
        return cart

    def get_item(self, cart_id: int, variant_id: int):
        return self.db.scalar(select(CartDetail).where(
            CartDetail.id_carrito == cart_id,
            CartDetail.id_variante_producto == variant_id,
        ))

    def create_item(self, cart_id: int, variant_id: int, quantity: int):
        item = CartDetail(
            id_carrito=cart_id, id_variante_producto=variant_id, cantidad=quantity
        )
        self.db.add(item)
        return item

    def update_quantity(self, item, quantity: int):
        item.cantidad = quantity

    def delete_item(self, item):
        self.db.delete(item)

    def clear_items(self, cart_id: int):
        self.db.execute(delete(CartDetail).where(CartDetail.id_carrito == cart_id))

    def get_variant(self, variant_id: int):
        return self.db.execute(
            select(ProductVariant, Product)
            .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
            .where(ProductVariant.id_variante_producto == variant_id)
        ).one_or_none()

    def availability(self, product_id: int, variant_id: int):
        # CU13 ya filtra producto, variante y sucursal activos. No bloquea stock.
        return CatalogAvailabilityRepository(self.db).list_availability(
            product_id, id_variante_producto=variant_id
        )

    def list_items(self, cart_id: int):
        # No filtrar estados: un artículo desactivado debe seguir visible.
        return self.db.execute(
            select(
                CartDetail.id_detalle_carrito, CartDetail.id_variante_producto,
                CartDetail.cantidad, Product.id_producto,
                Product.nombre.label("nombre_producto"), Product.precio,
                Product.estado.label("estado_producto"), ProductVariant.sku,
                ProductVariant.estado.label("estado_variante"),
                Size.id_talla, Size.nombre.label("talla"),
                Color.id_color, Color.nombre.label("color"), Color.codigo_hex,
                CatalogRepository._principal_image().label("imagen_principal"),
            )
            .select_from(CartDetail)
            .join(ProductVariant, ProductVariant.id_variante_producto == CartDetail.id_variante_producto)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(CartDetail.id_carrito == cart_id)
            .order_by(CartDetail.id_detalle_carrito)
        ).mappings().all()
