"""CU29: validacion y serializacion; nunca libera reservas ni altera inventario."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.category import Category
from app.models.product import Product
from app.repositories.admin_inventory_report import AdminInventoryReportRepository
from app.schemas.admin_inventory_report import InventoryReportData, InventoryReportFilters


class InvalidInventoryReportFilter(ValueError):
    pass


class AdminInventoryReportService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminInventoryReportRepository(db)

    def report(self, filters: InventoryReportFilters) -> InventoryReportData:
        # Aun con una Session configurada con autoflush, este servicio solo lee.
        with self.db.no_autoflush:
            for model, column, value, label in (
                (Branch, Branch.id_sucursal, filters.id_sucursal, "Sucursal"),
                (Category, Category.id_categoria, filters.id_categoria, "Categoria"),
                (Product, Product.id_producto, filters.id_producto, "Producto"),
            ):
                if value is not None and not self.repository.exists(model, column, value):
                    raise InvalidInventoryReportFilter(f"{label} inexistente")
            kpis, branches, categories, rows, negative = self.repository.report(filters)
        total = kpis["total_registros_inventario"]
        return InventoryReportData(
            generado_en=datetime.now(timezone.utc), filtros=filters,
            kpis=kpis, por_sucursal=branches, por_categoria=categories,
            detalle={
                "items": [self._item(row) for row in rows],
                "pagination": {
                    "page": filters.page, "page_size": filters.page_size, "total": total,
                    "total_pages": (total + filters.page_size - 1) // filters.page_size,
                },
            },
            advertencias=[{"registros": negative}] if negative else [],
        )

    @staticmethod
    def _item(row):
        return {
            "id_inventario_sucursal": row["id_inventario_sucursal"],
            **{name: {f"id_{name}": row[f"id_{name}"], "nombre": row[name], "estado": row[f"{name}_estado"]}
               for name in ("sucursal", "categoria", "producto")},
            "variante": {
                "id_variante_producto": row["id_variante_producto"], "sku": row["sku"],
                "talla": row["talla"], "color": row["color"], "estado": row["variante_estado"],
            },
            **{name: row[name] for name in (
                "stock_actual", "stock_reservado", "stock_disponible", "stock_minimo",
                "estado_stock", "faltante_hasta_minimo",
            )},
        }
