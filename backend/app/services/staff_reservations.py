"""Reglas y transacciones de CU18 para personal de sucursal."""

from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.staff_reservations import StaffReservationRepository
from app.schemas.client_reservations import (
    ReservationBranchData,
    ReservationCityData,
    ReservationColorData,
    ReservationPaginationData,
    ReservationSizeData,
)
from app.schemas.staff_reservations import (
    StaffReservationClientData,
    StaffReservationDetailData,
    StaffReservationItemData,
    StaffReservationSummaryData,
)
from app.services.client_reservations import (
    ClientReservationService,
    ReservationConflictError,
    ReservationNotFoundError,
    ReservationPersistenceError,
    ReservationValidationError,
)


class StaffReservationAccessError(ReservationValidationError):
    pass


class StaffReservationService(ClientReservationService):
    """Reutiliza el ciclo de expiracion de CU17 y agrega ownership por sucursal."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = StaffReservationRepository(db)

    def _staff_context(self, user_id: int, *, for_update: bool = False):
        employee = self.repository.get_employee_by_user(user_id)
        if employee is None:
            raise StaffReservationAccessError("Perfil de empleado no encontrado")
        branch_ids = self.repository.list_active_branch_ids(
            employee.id_empleado, for_update=for_update
        )
        if not branch_ids:
            raise StaffReservationAccessError(
                "El empleado no tiene una asignacion activa a sucursal"
            )
        return employee, branch_ids

    @staticmethod
    def _scheduled_bounds(value: date | None):
        if value is None:
            return None, None
        try:
            application_timezone = ZoneInfo(settings.APP_TIMEZONE)
        except ZoneInfoNotFoundError as error:
            raise ReservationPersistenceError(
                "La zona horaria de la aplicacion no esta configurada correctamente"
            ) from error
        start_local = datetime.combine(value, time.min, tzinfo=application_timezone)
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(timezone.utc).replace(tzinfo=None),
            end_local.astimezone(timezone.utc).replace(tzinfo=None),
        )

    @classmethod
    def _summary(cls, row):
        return StaffReservationSummaryData(
            id_reserva=row["id_reserva"],
            codigo=row["codigo"],
            estado=row["estado"],
            created_at=row["created_at"],
            fecha_atencion_programada=row["fecha_atencion_programada"],
            fecha_expiracion=row["fecha_expiracion"],
            fecha_atencion=row["fecha_atencion"],
            cliente=StaffReservationClientData(
                id_cliente=row["id_cliente"],
                nombre=row["cliente_nombre"],
                apellido=row["cliente_apellido"],
                correo=row["cliente_correo"],
                telefono=row["cliente_telefono"],
            ),
            sucursal=ReservationBranchData(
                id_sucursal=row["id_sucursal"],
                nombre=row["sucursal"],
                direccion=row["direccion"],
                ciudad=ReservationCityData(
                    id_ciudad=row["id_ciudad"], nombre=row["ciudad"]
                ),
            ),
            cantidad_prendas=int(row["cantidad_prendas"]),
            total=cls._money(row["total"]),
        )

    @classmethod
    def _detail_data(cls, row):
        summary = cls._summary(row)
        items = [
            StaffReservationItemData(
                id_variante_producto=item["id_variante_producto"],
                sku=item["sku"],
                id_producto=item["id_producto"],
                producto=item["producto"],
                talla=ReservationSizeData(
                    id_talla=item["id_talla"], nombre=item["talla"]
                ),
                color=ReservationColorData(
                    id_color=item["id_color"],
                    nombre=item["color"],
                    codigo_hex=item["codigo_hex"],
                ),
                cantidad=item["cantidad"],
                precio_reservado=cls._money(item["precio_unitario"]),
                subtotal=cls._money(item["cantidad"] * item["precio_unitario"]),
            )
            for item in row["items"]
        ]
        return StaffReservationDetailData(**summary.model_dump(), prendas=items)

    def _get_detail(self, reservation_id: int, branch_ids: list[int]):
        row = self.repository.get_detail(reservation_id, branch_ids)
        if row is None:
            raise ReservationNotFoundError("Reserva no encontrada")
        return self._detail_data(row)

    def _expire_due(self, branch_ids: list[int], now: datetime):
        for reservation_id in self.repository.list_due_ids(branch_ids, now):
            reservation = self.repository.get_scoped_reservation(
                reservation_id, branch_ids, for_update=True
            )
            if reservation is not None:
                self._expire_locked(reservation, now)

    def list_reservations(
        self, user_id: int, *, state=None, scheduled_date=None, page=1, page_size=20
    ):
        def operation():
            _, branch_ids = self._staff_context(user_id)
            now = self._now()
            self._expire_due(branch_ids, now)
            scheduled_from, scheduled_until = self._scheduled_bounds(scheduled_date)
            rows, total = self.repository.list_reservations(
                branch_ids,
                state=state,
                scheduled_from=scheduled_from,
                scheduled_until=scheduled_until,
                page=page,
                page_size=page_size,
            )
            return (
                [self._summary(row) for row in rows],
                ReservationPaginationData(
                    page=page,
                    page_size=page_size,
                    total=total,
                    total_pages=ceil(total / page_size) if total else 0,
                ),
            )

        return self._transaction(operation)

    def get_reservation(self, user_id: int, reservation_id: int):
        def operation():
            _, branch_ids = self._staff_context(user_id)
            reservation = self.repository.get_scoped_reservation(
                reservation_id, branch_ids, for_update=True
            )
            if reservation is None:
                raise ReservationNotFoundError("Reserva no encontrada")
            self._expire_locked(reservation, self._now())
            return self._get_detail(reservation_id, branch_ids)

        return self._transaction(operation)

    def get_reservation_by_code(self, user_id: int, code: str):
        def operation():
            _, branch_ids = self._staff_context(user_id)
            reservation = self.repository.get_scoped_reservation_by_code(
                code.strip().upper(), branch_ids, for_update=True
            )
            if reservation is None:
                raise ReservationNotFoundError("Reserva no encontrada")
            self._expire_locked(reservation, self._now())
            return self._get_detail(reservation.id_reserva, branch_ids)

        return self._transaction(operation)

    def _transition(self, user_id: int, reservation_id: int, source: str, target: str):
        expired = False

        def operation():
            nonlocal expired
            employee, branch_ids = self._staff_context(user_id, for_update=True)
            reservation = self.repository.get_scoped_reservation(
                reservation_id, branch_ids, for_update=True
            )
            if reservation is None:
                raise ReservationNotFoundError("Reserva no encontrada")
            now = self._now()
            expired = self._expire_locked(reservation, now)
            if not expired:
                if reservation.estado != source:
                    raise ReservationConflictError(
                        f"Transicion invalida: se requiere estado {source}"
                    )
                reservation.estado = target
                reservation.updated_at = now
                if target == "ATENDIDA":
                    reservation.id_empleado_atencion = employee.id_empleado
                    reservation.fecha_atencion = now
                self.db.flush()
            return self._get_detail(reservation_id, branch_ids)

        result = self._transaction(operation)
        if expired:
            raise ReservationConflictError(
                "La reserva vencio y fue marcada como EXPIRADA"
            )
        return result

    def confirm_reservation(self, user_id: int, reservation_id: int):
        return self._transition(user_id, reservation_id, "PENDIENTE", "CONFIRMADA")

    def attend_reservation(self, user_id: int, reservation_id: int):
        return self._transition(user_id, reservation_id, "CONFIRMADA", "ATENDIDA")
