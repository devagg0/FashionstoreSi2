"""Persistencia CU20 con joins explicitos; nunca realiza commit."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.city import City
from app.models.client import Client
from app.models.color import Color
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.size import Size
from app.models.user import User


class StaffSalesRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_employee(self, user_id):
        return self.db.scalar(select(Employee).where(Employee.id_usuario == user_id))

    def branches(self, employee_id, *, for_update=False):
        statement = (
            select(Branch.id_sucursal, Branch.nombre, Branch.direccion,
                   City.nombre.label("ciudad"), EmployeeBranch.id_empleado_sucursal)
            .select_from(EmployeeBranch)
            .join(Branch, Branch.id_sucursal == EmployeeBranch.id_sucursal)
            .join(City, City.id_ciudad == Branch.id_ciudad)
            .where(EmployeeBranch.id_empleado == employee_id,
                   EmployeeBranch.estado.is_(True), Branch.estado.is_(True))
            .order_by(EmployeeBranch.id_sucursal)
        )
        if for_update:
            statement = statement.with_for_update(of=(EmployeeBranch, Branch))
        return self.db.execute(statement).mappings().all()

    def get_branch(self, branch_id):
        return self.db.get(Branch, branch_id)

    def get_reservation(self, reservation_id, *, for_update=False):
        statement = select(Reservation).where(Reservation.id_reserva == reservation_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement.execution_options(populate_existing=True))

    def reservation_details(self, reservation_id):
        return self.db.scalars(select(ReservationDetail).where(
            ReservationDetail.id_reserva == reservation_id
        ).order_by(ReservationDetail.id_variante_producto)).all()

    def sale_for_reservation(self, reservation_id):
        return self.db.scalar(select(Sale).where(Sale.id_reserva == reservation_id))

    def sale_for_number(self, number):
        return self.db.scalar(select(Sale).where(Sale.numero_venta == number))

    def get_sale(self, sale_id):
        return self.db.get(Sale, sale_id)

    def variant(self, variant_id):
        return self.db.execute(
            select(ProductVariant, Product, Size.nombre, Color.nombre)
            .select_from(ProductVariant)
            .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(ProductVariant.id_variante_producto == variant_id)
        ).one_or_none()

    def inventories(self, branch_id, variant_ids, *, for_update=False):
        statement = (select(BranchInventory).where(
            BranchInventory.id_sucursal == branch_id,
            BranchInventory.id_variante_producto.in_(sorted(variant_ids)),
        ).order_by(BranchInventory.id_variante_producto))
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalars(statement.execution_options(populate_existing=True)).all()

    def create_sale(self, **values):
        sale = Sale(**values)
        self.db.add(sale)
        self.db.flush()
        return sale

    def create_details(self, sale_id, items):
        self.db.add_all([SaleDetail(id_venta=sale_id, **item) for item in items])
        self.db.flush()

    def create_movement(self, sale, assignment_id, items):
        movement = InventoryMovement(
            id_sucursal_origen=sale.id_sucursal, id_sucursal_destino=None,
            id_empleado_sucursal=assignment_id, id_venta=sale.id_venta,
            tipo_movimiento="VENTA", estado="PENDIENTE", motivo="Venta presencial",
        )
        self.db.add(movement)
        self.db.flush()
        self.db.add_all([
            InventoryMovementDetail(
                id_movimiento_inventario=movement.id_movimiento_inventario,
                id_variante_producto=item["id_variante_producto"],
                cantidad=item["cantidad"], costo_unitario=None,
            ) for item in items
        ])
        self.db.flush()
        return movement

    def detail(self, sale):
        branch = self.db.execute(
            select(Branch.id_sucursal, Branch.nombre, Branch.direccion,
                   City.nombre.label("ciudad"), EmployeeBranch.id_empleado_sucursal)
            .select_from(Branch).join(City, City.id_ciudad == Branch.id_ciudad)
            .join(EmployeeBranch, (EmployeeBranch.id_sucursal == Branch.id_sucursal)
                  & (EmployeeBranch.id_empleado == sale.id_empleado))
            .where(Branch.id_sucursal == sale.id_sucursal)
        ).mappings().one()
        cashier = self.db.execute(
            select(Employee.id_empleado, User.id_usuario, User.nombre, User.apellido)
            .join(User, User.id_usuario == Employee.id_usuario)
            .where(Employee.id_empleado == sale.id_empleado)
        ).mappings().one()
        client = None
        if sale.id_cliente is not None:
            client = self.db.execute(
                select(Client.id_cliente, User.id_usuario, User.nombre, User.apellido)
                .join(User, User.id_usuario == Client.id_usuario)
                .where(Client.id_cliente == sale.id_cliente)
            ).mappings().one()
        reservation = None
        if sale.id_reserva is not None:
            reservation = self.db.execute(select(
                Reservation.id_reserva, Reservation.codigo, Reservation.estado,
            ).where(Reservation.id_reserva == sale.id_reserva)).mappings().one()
        details = self.db.execute(
            select(SaleDetail.id_variante_producto, SaleDetail.cantidad,
                   SaleDetail.precio_unitario, SaleDetail.descuento_unitario,
                   SaleDetail.id_promocion, SaleDetail.subtotal_linea,
                   ProductVariant.sku, Product.nombre.label("producto"),
                   Size.nombre.label("talla"), Color.nombre.label("color"))
            .select_from(SaleDetail)
            .join(ProductVariant, ProductVariant.id_variante_producto == SaleDetail.id_variante_producto)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(SaleDetail.id_venta == sale.id_venta)
            .order_by(SaleDetail.id_variante_producto)
        ).mappings().all()
        movement = self.db.execute(select(
            InventoryMovement.id_movimiento_inventario,
            InventoryMovement.id_empleado_sucursal,
            InventoryMovement.tipo_movimiento, InventoryMovement.estado,
        ).where(InventoryMovement.id_venta == sale.id_venta)).mappings().one()
        return {
            **{key: getattr(sale, key) for key in (
                "id_venta", "numero_venta", "estado", "id_sucursal", "id_empleado",
                "id_cliente", "id_reserva", "fecha_venta", "subtotal", "descuento_total", "total",
            )},
            "sucursal": branch, "cajero": cashier, "cliente": client,
            "reserva": reservation, "detalles": details, "movimiento": movement,
        }
