"""Repositorio de lectura para PK08 - CU12: Consultar operaciones offline persistidas en PostgreSQL."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.client import Client
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.offline_reservation_sync import (
    OfflineReservationSync,
    ensure_offline_reservation_sync_table,
)
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail


class OfflineOperationStatusRepository:
    """Acceso de solo lectura a entidades de sincronización offline, reservas, ventas y pagos."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_reservation_sync(
        self, company_id: int, uuid_offline: str
    ) -> OfflineReservationSync | None:
        """Busca el registro de sincronización de reserva por su UUID offline."""
        ensure_offline_reservation_sync_table(self.db)
        statement = select(OfflineReservationSync).where(
            OfflineReservationSync.empresa_id == company_id,
            OfflineReservationSync.uuid_reserva_offline == uuid_offline,
        )
        return self.db.scalar(statement)

    def get_reservation(
        self, company_id: int, reservation_id: int
    ) -> Reservation | None:
        """Obtiene la reserva por su ID dentro del tenant."""
        statement = select(Reservation).where(
            Reservation.empresa_id == company_id,
            Reservation.id_reserva == reservation_id,
        )
        return self.db.scalar(statement)

    def get_reservation_by_code(
        self, company_id: int, code: str
    ) -> Reservation | None:
        """Obtiene la reserva por su código oficial dentro del tenant."""
        statement = select(Reservation).where(
            Reservation.empresa_id == company_id,
            Reservation.codigo == code.strip().upper(),
        )
        return self.db.scalar(statement)

    def get_payment_by_key(
        self, company_id: int, idempotency_key: UUID
    ) -> Payment | None:
        """Busca un pago por su clave UUID de idempotencia."""
        statement = select(Payment).where(
            Payment.empresa_id == company_id,
            Payment.clave_idempotencia == idempotency_key,
        )
        return self.db.scalar(statement)

    def get_sale_by_number(self, company_id: int, sale_number: str) -> Sale | None:
        """Busca una venta por su número determinístico."""
        statement = select(Sale).where(
            Sale.empresa_id == company_id,
            Sale.numero_venta == sale_number,
        )
        return self.db.scalar(statement)

    def get_sale(self, company_id: int, sale_id: int) -> Sale | None:
        """Obtiene la venta por ID dentro del tenant."""
        statement = select(Sale).where(
            Sale.empresa_id == company_id,
            Sale.id_venta == sale_id,
        )
        return self.db.scalar(statement)

    def get_payment_for_sale(
        self, company_id: int, sale_id: int
    ) -> Payment | None:
        """Obtiene el pago registrado para una venta."""
        statement = (
            select(Payment)
            .where(
                Payment.empresa_id == company_id,
                Payment.id_venta == sale_id,
            )
            .order_by(Payment.id_pago.desc())
        )
        return self.db.scalar(statement)

    def get_sale_details(
        self, company_id: int, sale_id: int
    ) -> list[tuple[SaleDetail, ProductVariant | None, Product | None]]:
        """Obtiene las líneas de la venta con variante y producto."""
        statement = (
            select(SaleDetail, ProductVariant, Product)
            .outerjoin(
                ProductVariant,
                ProductVariant.id_variante_producto == SaleDetail.id_variante_producto,
            )
            .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
            .where(
                SaleDetail.empresa_id == company_id,
                SaleDetail.id_venta == sale_id,
            )
            .order_by(SaleDetail.id_detalle_venta.asc())
        )
        return self.db.execute(statement).all()

    def get_reservation_details(
        self, company_id: int, reservation_id: int
    ) -> list[tuple[ReservationDetail, ProductVariant | None, Product | None]]:
        """Obtiene las líneas de la reserva con variante y producto."""
        statement = (
            select(ReservationDetail, ProductVariant, Product)
            .outerjoin(
                ProductVariant,
                ProductVariant.id_variante_producto == ReservationDetail.id_variante_producto,
            )
            .outerjoin(Product, Product.id_producto == ProductVariant.id_producto)
            .where(
                ReservationDetail.empresa_id == company_id,
                ReservationDetail.id_reserva == reservation_id,
            )
            .order_by(ReservationDetail.id_detalle_reserva.asc())
        )
        return self.db.execute(statement).all()

    def get_branch(self, company_id: int, branch_id: int) -> Branch | None:
        """Obtiene la sucursal por ID dentro de la empresa."""
        statement = select(Branch).where(
            Branch.empresa_id == company_id,
            Branch.id_sucursal == branch_id,
        )
        return self.db.scalar(statement)

    def get_client_by_user(self, company_id: int, user_id: int) -> Client | None:
        """Obtiene el cliente vinculado al usuario autenticado."""
        statement = select(Client).where(
            Client.empresa_id == company_id,
            Client.id_usuario == user_id,
        )
        return self.db.scalar(statement)

    def get_employee_by_user(self, company_id: int, user_id: int) -> Employee | None:
        """Obtiene el empleado vinculado al usuario autenticado."""
        statement = select(Employee).where(
            Employee.empresa_id == company_id,
            Employee.id_usuario == user_id,
        )
        return self.db.scalar(statement)

    def get_employee_branch_assignment(
        self, company_id: int, employee_id: int, branch_id: int
    ) -> EmployeeBranch | None:
        """Verifica la asignación del empleado a la sucursal."""
        statement = select(EmployeeBranch).where(
            EmployeeBranch.empresa_id == company_id,
            EmployeeBranch.id_empleado == employee_id,
            EmployeeBranch.id_sucursal == branch_id,
        )
        return self.db.scalar(statement)

    def list_synced_reservations_for_user(
        self, company_id: int, user_id: int, limit: int = 50
    ) -> list[OfflineReservationSync]:
        """Lista las reservas offline sincronizadas por un usuario cliente."""
        statement = (
            select(OfflineReservationSync)
            .where(
                OfflineReservationSync.empresa_id == company_id,
                OfflineReservationSync.id_usuario == user_id,
            )
            .order_by(OfflineReservationSync.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def list_synced_reservations_for_branch(
        self, company_id: int, branch_id: int, limit: int = 50
    ) -> list[OfflineReservationSync]:
        """Lista las reservas offline sincronizadas en una sucursal."""
        statement = (
            select(OfflineReservationSync)
            .where(
                OfflineReservationSync.empresa_id == company_id,
                OfflineReservationSync.id_sucursal == branch_id,
            )
            .order_by(OfflineReservationSync.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def list_synced_sales_for_user(
        self, company_id: int, user_id: int, limit: int = 50
    ) -> list[Sale]:
        """Lista las ventas/compras offline sincronizadas por un usuario."""
        client = self.get_client_by_user(company_id, user_id)
        if client is not None:
            statement = (
                select(Sale)
                .where(
                    Sale.empresa_id == company_id,
                    Sale.id_cliente == client.id_cliente,
                )
                .order_by(Sale.id_venta.desc())
                .limit(limit)
            )
            return list(self.db.scalars(statement).all())

        employee = self.get_employee_by_user(company_id, user_id)
        if employee is not None:
            statement = (
                select(Sale)
                .where(
                    Sale.empresa_id == company_id,
                    Sale.id_empleado == employee.id_empleado,
                )
                .order_by(Sale.id_venta.desc())
                .limit(limit)
            )
            return list(self.db.scalars(statement).all())

        return []

    def list_synced_sales_for_branch(
        self, company_id: int, branch_id: int, limit: int = 50
    ) -> list[Sale]:
        """Lista las ventas offline sincronizadas en una sucursal."""
        statement = (
            select(Sale)
            .where(
                Sale.empresa_id == company_id,
                Sale.id_sucursal == branch_id,
            )
            .order_by(Sale.id_venta.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

