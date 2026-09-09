"""Reglas y transacciones CU14. CU15 es responsable de los movimientos."""

from datetime import datetime, timezone
from math import ceil

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.repositories.inventory import InventoryRepository
from app.schemas.admin_inventory import InventoryData, InventoryPaginationData


class InventoryNotFoundError(Exception):
    pass


class InventoryValidationError(Exception):
    pass


class InventoryConflictError(Exception):
    pass


class InventoryPersistenceError(Exception):
    pass


class AdminInventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = InventoryRepository(db)

    def _transaction(self, operation):
        try:
            result = operation()
            self.db.commit()
            return result
        except (InventoryNotFoundError, InventoryValidationError, InventoryConflictError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise InventoryConflictError("Inventario duplicado o conflicto de integridad concurrente") from error
        except DBAPIError as error:
            self.db.rollback()
            code = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
            if code in {"40001", "40P01", "55P03"}:
                raise InventoryConflictError("Conflicto concurrente; reintente la operación") from error
            raise InventoryPersistenceError from error
        except Exception as error:
            self.db.rollback()
            raise InventoryPersistenceError from error

    @staticmethod
    def _data(row):
        return InventoryData.model_validate(dict(
            row, stock_disponible=max(row["stock_actual"] - row["stock_reservado"], 0),
        ))

    def get_inventory(self, inventory_id):
        row = self.repository.get_detail(inventory_id)
        if row is None:
            raise InventoryNotFoundError("Inventario no encontrado")
        return self._data(row)

    def list_inventory(self, **filters):
        rows, total = self.repository.list_inventory(**filters)
        page, size = filters.get("page", 1), filters.get("page_size", 20)
        return [self._data(row) for row in rows], InventoryPaginationData(
            page=page, page_size=size, total=total, total_pages=ceil(total / size) if total else 0,
        )

    def create_inventory(self, payload):
        def operation():
            branch = self.repository.get_branch(payload.id_sucursal)
            if branch is None:
                raise InventoryNotFoundError("Sucursal no encontrada")
            if not branch.estado:
                raise InventoryValidationError("La sucursal está inactiva")
            row = self.repository.get_variant(payload.id_variante_producto)
            if row is None:
                raise InventoryNotFoundError("Variante no encontrada")
            variant, product = row
            if product is None:
                raise InventoryNotFoundError("Producto no encontrado")
            if not variant.estado or not product.estado:
                raise InventoryValidationError("La variante o su producto están inactivos")
            if self.repository.get_by_branch_variant(payload.id_sucursal, payload.id_variante_producto) is not None:
                raise InventoryConflictError("Ya existe inventario para esa sucursal y variante")
            inventory = self.repository.create(
                payload.id_sucursal, payload.id_variante_producto, payload.stock_minimo,
            )
            self.db.flush()
            return self.get_inventory(inventory.id_inventario_sucursal)
        return self._transaction(operation)

    def update_inventory(self, inventory_id, payload):
        def operation():
            inventory = self.repository.get_inventory(inventory_id)
            if inventory is None:
                raise InventoryNotFoundError("Inventario no encontrado")
            inventory.stock_minimo = payload.stock_minimo
            inventory.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            # La Session existente deshabilita autoflush: persistir antes del detalle.
            self.db.flush()
            return self.get_inventory(inventory_id)
        return self._transaction(operation)
