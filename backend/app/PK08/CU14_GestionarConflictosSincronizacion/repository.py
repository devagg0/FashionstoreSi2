"""Repositorio de soporte para PK08 - CU14: Gestionar conflictos y resultados de sincronización."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch_inventory import BranchInventory
from app.models.offline_reservation_sync import (
    OfflineReservationSync,
    ensure_offline_reservation_sync_table,
)


class OfflineConflictRepository:
    """Consultas de solo lectura de inventario y persistencia de descartes para CU14."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_inventories_snapshot(
        self, company_id: int, branch_id: int, variant_ids: list[int]
    ) -> dict[int, BranchInventory]:
        """Consulta el inventario actual de la sucursal sin bloquear filas (para diagnóstico CU14)."""
        if not variant_ids:
            return {}
        statement = select(BranchInventory).where(
            BranchInventory.empresa_id == company_id,
            BranchInventory.id_sucursal == branch_id,
            BranchInventory.id_variante_producto.in_(sorted(variant_ids)),
        )
        rows = self.db.scalars(statement).all()
        return {inv.id_variante_producto: inv for inv in rows}

    def mark_reservation_sync_discarded(
        self,
        *,
        company_id: int,
        uuid_offline: str,
        branch_id: int,
        client_id: int,
        user_id: int,
        reason: str,
        now: datetime,
    ) -> OfflineReservationSync:
        """Registra o actualiza una reserva offline como descartada voluntariamente por el cliente (RECHAZADA)."""
        ensure_offline_reservation_sync_table(self.db)
        existing = self.db.scalar(
            select(OfflineReservationSync).where(
                OfflineReservationSync.empresa_id == company_id,
                OfflineReservationSync.uuid_reserva_offline == uuid_offline,
            )
        )
        if existing is not None:
            if getattr(existing, "id_reserva", None) is None:
                existing.estado_sincronizacion = "RECHAZADA"
                existing.motivo = reason
                existing.updated_at = now
                self.db.flush()
            return existing

        sync_row = OfflineReservationSync(
            empresa_id=company_id,
            uuid_reserva_offline=uuid_offline,
            id_reserva=None,
            codigo_reserva=None,
            id_sucursal=branch_id,
            id_cliente=client_id,
            id_usuario=user_id,
            estado_sincronizacion="RECHAZADA",
            motivo=reason,
            detalles_json=None,
            fecha_reserva_offline=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(sync_row)
        self.db.flush()
        return sync_row

