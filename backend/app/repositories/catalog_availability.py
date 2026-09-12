"""CU13: consultas de inventario publico con joins explicitos."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.city import City
from app.models.color import Color
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.size import Size


class CatalogAvailabilityRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_product(self, product_id):
        return self.db.get(Product, product_id)

    def get_variant(self, variant_id):
        return self.db.get(ProductVariant, variant_id)

    def list_availability(self, product_id, *, id_variante_producto=None,
                          id_sucursal=None, id_ciudad=None, id_talla=None,
                          id_color=None):
        statement = select(
            ProductVariant.id_variante_producto, ProductVariant.sku,
            ProductVariant.estado.label("variante_estado"),
            Size.id_talla, Size.nombre.label("talla"),
            Color.id_color, Color.nombre.label("color"), Color.codigo_hex,
            Branch.id_sucursal, Branch.nombre.label("nombre_sucursal"),
            Branch.direccion, Branch.hora_apertura, Branch.hora_cierre,
            City.id_ciudad, City.nombre.label("nombre_ciudad"),
            BranchInventory.stock_actual, BranchInventory.stock_reservado,
        ).select_from(BranchInventory).join(
            ProductVariant,
            ProductVariant.id_variante_producto == BranchInventory.id_variante_producto,
        ).join(Product, Product.id_producto == ProductVariant.id_producto).join(
            Size, Size.id_talla == ProductVariant.id_talla,
        ).join(Color, Color.id_color == ProductVariant.id_color).join(
            Branch, Branch.id_sucursal == BranchInventory.id_sucursal,
        ).join(City, City.id_ciudad == Branch.id_ciudad).where(
            Product.id_producto == product_id, Product.estado.is_(True),
            ProductVariant.estado.is_(True), Branch.estado.is_(True),
        )
        for column, value in (
            (ProductVariant.id_variante_producto, id_variante_producto),
            (Branch.id_sucursal, id_sucursal), (City.id_ciudad, id_ciudad),
            (ProductVariant.id_talla, id_talla), (ProductVariant.id_color, id_color),
        ):
            if value is not None:
                statement = statement.where(column == value)
        return self.db.execute(statement.order_by(
            City.nombre, City.id_ciudad, Branch.nombre, Branch.id_sucursal,
            ProductVariant.id_variante_producto,
        )).mappings().all()
