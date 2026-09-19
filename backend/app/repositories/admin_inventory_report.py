"""CU29: cinco SELECT acotados, sin movimientos ni operaciones de escritura."""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.color import Color
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.size import Size


class AdminInventoryReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def exists(self, model, column, value):
        return self.db.scalar(select(column).select_from(model).where(column == value)) is not None

    @staticmethod
    def _base(filters):
        available = BranchInventory.stock_actual - BranchInventory.stock_reservado
        state = case(
            (available == 0, "AGOTADO"),
            ((available > 0) & (available < BranchInventory.stock_minimo), "BAJO_STOCK"),
            ((available > 0) & (available >= BranchInventory.stock_minimo), "NORMAL"),
            else_=None,
        )
        statement = select(
            BranchInventory.id_inventario_sucursal,
            Branch.id_sucursal, Branch.nombre.label("sucursal"), Branch.estado.label("sucursal_estado"),
            Category.id_categoria, Category.nombre.label("categoria"), Category.estado.label("categoria_estado"),
            Product.id_producto, Product.nombre.label("producto"), Product.estado.label("producto_estado"),
            ProductVariant.id_variante_producto, ProductVariant.sku, ProductVariant.estado.label("variante_estado"),
            Size.nombre.label("talla"), Color.nombre.label("color"),
            BranchInventory.stock_actual, BranchInventory.stock_reservado, BranchInventory.stock_minimo,
            available.label("stock_disponible"), state.label("estado_stock"),
            case((BranchInventory.stock_minimo > available,
                  BranchInventory.stock_minimo - available), else_=0).label("faltante_hasta_minimo"),
        ).select_from(BranchInventory).join(
            Branch, Branch.id_sucursal == BranchInventory.id_sucursal,
        ).join(ProductVariant, ProductVariant.id_variante_producto == BranchInventory.id_variante_producto).join(
            Product, Product.id_producto == ProductVariant.id_producto,
        ).join(Category, Category.id_categoria == Product.id_categoria).join(
            Size, Size.id_talla == ProductVariant.id_talla,
        ).join(Color, Color.id_color == ProductVariant.id_color)
        for column, value in (
            (Branch.id_sucursal, filters.id_sucursal),
            (Category.id_categoria, filters.id_categoria),
            (Product.id_producto, filters.id_producto),
        ):
            if value is not None:
                statement = statement.where(column == value)
        return statement.cte("inventarios_alcance")

    def report(self, filters):
        scope = self._base(filters)
        # Advertir incluso si un filtro de estado excluye las filas inconsistentes.
        negative = self.db.scalar(select(func.count()).select_from(scope).where(scope.c.stock_disponible < 0))
        filtered = select(scope)
        if filters.estado_stock is not None:
            filtered = filtered.where(scope.c.estado_stock == filters.estado_stock)
        base = filtered.cte("inventarios_filtrados")
        c = base.c

        def count_if(condition):
            return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)

        aggregates = (
            func.count(func.distinct(c.id_producto)).label("total_productos"),
            func.count(func.distinct(c.id_variante_producto)).label("total_variantes"),
            func.count().label("total_registros_inventario"),
            func.coalesce(func.sum(c.stock_actual), 0).label("unidades_actuales"),
            func.coalesce(func.sum(c.stock_reservado), 0).label("unidades_reservadas"),
            func.coalesce(func.sum(c.stock_disponible), 0).label("unidades_disponibles"),
            count_if(c.estado_stock == "AGOTADO").label("registros_agotados"),
            count_if(c.estado_stock == "BAJO_STOCK").label("registros_bajo_stock"),
            func.count(func.distinct(case((c.estado_stock == "AGOTADO", c.id_producto)))).label("productos_con_agotados"),
            func.count(func.distinct(case((c.estado_stock == "BAJO_STOCK", c.id_producto)))).label("productos_con_bajo_stock"),
            count_if(c.stock_minimo == 0).label("registros_con_stock_minimo_cero"),
        )
        kpis = self.db.execute(select(*aggregates).select_from(base)).mappings().one()
        branches = self.db.execute(select(
            c.id_sucursal, c.sucursal.label("nombre"), c.sucursal_estado.label("estado"), *aggregates,
        ).group_by(c.id_sucursal, c.sucursal, c.sucursal_estado).order_by(c.id_sucursal)).mappings().all()
        categories = self.db.execute(select(
            c.id_categoria, c.categoria.label("nombre"), c.categoria_estado.label("estado"), *aggregates,
        ).group_by(c.id_categoria, c.categoria, c.categoria_estado).order_by(c.id_categoria)).mappings().all()
        rows = self.db.execute(select(base).order_by(c.id_inventario_sucursal).offset(
            (filters.page - 1) * filters.page_size,
        ).limit(filters.page_size)).mappings().all()
        return kpis, branches, categories, rows, negative
