"""Persistencia CU14 con joins explícitos, sin commits ni cambios de stock."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.city import City
from app.models.color import Color
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.size import Size


class InventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_branch(self, branch_id):
        return self.db.get(Branch, branch_id)

    def get_variant(self, variant_id):
        return self.db.execute(select(ProductVariant, Product).outerjoin(
            Product, Product.id_producto == ProductVariant.id_producto,
        ).where(ProductVariant.id_variante_producto == variant_id)).one_or_none()

    def get_inventory(self, inventory_id):
        return self.db.get(BranchInventory, inventory_id)

    def get_by_branch_variant(self, branch_id, variant_id):
        return self.db.scalar(select(BranchInventory).where(
            BranchInventory.id_sucursal == branch_id,
            BranchInventory.id_variante_producto == variant_id,
        ))

    def create(self, branch_id, variant_id, minimum):
        inventory = BranchInventory(
            id_sucursal=branch_id, id_variante_producto=variant_id,
            stock_actual=0, stock_reservado=0, stock_minimo=minimum,
        )
        self.db.add(inventory)
        return inventory

    @staticmethod
    def _statement():
        return select(
            BranchInventory.id_inventario_sucursal,
            BranchInventory.id_sucursal, Branch.nombre.label("sucursal"),
            Branch.estado.label("sucursal_estado"), City.id_ciudad, City.nombre.label("ciudad"),
            Product.id_producto, Product.nombre.label("producto"), Product.estado.label("producto_estado"),
            BranchInventory.id_variante_producto, ProductVariant.sku,
            ProductVariant.estado.label("variante_estado"),
            Size.id_talla, Size.nombre.label("talla"), Color.id_color, Color.nombre.label("color"),
            BranchInventory.stock_actual, BranchInventory.stock_reservado,
            BranchInventory.stock_minimo, BranchInventory.created_at, BranchInventory.updated_at,
        ).select_from(BranchInventory).join(
            Branch, Branch.id_sucursal == BranchInventory.id_sucursal,
        ).join(City, City.id_ciudad == Branch.id_ciudad).join(
            ProductVariant, ProductVariant.id_variante_producto == BranchInventory.id_variante_producto,
        ).join(Product, Product.id_producto == ProductVariant.id_producto).join(
            Size, Size.id_talla == ProductVariant.id_talla,
        ).join(Color, Color.id_color == ProductVariant.id_color)

    def get_detail(self, inventory_id):
        return self.db.execute(self._statement().where(
            BranchInventory.id_inventario_sucursal == inventory_id,
        )).mappings().one_or_none()

    def list_inventory(self, *, page=1, page_size=20, search=None, id_sucursal=None,
                       id_ciudad=None, id_categoria=None, id_producto=None,
                       id_variante_producto=None, id_talla=None, id_color=None):
        statement = self._statement()
        for column, value in (
            (BranchInventory.id_sucursal, id_sucursal), (Branch.id_ciudad, id_ciudad),
            (Product.id_categoria, id_categoria), (Product.id_producto, id_producto),
            (BranchInventory.id_variante_producto, id_variante_producto),
            (ProductVariant.id_talla, id_talla), (ProductVariant.id_color, id_color),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if search and search.strip():
            escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            statement = statement.where(or_(
                Product.nombre.ilike(pattern, escape="\\"),
                ProductVariant.sku.ilike(pattern, escape="\\"),
            ))
        # Count y listado parten de la misma consulta filtrada, sin filtrar estados.
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(statement.order_by(
            BranchInventory.id_inventario_sucursal,
        ).offset((page - 1) * page_size).limit(page_size)).mappings().all()
        return rows, total
