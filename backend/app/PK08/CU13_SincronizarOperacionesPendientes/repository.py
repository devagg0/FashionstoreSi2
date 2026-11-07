"""Repositorio de soporte para PK08 - CU13: Sincronizar operaciones pendientes de FashionStore."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.offline_reservation_sync import (
    OfflineReservationSync,
    ensure_offline_reservation_sync_table,
)
from app.models.reservation import Reservation


class OfflineSyncQueueRepository:
    """Resuelve referencias cruzadas entre UUIDs/códigos locales offline y registros oficiales en PostgreSQL."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve_reservation_reference(
        self,
        company_id: int,
        *,
        uuid_offline: str | None = None,
        code: str | None = None,
        reservation_id: int | None = None,
    ) -> tuple[int, str] | None:
        """Vincula un UUID offline o código local con el (id_reserva, codigo_oficial) en PostgreSQL."""
        ensure_offline_reservation_sync_table(self.db)
        if reservation_id is not None and reservation_id < 70000000:
            res = self.db.scalar(
                select(Reservation).where(
                    Reservation.empresa_id == company_id,
                    Reservation.id_reserva == reservation_id,
                )
            )
            if res is not None and getattr(res, "id_reserva", None):
                return (res.id_reserva, getattr(res, "codigo", None) or str(res.id_reserva))

        for candidate_uuid in (uuid_offline, code):
            if not candidate_uuid:
                continue
            cleaned = candidate_uuid.strip()
            sync_row = self.db.scalar(
                select(OfflineReservationSync).where(
                    OfflineReservationSync.empresa_id == company_id,
                    OfflineReservationSync.uuid_reserva_offline == cleaned,
                )
            )
            if sync_row is not None and getattr(sync_row, "id_reserva", None):
                official_code = getattr(sync_row, "codigo_reserva", None)
                if not official_code:
                    res = self.db.scalar(
                        select(Reservation).where(
                            Reservation.empresa_id == company_id,
                            Reservation.id_reserva == sync_row.id_reserva,
                        )
                    )
                    official_code = getattr(res, "codigo", None) if res else None
                return (
                    sync_row.id_reserva,
                    official_code or f"RSV-{sync_row.id_reserva}",
                )

        if code:
            cleaned_code = code.strip().upper()
            res = self.db.scalar(
                select(Reservation).where(
                    Reservation.empresa_id == company_id,
                    Reservation.codigo == cleaned_code,
                )
            )
            if res is not None and getattr(res, "id_reserva", None):
                return (res.id_reserva, getattr(res, "codigo", cleaned_code))

        return None

    def get_branch_name(self, company_id: int, branch_id: int | None) -> str | None:
        """Obtiene el nombre legible de la sucursal dentro del tenant."""
        if not branch_id:
            return None
        branch = self.db.scalar(
            select(Branch).where(
                Branch.empresa_id == company_id,
                Branch.id_sucursal == branch_id,
            )
        )
        return getattr(branch, "nombre", None) if branch is not None else None

