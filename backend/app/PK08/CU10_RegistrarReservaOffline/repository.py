"""Repositorio de persistencia para PK08 - CU10: Registrar reserva de prendas offline."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.client import Client
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.offline_reservation_sync import OfflineReservationSync
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail


class OfflineReservationRepository:
    """Acceso y mutación transaccional de reservas y sincronización offline en PostgreSQL."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_sync_record(
        self, company_id: int, uuid_offline: str
    ) -> OfflineReservationSync | None:
        """Busca si el UUID offline ya fue registrado previamente para este tenant."""
        statement = select(OfflineReservationSync).where(
            OfflineReservationSync.empresa_id == company_id,
            OfflineReservationSync.uuid_reserva_offline == uuid_offline,
        )
        return self.db.scalar(statement)

    def get_branch(self, company_id: int, branch_id: int) -> Branch | None:
        """Obtiene la sucursal validando pertenencia a la empresa."""
        statement = select(Branch).where(
            Branch.empresa_id == company_id,
            Branch.id_sucursal == branch_id,
        )
        return self.db.scalar(statement)

    def get_employee_for_user(
        self, company_id: int, user_id: int
    ) -> Employee | None:
        """Obtiene el empleado vinculado al usuario en la empresa."""
        statement = select(Employee).where(
            Employee.empresa_id == company_id,
            Employee.id_usuario == user_id,
        )
        return self.db.scalar(statement)

    def is_employee_assigned_to_branch(
        self, company_id: int, employee_id: int, branch_id: int
    ) -> bool:
        """Verifica que el empleado tenga asignación activa a la sucursal."""
        statement = select(EmployeeBranch).where(
            EmployeeBranch.empresa_id == company_id,
            EmployeeBranch.id_empleado == employee_id,
            EmployeeBranch.id_sucursal == branch_id,
            EmployeeBranch.estado.is_(True),
        )
        return self.db.scalar(statement) is not None

    def get_client(self, company_id: int, client_id: int) -> Client | None:
        """Obtiene el cliente dentro de la empresa."""
        statement = select(Client).where(
            Client.empresa_id == company_id,
            Client.id_cliente == client_id,
        )
        return self.db.scalar(statement)

    def get_variants_with_products(
        self, company_id: int, variant_ids: list[int]
    ) -> dict[int, tuple[ProductVariant, Product]]:
        """Obtiene variantes y sus productos padre para validar pertenencia a la empresa y precios."""
        if not variant_ids:
            return {}
        statement = (
            select(ProductVariant, Product)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .where(
                ProductVariant.empresa_id == company_id,
                ProductVariant.id_variante_producto.in_(sorted(variant_ids)),
            )
        )
        rows = self.db.execute(statement).all()
        return {row[0].id_variante_producto: (row[0], row[1]) for row in rows}

    def lock_inventories(
        self, company_id: int, branch_id: int, variant_ids: list[int]
    ) -> dict[int, BranchInventory]:
        """Bloquea concurrentemente las filas de inventario para las variantes solicitadas."""
        if not variant_ids:
            return {}
        statement = (
            select(BranchInventory)
            .where(
                BranchInventory.empresa_id == company_id,
                BranchInventory.id_sucursal == branch_id,
                BranchInventory.id_variante_producto.in_(sorted(variant_ids)),
            )
            .order_by(BranchInventory.id_variante_producto)
            .with_for_update()
        )
        inventories = self.db.scalars(statement).all()
        return {inv.id_variante_producto: inv for inv in inventories}

    def create_reservation(
        self,
        *,
        company_id: int,
        client_id: int,
        branch_id: int,
        employee_id: int | None,
        code: str,
        scheduled_at: datetime,
        expires_at: datetime,
        now: datetime,
    ) -> Reservation:
        """Crea el encabezado de la reserva en t_reserva."""
        reservation = Reservation(
            empresa_id=company_id,
            id_cliente=client_id,
            id_sucursal=branch_id,
            id_empleado_atencion=employee_id,
            codigo=code,
            estado="PENDIENTE",
            fecha_expiracion=expires_at,
            fecha_atencion_programada=scheduled_at,
            created_at=now,
            updated_at=now,
        )
        self.db.add(reservation)
        self.db.flush()
        return reservation

    def create_reservation_detail(
        self,
        *,
        company_id: int,
        reservation_id: int,
        variant_id: int,
        quantity: int,
        unit_price: Decimal,
    ) -> ReservationDetail:
        """Crea una línea de detalle de prenda reservada en t_detalle_reserva."""
        detail = ReservationDetail(
            empresa_id=company_id,
            id_reserva=reservation_id,
            id_variante_producto=variant_id,
            cantidad=quantity,
            precio_unitario=unit_price,
        )
        self.db.add(detail)
        return detail

    def create_sync_record(
        self,
        *,
        company_id: int,
        uuid_offline: str,
        reservation_id: int | None,
        reservation_code: str | None,
        branch_id: int,
        client_id: int,
        user_id: int,
        status: str,
        reason: str | None,
        details_json: str | None,
        offline_date: datetime,
        now: datetime,
    ) -> OfflineReservationSync:
        """Registra el resultado de sincronización para control de idempotencia estricto."""
        sync_record = OfflineReservationSync(
            empresa_id=company_id,
            uuid_reserva_offline=uuid_offline,
            id_reserva=reservation_id,
            codigo_reserva=reservation_code,
            id_sucursal=branch_id,
            id_cliente=client_id,
            id_usuario=user_id,
            estado_sincronizacion=status,
            motivo=reason,
            detalles_json=details_json,
            fecha_reserva_offline=offline_date,
            created_at=now,
            updated_at=now,
        )
        self.db.add(sync_record)
        self.db.flush()
        return sync_record

