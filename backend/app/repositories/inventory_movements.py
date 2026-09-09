"""Persistencia CU15. La transacción pertenece al servicio."""

from typing import get_args

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.color import Color
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.role import Role
from app.models.size import Size
from app.models.user import User
from app.schemas.admin_inventory_movements import MovementType


class InventoryMovementRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_movement(self, movement_id, *, for_update=False):
        statement = select(InventoryMovement).where(
            InventoryMovement.id_movimiento_inventario == movement_id,
            InventoryMovement.tipo_movimiento.in_(get_args(MovementType)),
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_branch(self, branch_id):
        return self.db.get(Branch, branch_id)

    def get_variant(self, variant_id):
        return self.db.execute(select(ProductVariant, Product).outerjoin(
            Product, Product.id_producto == ProductVariant.id_producto,
        ).where(ProductVariant.id_variante_producto == variant_id)).one_or_none()

    def get_responsible(self, assignment_id):
        return self.db.execute(select(EmployeeBranch, Employee, User, Role).outerjoin(
            Employee, Employee.id_empleado == EmployeeBranch.id_empleado,
        ).outerjoin(User, User.id_usuario == Employee.id_usuario).outerjoin(
            Role, Role.id_rol == User.id_rol,
        ).where(EmployeeBranch.id_empleado_sucursal == assignment_id)).one_or_none()

    def get_details(self, movement_id):
        return self.db.scalars(select(InventoryMovementDetail).where(
            InventoryMovementDetail.id_movimiento_inventario == movement_id,
        ).order_by(InventoryMovementDetail.id_variante_producto)).all()

    def lock_inventory(self, branch_id, variant_id):
        return self.db.scalar(select(BranchInventory).where(
            BranchInventory.id_sucursal == branch_id,
            BranchInventory.id_variante_producto == variant_id,
        ).with_for_update())

    def create_inventory(self, branch_id, variant_id):
        inventory = BranchInventory(
            id_sucursal=branch_id, id_variante_producto=variant_id,
            stock_actual=0, stock_reservado=0, stock_minimo=0,
        )
        self.db.add(inventory)
        # La unicidad existente detecta inserciones concurrentes; el servicio
        # revierte la transacción completa y devuelve 409 para reintentar.
        self.db.flush()
        return inventory

    def create(self, payload):
        movement = InventoryMovement(**payload.model_dump(exclude={"detalles"}), estado="PENDIENTE")
        self.db.add(movement)
        self.db.flush()
        self.db.add_all([
            InventoryMovementDetail(
                id_movimiento_inventario=movement.id_movimiento_inventario,
                **detail.model_dump(),
            ) for detail in payload.detalles
        ])
        self.db.flush()
        return movement

    @staticmethod
    def _header_statement():
        origin, destination = aliased(Branch), aliased(Branch)
        return select(
            InventoryMovement.id_movimiento_inventario,
            InventoryMovement.tipo_movimiento, InventoryMovement.estado,
            InventoryMovement.fecha_movimiento, InventoryMovement.motivo,
            InventoryMovement.id_sucursal_origen, origin.nombre.label("sucursal_origen"),
            InventoryMovement.id_sucursal_destino, destination.nombre.label("sucursal_destino"),
            InventoryMovement.id_empleado_sucursal, Employee.id_empleado,
            (User.nombre + " " + User.apellido).label("nombre_empleado"),
            Role.nombre.label("rol"), InventoryMovement.created_at, InventoryMovement.updated_at,
        ).select_from(InventoryMovement).outerjoin(
            origin, origin.id_sucursal == InventoryMovement.id_sucursal_origen,
        ).outerjoin(destination, destination.id_sucursal == InventoryMovement.id_sucursal_destino).join(
            EmployeeBranch, EmployeeBranch.id_empleado_sucursal == InventoryMovement.id_empleado_sucursal,
        ).join(Employee, Employee.id_empleado == EmployeeBranch.id_empleado).join(
            User, User.id_usuario == Employee.id_usuario,
        ).join(Role, Role.id_rol == User.id_rol).where(
            InventoryMovement.tipo_movimiento.in_(get_args(MovementType)),
        )

    def get_detail(self, movement_id):
        header = self.db.execute(self._header_statement().where(
            InventoryMovement.id_movimiento_inventario == movement_id,
        )).mappings().one_or_none()
        if header is None:
            return None
        details = self.db.execute(select(
            InventoryMovementDetail.id_variante_producto, ProductVariant.sku,
            Product.nombre.label("producto"), Size.nombre.label("talla"), Color.nombre.label("color"),
            InventoryMovementDetail.cantidad, InventoryMovementDetail.costo_unitario,
        ).select_from(InventoryMovementDetail).join(
            ProductVariant, ProductVariant.id_variante_producto == InventoryMovementDetail.id_variante_producto,
        ).join(Product, Product.id_producto == ProductVariant.id_producto).join(
            Size, Size.id_talla == ProductVariant.id_talla,
        ).join(Color, Color.id_color == ProductVariant.id_color).where(
            InventoryMovementDetail.id_movimiento_inventario == movement_id,
        ).order_by(InventoryMovementDetail.id_variante_producto)).mappings().all()
        return {**header, "detalles": details}

    def list_movements(self, *, search=None, tipo_movimiento=None, estado=None,
                       id_sucursal=None, id_variante_producto=None,
                       fecha_desde=None, fecha_hasta=None, page=1, page_size=20):
        statement = self._header_statement()
        if search:
            statement = statement.where(InventoryMovement.motivo.ilike(f"%{search}%"))
        if tipo_movimiento is not None:
            statement = statement.where(InventoryMovement.tipo_movimiento == tipo_movimiento)
        if estado is not None:
            statement = statement.where(InventoryMovement.estado == estado)
        if id_sucursal is not None:
            statement = statement.where(or_(
                InventoryMovement.id_sucursal_origen == id_sucursal,
                InventoryMovement.id_sucursal_destino == id_sucursal,
            ))
        if id_variante_producto is not None:
            # La pareja movimiento-variante es UNIQUE: este join no duplica cabeceras.
            statement = statement.join(InventoryMovementDetail,
                InventoryMovementDetail.id_movimiento_inventario == InventoryMovement.id_movimiento_inventario,
            ).where(InventoryMovementDetail.id_variante_producto == id_variante_producto)
        if fecha_desde is not None:
            statement = statement.where(InventoryMovement.fecha_movimiento >= fecha_desde)
        if fecha_hasta is not None:
            statement = statement.where(InventoryMovement.fecha_movimiento <= fecha_hasta)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.execute(statement.order_by(
            InventoryMovement.fecha_movimiento.desc(), InventoryMovement.id_movimiento_inventario.desc(),
        ).offset((page - 1) * page_size).limit(page_size)).mappings().all()
        return rows, total
