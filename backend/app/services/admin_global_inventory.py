"""CU16: serialización y totales de consulta, sin transacciones de escritura."""

from math import ceil

from sqlalchemy.orm import Session

from app.repositories.global_inventory import GlobalInventoryRepository
from app.schemas.admin_global_inventory import (
    BranchInventoryData, GlobalInventoryData, GlobalInventoryDetailData,
    GlobalInventoryPaginationData,
)


class GlobalInventoryNotFoundError(Exception):
    pass


class AdminGlobalInventoryService:
    def __init__(self, db: Session):
        self.repository = GlobalInventoryRepository(db)

    @staticmethod
    def _data(row):
        return GlobalInventoryData(
            producto=dict(id_producto=row["id_producto"], nombre=row["producto"], estado=row["producto_estado"]),
            categoria=dict(id_categoria=row["id_categoria"], nombre=row["categoria"]),
            variante=dict(id_variante_producto=row["id_variante_producto"], sku=row["sku"], estado=row["variante_estado"]),
            talla=dict(id_talla=row["id_talla"], nombre=row["talla"]),
            color=dict(id_color=row["id_color"], nombre=row["color"]),
            **{field: row[field] for field in (
                "total_stock_actual", "total_stock_reservado", "total_stock_disponible",
                "cantidad_sucursales", "cantidad_sucursales_con_stock",
            )},
        )

    def list_inventory(self, **filters):
        rows, total = self.repository.list_inventory(**filters)
        page, size = filters.get("page", 1), filters.get("page_size", 20)
        return [self._data(row) for row in rows], GlobalInventoryPaginationData(
            page=page, page_size=size, total=total, total_pages=ceil(total / size) if total else 0,
        )

    def get_inventory(self, variant_id):
        row = self.repository.get_variant(variant_id)
        if row is None:
            raise GlobalInventoryNotFoundError("Variante no encontrada")
        branches = [BranchInventoryData(**dict(
            branch, stock_disponible=max(branch["stock_actual"] - branch["stock_reservado"], 0),
        )) for branch in self.repository.list_branches(variant_id)]
        data = self._data(dict(
            row,
            total_stock_actual=sum(branch.stock_actual for branch in branches),
            total_stock_reservado=sum(branch.stock_reservado for branch in branches),
            total_stock_disponible=sum(branch.stock_disponible for branch in branches),
            cantidad_sucursales=len(branches),
            cantidad_sucursales_con_stock=sum(branch.stock_disponible > 0 for branch in branches),
        ))
        return GlobalInventoryDetailData(**data.model_dump(), sucursales=branches)
