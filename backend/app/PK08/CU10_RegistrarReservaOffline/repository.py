"""Repositorio de persistencia para PK08 - CU10: Registrar reserva de prendas offline."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.client import Client
from app.models.offline_reservation_sync import (
    OfflineReservationSync,
    ensure_offline_reservation_sync_table,
)
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.repositories.client_reservations import HOLDING_STATES


class OfflineReservationRepository:
    """Acceso y mutación transaccional de reservas de CLIENTE y sincronización offline en PostgreSQL."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_sync_record(
        self, company_id: int, uuid_offline: str
    ) -> OfflineReservationSync | None:
        """Busca si el UUID offline ya fue registrado previamente para este tenant."""
        ensure_offline_reservation_sync_table(self.db)
        statement = select(OfflineReservationSync).where(
            OfflineReservationSync.empresa_id == company_id,
            OfflineReservationSync.uuid_reserva_offline == uuid_offline,
        )
        return self.db.scalar(statement)

    def get_branch(self, company_id: int, branch_id: int) -> Branch | None:
        """Obtiene la sucursal validando pertenencia estricta a la empresa."""
        statement = select(Branch).where(
            Branch.empresa_id == company_id,
            Branch.id_sucursal == branch_id,
        )
        return self.db.scalar(statement)

    def get_client_by_user(self, company_id: int, user_id: int) -> Client | None:
        """Obtiene el perfil de cliente vinculado al usuario autenticado dentro de la empresa."""
        statement = select(Client).where(
            Client.empresa_id == company_id,
            Client.id_usuario == user_id,
        )
        return self.db.scalar(statement)

    def get_client(self, company_id: int, client_id: int) -> Client | None:
        """Obtiene el cliente por ID dentro de la empresa."""
        statement = select(Client).where(
            Client.empresa_id == company_id,
            Client.id_cliente == client_id,
        )
        return self.db.scalar(statement)

    def get_variants_with_products(
        self, company_id: int, variant_ids: list[int]
    ) -> dict[int, tuple[ProductVariant, Product]]:
        """Obtiene variantes y sus productos padre validando pertenencia a la empresa."""
        if not variant_ids:
            return {}
        statement = (
            select(ProductVariant, Product)
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .where(
                ProductVariant.empresa_id == company_id,
                Product.empresa_id == company_id,
                ProductVariant.id_variante_producto.in_(sorted(variant_ids)),
            )
        )
        rows = self.db.execute(statement).all()
        return {row[0].id_variante_producto: (row[0], row[1]) for row in rows}

    def has_active_slot_conflict(
        self,
        *,
        company_id: int,
        branch_id: int,
        scheduled_at: datetime,
        variant_ids: list[int],
        now: datetime,
    ) -> bool:
        """Verifica si alguna variante ya está reservada en la misma sucursal y horario activo."""
        if not variant_ids:
            return False
        statement = (
            select(ReservationDetail.id_detalle_reserva)
            .join(
                Reservation,
                Reservation.id_reserva == ReservationDetail.id_reserva,
            )
            .where(
                Reservation.empresa_id == company_id,
                Reservation.id_sucursal == branch_id,
                Reservation.fecha_atencion_programada == scheduled_at,
                Reservation.estado.in_(HOLDING_STATES),
                Reservation.fecha_expiracion > now,
                ReservationDetail.id_variante_producto.in_(sorted(variant_ids)),
            )
            .limit(1)
        )
        return self.db.scalar(statement) is not None

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

    def code_exists(self, code: str) -> bool:
        """Verifica si un código de reserva ya existe en t_reserva."""
        return (
            self.db.scalar(
                select(Reservation.id_reserva).where(Reservation.codigo == code)
            )
            is not None
        )

    def get_reservation_by_id(
        self, company_id: int, reservation_id: int
    ) -> Reservation | None:
        """Obtiene una reserva por ID dentro de la empresa."""
        statement = select(Reservation).where(
            Reservation.empresa_id == company_id,
            Reservation.id_reserva == reservation_id,
        )
        return self.db.scalar(statement)

    def create_reservation(
        self,
        *,
        company_id: int,
        client_id: int,
        branch_id: int,
        code: str,
        scheduled_at: datetime,
        expires_at: datetime,
        now: datetime,
        employee_id: int | None = None,
    ) -> Reservation:
        """Crea el encabezado de la reserva del cliente en t_reserva con estado PENDIENTE."""
        reservation = Reservation(
            empresa_id=company_id,
            id_cliente=client_id,
            id_sucursal=branch_id,
            id_empleado_atencion=employee_id,
            codigo=code,
            estado="PENDIENTE",
            fecha_expiracion=expires_at,
            fecha_atencion_programada=scheduled_at,
            fecha_atencion=None,
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
        ensure_offline_reservation_sync_table(self.db)
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

    def update_sync_record(
        self,
        sync_record: OfflineReservationSync,
        *,
        reservation_id: int | None,
        reservation_code: str | None,
        branch_id: int,
        status: str,
        reason: str | None,
        details_json: str | None,
        now: datetime,
    ) -> OfflineReservationSync:
        """Actualiza un registro previo de conflicto/rechazo tras resolución autorizada en CU14 preservando el UUID original."""
        ensure_offline_reservation_sync_table(self.db)
        sync_record.id_reserva = reservation_id
        sync_record.codigo_reserva = reservation_code
        sync_record.id_sucursal = branch_id
        sync_record.estado_sincronizacion = status
        sync_record.motivo = reason
        if details_json is not None:
            sync_record.detalles_json = details_json
        sync_record.updated_at = now
        self.db.flush()
        return sync_record
