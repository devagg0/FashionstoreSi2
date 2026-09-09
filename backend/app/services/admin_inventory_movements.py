"""Reglas y transacciones de CU15 sobre los modelos existentes."""

from datetime import datetime, timezone
from math import ceil
from typing import get_args

from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories.inventory_movements import InventoryMovementRepository
from app.schemas.admin_inventory_movements import (
    MovementData, MovementFullData, MovementPaginationData, MovementType,
)
from app.services.admin_user_service import EMPLOYEE_ROLE_NAMES


class MovementNotFoundError(Exception):
    pass


class MovementValidationError(Exception):
    pass


class MovementConflictError(Exception):
    pass


class MovementPersistenceError(Exception):
    pass


class AdminInventoryMovementService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = InventoryMovementRepository(db)

    def _transaction(self, operation):
        try:
            result = operation()
            self.db.commit()
            return result
        except (MovementNotFoundError, MovementValidationError, MovementConflictError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise MovementConflictError("Conflicto de integridad o inventario concurrente; reintente la operación") from error
        except DBAPIError as error:
            self.db.rollback()
            code = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
            if code in {"40001", "40P01", "55P03"}:
                raise MovementConflictError("Conflicto concurrente; reintente la operación") from error
            raise MovementPersistenceError from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise MovementPersistenceError from error
        except Exception:
            self.db.rollback()
            raise

    def _validate(self, movement, details):
        kind = movement.tipo_movimiento
        origin, destination = movement.id_sucursal_origen, movement.id_sucursal_destino
        if kind not in get_args(MovementType):
            raise MovementValidationError("Tipo de movimiento no permitido en CU15")
        if kind in {"ENTRADA", "AJUSTE_POSITIVO"}:
            valid = origin is None and destination is not None
        elif kind in {"SALIDA", "AJUSTE_NEGATIVO"}:
            valid = origin is not None and destination is None
        else:
            valid = origin is not None and destination is not None and origin != destination
        if not valid:
            raise MovementValidationError("Sucursales incompatibles con el tipo de movimiento")
        if not details:
            raise MovementValidationError("El movimiento requiere al menos un detalle")
        seen = set()
        for detail in details:
            if detail.id_variante_producto in seen:
                raise MovementValidationError("La variante está repetida en el movimiento")
            seen.add(detail.id_variante_producto)
            if detail.cantidad <= 0:
                raise MovementValidationError("La cantidad debe ser mayor que cero")
            if detail.costo_unitario is not None and detail.costo_unitario < 0:
                raise MovementValidationError("El costo no puede ser negativo")
        for branch_id in sorted({value for value in (origin, destination) if value is not None}):
            branch = self.repository.get_branch(branch_id)
            if branch is None:
                raise MovementNotFoundError("Sucursal no encontrada")
            if not branch.estado:
                raise MovementValidationError("La sucursal está inactiva")
        for variant_id in sorted(seen):
            row = self.repository.get_variant(variant_id)
            if row is None:
                raise MovementNotFoundError("Variante no encontrada")
            variant, product = row
            if product is None:
                raise MovementNotFoundError("Producto no encontrado")
            if not variant.estado or not product.estado:
                raise MovementValidationError("La variante o su producto están inactivos")
        row = self.repository.get_responsible(movement.id_empleado_sucursal)
        if row is None:
            raise MovementNotFoundError("Asignación de empleado no encontrada")
        assignment, employee, user, role = row
        if employee is None:
            raise MovementNotFoundError("Empleado no encontrado")
        # Employee no tiene estado propio: CU06 usa User.estado.
        if not assignment.estado or user is None or not user.estado:
            raise MovementValidationError("La asignación o el usuario del empleado están inactivos")
        if role is None or not role.estado or role.nombre.upper() not in EMPLOYEE_ROLE_NAMES:
            raise MovementValidationError("El responsable no tiene un rol operativo válido")
        if assignment.id_sucursal != (origin if origin is not None else destination):
            raise MovementValidationError("El responsable debe estar asignado a la sucursal de origen o, en entradas, de destino")

    def get_movement(self, movement_id):
        row = self.repository.get_detail(movement_id)
        if row is None:
            raise MovementNotFoundError("Movimiento no encontrado")
        return MovementFullData.model_validate(row)

    def list_movements(self, **filters):
        # Los modelos almacenan fechas UTC sin zona, igual que updated_at.
        for key in ("fecha_desde", "fecha_hasta"):
            value = filters.get(key)
            if value is not None and value.tzinfo is not None:
                filters[key] = value.astimezone(timezone.utc).replace(tzinfo=None)
        start, end = filters.get("fecha_desde"), filters.get("fecha_hasta")
        if start is not None and end is not None and start > end:
            raise MovementValidationError("fecha_desde no puede ser posterior a fecha_hasta")
        rows, total = self.repository.list_movements(**filters)
        page, size = filters.get("page", 1), filters.get("page_size", 20)
        return [MovementData.model_validate(row) for row in rows], MovementPaginationData(
            page=page, page_size=size, total=total, total_pages=ceil(total / size) if total else 0,
        )

    def create_movement(self, payload):
        def operation():
            self._validate(payload, payload.detalles)
            movement = self.repository.create(payload)
            return self.get_movement(movement.id_movimiento_inventario)
        return self._transaction(operation)

    def _pending(self, movement_id):
        movement = self.repository.get_movement(movement_id, for_update=True)
        if movement is None:
            raise MovementNotFoundError("Movimiento no encontrado")
        if movement.estado != "PENDIENTE":
            raise MovementConflictError("Solo se permiten operaciones sobre movimientos PENDIENTES")
        return movement

    def confirm_movement(self, movement_id):
        def operation():
            movement = self._pending(movement_id)
            details = self.repository.get_details(movement_id)
            self._validate(movement, details)
            origin, destination = movement.id_sucursal_origen, movement.id_sucursal_destino
            changes = {}
            for detail in details:
                if origin is not None:
                    changes[(origin, detail.id_variante_producto)] = -detail.cantidad
                if destination is not None:
                    changes[(destination, detail.id_variante_producto)] = detail.cantidad
            inventories = {}
            # Incluye inserciones en el mismo orden global para evitar ciclos
            # con bloqueos de unicidad de inventarios todavía inexistentes.
            for (branch_id, variant_id), delta in sorted(changes.items()):
                inventory = self.repository.lock_inventory(branch_id, variant_id)
                if inventory is None:
                    if delta < 0:
                        raise MovementConflictError("No existe inventario en la sucursal de origen")
                    inventory = self.repository.create_inventory(branch_id, variant_id)
                if delta < 0 and -delta > inventory.stock_actual - inventory.stock_reservado:
                    raise MovementConflictError("Stock disponible insuficiente; no se puede consumir stock reservado")
                inventories[(branch_id, variant_id)] = inventory
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for key, inventory in inventories.items():
                inventory.stock_actual += changes[key]
                inventory.updated_at = now
            movement.estado = "CONFIRMADO"
            movement.updated_at = now
            self.db.flush()
            return self.get_movement(movement_id)
        return self._transaction(operation)

    def cancel_movement(self, movement_id):
        def operation():
            movement = self._pending(movement_id)
            movement.estado = "ANULADO"
            movement.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.flush()
            return self.get_movement(movement_id)
        return self._transaction(operation)
