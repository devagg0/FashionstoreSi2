"""Persistencia de CU18, siempre acotada a asignaciones activas."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.city import City
from app.models.client import Client
from app.models.color import Color
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.size import Size
from app.models.user import User
from app.repositories.client_reservations import ClientReservationRepository, HOLDING_STATES


class StaffReservationRepository(ClientReservationRepository):
    """Extiende la persistencia de CU17 para reutilizar expiracion e inventario."""

    def __init__(self, db: Session):
        super().__init__(db)

    def get_employee_by_user(self, user_id: int):
        return self.db.scalar(select(Employee).where(Employee.id_usuario == user_id))

    def list_active_branch_ids(self, employee_id: int, *, for_update: bool = False):
        statement = (
            select(EmployeeBranch.id_sucursal)
            .where(
                EmployeeBranch.id_empleado == employee_id,
                EmployeeBranch.estado.is_(True),
            )
            .order_by(EmployeeBranch.id_sucursal)
        )
        if for_update:
            statement = statement.with_for_update()
        return list(self.db.scalars(statement).all())

    def get_scoped_reservation(
        self, reservation_id: int, branch_ids: list[int], *, for_update: bool = False
    ):
        statement = select(Reservation).where(
            Reservation.id_reserva == reservation_id,
            Reservation.id_sucursal.in_(branch_ids),
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_scoped_reservation_by_code(
        self, code: str, branch_ids: list[int], *, for_update: bool = False
    ):
        statement = select(Reservation).where(
            Reservation.codigo == code,
            Reservation.id_sucursal.in_(branch_ids),
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def list_due_ids(self, branch_ids: list[int], now: datetime):
        return list(
            self.db.scalars(
                select(Reservation.id_reserva)
                .where(
                    Reservation.id_sucursal.in_(branch_ids),
                    Reservation.estado.in_(HOLDING_STATES),
                    Reservation.fecha_expiracion <= now,
                )
                .order_by(Reservation.id_reserva)
            ).all()
        )

    @staticmethod
    def _staff_summary_statement():
        quantity = func.coalesce(func.sum(ReservationDetail.cantidad), 0)
        total = func.coalesce(
            func.sum(ReservationDetail.cantidad * ReservationDetail.precio_unitario), 0
        )
        return (
            select(
                Reservation.id_reserva,
                Reservation.codigo,
                Reservation.estado,
                Reservation.created_at,
                Reservation.fecha_atencion_programada,
                Reservation.fecha_expiracion,
                Reservation.fecha_atencion,
                Client.id_cliente,
                User.nombre.label("cliente_nombre"),
                User.apellido.label("cliente_apellido"),
                User.correo.label("cliente_correo"),
                User.telefono.label("cliente_telefono"),
                Branch.id_sucursal,
                Branch.nombre.label("sucursal"),
                Branch.direccion,
                City.id_ciudad,
                City.nombre.label("ciudad"),
                quantity.label("cantidad_prendas"),
                total.label("total"),
            )
            .select_from(Reservation)
            .join(Client, Client.id_cliente == Reservation.id_cliente)
            .join(User, User.id_usuario == Client.id_usuario)
            .join(Branch, Branch.id_sucursal == Reservation.id_sucursal)
            .join(City, City.id_ciudad == Branch.id_ciudad)
            .outerjoin(
                ReservationDetail,
                ReservationDetail.id_reserva == Reservation.id_reserva,
            )
            .group_by(
                Reservation.id_reserva,
                Client.id_cliente,
                User.id_usuario,
                Branch.id_sucursal,
                City.id_ciudad,
            )
        )

    def list_reservations(
        self,
        branch_ids: list[int],
        *,
        state=None,
        scheduled_from: datetime | None = None,
        scheduled_until: datetime | None = None,
        page=1,
        page_size=20,
    ):
        statement = self._staff_summary_statement().where(
            Reservation.id_sucursal.in_(branch_ids)
        )
        if state is not None:
            statement = statement.where(Reservation.estado == state)
        if scheduled_from is not None:
            statement = statement.where(
                Reservation.fecha_atencion_programada >= scheduled_from
            )
        if scheduled_until is not None:
            statement = statement.where(
                Reservation.fecha_atencion_programada < scheduled_until
            )
        total = self.db.scalar(
            select(func.count()).select_from(statement.subquery())
        ) or 0
        rows = self.db.execute(
            statement.order_by(
                Reservation.fecha_atencion_programada,
                Reservation.id_reserva,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).mappings().all()
        return rows, total

    def get_detail(self, reservation_id: int, branch_ids: list[int]):
        header = self.db.execute(
            self._staff_summary_statement().where(
                Reservation.id_reserva == reservation_id,
                Reservation.id_sucursal.in_(branch_ids),
            )
        ).mappings().one_or_none()
        if header is None:
            return None
        items = self.db.execute(
            select(
                ReservationDetail.id_variante_producto,
                ProductVariant.sku,
                Product.id_producto,
                Product.nombre.label("producto"),
                Size.id_talla,
                Size.nombre.label("talla"),
                Color.id_color,
                Color.nombre.label("color"),
                Color.codigo_hex,
                ReservationDetail.cantidad,
                ReservationDetail.precio_unitario,
            )
            .select_from(ReservationDetail)
            .join(
                ProductVariant,
                ProductVariant.id_variante_producto
                == ReservationDetail.id_variante_producto,
            )
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(ReservationDetail.id_reserva == reservation_id)
            .order_by(ReservationDetail.id_variante_producto)
        ).mappings().all()
        return {**header, "items": items}
