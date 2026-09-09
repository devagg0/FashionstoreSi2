"""Consultas CU16: agregados por variante, sin escrituras ni filtros de estado."""

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.branch_inventory import BranchInventory
from app.models.branch import Branch
from app.models.city import City
from app.models.product_variant import ProductVariant
from app.models.product import Product
from app.models.category import Category
from app.models.size import Size
from app.models.color import Color


class GlobalInventoryRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _variant_statement():
        return select(
            Product.id_producto, Product.nombre.label("producto"),
            Product.estado.label("producto_estado"),
            Category.id_categoria, Category.nombre.label("categoria"),
            ProductVariant.id_variante_producto, ProductVariant.sku,
            ProductVariant.estado.label("variante_estado"),
            Size.id_talla, Size.nombre.label("talla"),
            Color.id_color, Color.nombre.label("color"),
        ).select_from(ProductVariant).join(
            Product, Product.id_producto == ProductVariant.id_producto,
        ).join(Category, Category.id_categoria == Product.id_categoria).join(
            Size, Size.id_talla == ProductVariant.id_talla,
        ).join(Color, Color.id_color == ProductVariant.id_color)

    def list_inventory(self, *, page=1, page_size=20, search=None,
                       id_categoria=None, id_producto=None, id_talla=None,
                       id_color=None, id_ciudad=None, id_sucursal=None):
        available = case((BranchInventory.stock_actual > BranchInventory.stock_reservado,
                          BranchInventory.stock_actual - BranchInventory.stock_reservado), else_=0)
        inventory = select(
            BranchInventory.id_variante_producto,
            func.sum(BranchInventory.stock_actual).label("total_stock_actual"),
            func.sum(BranchInventory.stock_reservado).label("total_stock_reservado"),
            func.sum(available).label("total_stock_disponible"),
            func.count(BranchInventory.id_sucursal).label("cantidad_sucursales"),
            func.sum(case((available > 0, 1), else_=0)).label("cantidad_sucursales_con_stock"),
        ).select_from(BranchInventory).join(
            Branch, Branch.id_sucursal == BranchInventory.id_sucursal,
        ).join(City, City.id_ciudad == Branch.id_ciudad)
        for column, value in ((City.id_ciudad, id_ciudad), (Branch.id_sucursal, id_sucursal)):
            if value is not None:
                inventory = inventory.where(column == value)
        totals = inventory.group_by(BranchInventory.id_variante_producto).subquery()
        statement = self._variant_statement().join(
            totals, totals.c.id_variante_producto == ProductVariant.id_variante_producto,
        ).add_columns(*[column for column in totals.c if column.key != "id_variante_producto"])
        for column, value in (
            (Product.id_categoria, id_categoria), (Product.id_producto, id_producto),
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
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(statement.order_by(
            ProductVariant.id_variante_producto,
        ).offset((page - 1) * page_size).limit(page_size)).mappings().all()
        return rows, total

    def get_variant(self, variant_id):
        return self.db.execute(self._variant_statement().where(
            ProductVariant.id_variante_producto == variant_id,
        )).mappings().one_or_none()

    def list_branches(self, variant_id):
        return self.db.execute(select(
            Branch.id_sucursal, Branch.nombre.label("nombre_sucursal"),
            Branch.estado.label("estado_sucursal"),
            City.id_ciudad, City.nombre.label("nombre_ciudad"),
            BranchInventory.id_inventario_sucursal, BranchInventory.stock_actual,
            BranchInventory.stock_reservado, BranchInventory.stock_minimo,
        ).select_from(BranchInventory).join(
            Branch, Branch.id_sucursal == BranchInventory.id_sucursal,
        ).join(City, City.id_ciudad == Branch.id_ciudad).where(
            BranchInventory.id_variante_producto == variant_id,
        ).order_by(Branch.id_sucursal)).mappings().all()
