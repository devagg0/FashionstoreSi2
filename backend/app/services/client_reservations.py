"""Reglas, precios y transacciones de CU17."""

import secrets
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.client_reservations import (
    HOLDING_STATES,
    ClientReservationRepository,
)
from app.schemas.client_reservations import (
    ReservationBranchData,
    ReservationCityData,
    ReservationColorData,
    ReservationDetailData,
    ReservationItemData,
    ReservationPaginationData,
    ReservationSizeData,
    ReservationSummaryData,
)
from app.services.catalog import CatalogService


MONEY = Decimal("0.01")
RESERVATION_WINDOW_DAYS = 7


class ReservationNotFoundError(Exception):
    pass


class ReservationValidationError(Exception):
    pass


class ReservationConflictError(Exception):
    pass


class ReservationPersistenceError(Exception):
    pass


class ClientReservationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ClientReservationRepository(db)
        self.catalog = CatalogService(db)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _transaction(self, operation):
        try:
            result = operation()
            self.db.commit()
            return result
        except (
            ReservationNotFoundError,
            ReservationValidationError,
            ReservationConflictError,
            ReservationPersistenceError,
        ):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise ReservationConflictError(
                "Conflicto de integridad al procesar la reserva; reintente la operacion"
            ) from error
        except DBAPIError as error:
            self.db.rollback()
            code = getattr(error.orig, "sqlstate", None) or getattr(
                error.orig, "pgcode", None
            )
            if code in {"40001", "40P01", "55P03"}:
                raise ReservationConflictError(
                    "Conflicto concurrente; reintente la operacion"
                ) from error
            raise ReservationPersistenceError from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise ReservationPersistenceError from error
        except Exception as error:
            self.db.rollback()
            raise ReservationPersistenceError from error

    def _client(self, user_id: int):
        client = self.repository.get_client_by_user(user_id)
        if client is None:
            raise ReservationNotFoundError("Perfil de cliente no encontrado")
        return client

    @staticmethod
    def _money(value) -> Decimal:
        return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)

    @classmethod
    def _summary(cls, row) -> ReservationSummaryData:
        return ReservationSummaryData(
            id_reserva=row["id_reserva"],
            codigo=row["codigo"],
            estado=row["estado"],
            created_at=row["created_at"],
            fecha_atencion_programada=row["fecha_atencion_programada"],
            fecha_expiracion=row["fecha_expiracion"],
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
            cancelable=row["estado"] in HOLDING_STATES,
        )

    @classmethod
    def _detail_data(cls, row) -> ReservationDetailData:
        summary = cls._summary(row)
        items = [
            ReservationItemData(
                id_variante_producto=item["id_variante_producto"],
                sku=item["sku"],
                id_producto=item["id_producto"],
                producto=item["producto"],
                imagen_principal=item["imagen_principal"],
                talla=ReservationSizeData(
                    id_talla=item["id_talla"], nombre=item["talla"]
                ),
                color=ReservationColorData(
                    id_color=item["id_color"],
                    nombre=item["color"],
                    codigo_hex=item["codigo_hex"],
                ),
                cantidad=item["cantidad"],
                precio_unitario=cls._money(item["precio_unitario"]),
                subtotal=cls._money(
                    item["cantidad"] * item["precio_unitario"]
                ),
            )
            for item in row["items"]
        ]
        return ReservationDetailData(**summary.model_dump(), items=items)

    def _get_detail(self, reservation_id: int, client_id: int):
        row = self.repository.get_detail(reservation_id, client_id)
        if row is None:
            raise ReservationNotFoundError("Reserva no encontrada")
        return self._detail_data(row)

    def _reservation_code(self, now: datetime) -> str:
        for _ in range(10):
            code = f"RSV-{now:%Y%m%d}-{secrets.token_hex(5).upper()}"
            if not self.repository.code_exists(code):
                return code
        raise ReservationConflictError(
            "No fue posible generar un codigo unico; reintente la operacion"
        )

    @staticmethod
    def _seconds(value: time) -> int:
        return value.hour * 3600 + value.minute * 60 + value.second

    @classmethod
    def _valid_slot(cls, value: time, opening: time, closing: time) -> bool:
        """Valida un slot desde apertura, incluso en horarios que cruzan medianoche."""
        day = 24 * 60 * 60
        opening_seconds = cls._seconds(opening)
        schedule_seconds = (cls._seconds(closing) - opening_seconds) % day
        selected_offset = (cls._seconds(value) - opening_seconds) % day
        slot_seconds = settings.RESERVATION_SLOT_MINUTES * 60
        return (
            value.second == 0
            and value.microsecond == 0
            and selected_offset % slot_seconds == 0
            and selected_offset + slot_seconds <= schedule_seconds
        )

    def _scheduled_utc(self, branch, value: datetime, now: datetime) -> datetime:
        if branch.hora_apertura is None or branch.hora_cierre is None:
            raise ReservationValidationError(
                "La sucursal no tiene un horario de atencion completo configurado"
            )
        if branch.hora_apertura == branch.hora_cierre:
            raise ReservationValidationError(
                "El horario de atencion de la sucursal es ambiguo"
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReservationValidationError(
                "La fecha de atencion programada debe incluir zona horaria"
            )
        try:
            application_timezone = ZoneInfo(settings.APP_TIMEZONE)
        except ZoneInfoNotFoundError as error:
            raise ReservationPersistenceError(
                "La zona horaria de la aplicacion no esta configurada correctamente"
            ) from error
        local_value = value.astimezone(application_timezone)
        if value.utcoffset() != local_value.utcoffset():
            raise ReservationValidationError(
                "La fecha de atencion debe usar la zona horaria de Bolivia"
            )
        local_now = now.replace(tzinfo=timezone.utc).astimezone(application_timezone)
        last_allowed_date = local_now.date() + timedelta(
            days=RESERVATION_WINDOW_DAYS - 1
        )
        if not local_now.date() <= local_value.date() <= last_allowed_date:
            raise ReservationValidationError(
                "La fecha de atencion debe estar dentro de los proximos 7 dias"
            )
        scheduled_at = local_value.astimezone(timezone.utc).replace(tzinfo=None)
        if scheduled_at <= now:
            raise ReservationValidationError(
                "La fecha de atencion programada debe ser futura"
            )
        local_time = local_value.timetz().replace(tzinfo=None)
        if not self._valid_slot(
            local_time, branch.hora_apertura, branch.hora_cierre
        ):
            raise ReservationValidationError(
                "La hora programada debe ser un slot valido de 30 minutos dentro del horario de la sucursal"
            )
        return scheduled_at

    def create_reservation(self, user_id: int, payload):
        def operation():
            client = self._client(user_id)
            branch = self.repository.get_branch(payload.id_sucursal)
            if branch is None:
                raise ReservationNotFoundError("Sucursal no encontrada")
            if not branch.estado:
                raise ReservationValidationError("La sucursal esta inactiva")
            now = self._now()
            scheduled_at = self._scheduled_utc(
                branch, payload.fecha_atencion_programada, now
            )

            quantities = {}
            product_ids = {}
            for item in payload.items:
                if item.id_variante_producto in quantities:
                    raise ReservationValidationError(
                        "La variante esta repetida en la reserva"
                    )
                row = self.repository.get_variant(item.id_variante_producto)
                if row is None:
                    raise ReservationNotFoundError("Variante no encontrada")
                variant, product = row
                if not variant.estado or not product.estado:
                    raise ReservationValidationError(
                        "La variante o su producto estan inactivos"
                    )
                quantities[item.id_variante_producto] = item.cantidad
                product_ids[item.id_variante_producto] = product.id_producto

            variant_ids = sorted(quantities)
            inventories = self.repository.lock_inventories(
                payload.id_sucursal, variant_ids
            )
            inventory_by_variant = {
                inventory.id_variante_producto: inventory
                for inventory in inventories
            }
            if set(inventory_by_variant) != set(variant_ids):
                raise ReservationNotFoundError(
                    "No existe inventario para una variante en la sucursal"
                )
            for variant_id in variant_ids:
                inventory = inventory_by_variant[variant_id]
                available = inventory.stock_actual - inventory.stock_reservado
                if quantities[variant_id] > available:
                    raise ReservationConflictError(
                        "Stock disponible insuficiente para completar la reserva"
                    )

            prices = {}
            for product_id in sorted(set(product_ids.values())):
                product = self.catalog.get_product(product_id, branch_id=None)
                prices[product_id] = self._money(product.precio_final)

            for variant_id in variant_ids:
                inventory = inventory_by_variant[variant_id]
                inventory.stock_reservado += quantities[variant_id]
                inventory.updated_at = now

            reservation = self.repository.create_reservation(
                client_id=client.id_cliente,
                branch_id=payload.id_sucursal,
                code=self._reservation_code(now),
                scheduled_at=scheduled_at,
                expires_at=scheduled_at
                + timedelta(minutes=settings.RESERVATION_GRACE_MINUTES),
            )
            self.repository.create_details(
                reservation.id_reserva,
                [
                    {
                        "id_variante_producto": variant_id,
                        "cantidad": quantities[variant_id],
                        "precio_unitario": prices[product_ids[variant_id]],
                    }
                    for variant_id in variant_ids
                ],
            )
            self.db.flush()
            return self._get_detail(reservation.id_reserva, client.id_cliente)

        return self._transaction(operation)

    def _release(self, reservation, now: datetime):
        details = self.repository.get_details(reservation.id_reserva)
        if not details:
            raise ReservationConflictError(
                "La reserva no tiene detalles y no puede liberar inventario"
            )
        variant_ids = sorted(
            detail.id_variante_producto for detail in details
        )
        inventories = self.repository.lock_inventories(
            reservation.id_sucursal, variant_ids
        )
        inventory_by_variant = {
            inventory.id_variante_producto: inventory
            for inventory in inventories
        }
        if set(inventory_by_variant) != set(variant_ids):
            raise ReservationConflictError(
                "El inventario asociado a la reserva ya no esta disponible"
            )
        for detail in details:
            inventory = inventory_by_variant[detail.id_variante_producto]
            if inventory.stock_reservado < detail.cantidad:
                raise ReservationConflictError(
                    "El stock reservado es inconsistente; no se libero inventario"
                )
        for detail in details:
            inventory = inventory_by_variant[detail.id_variante_producto]
            inventory.stock_reservado -= detail.cantidad
            inventory.updated_at = now

    def _expire_locked(self, reservation, now: datetime) -> bool:
        if (
            reservation.estado not in HOLDING_STATES
            or reservation.fecha_expiracion > now
        ):
            return False
        self._release(reservation, now)
        reservation.estado = "EXPIRADA"
        reservation.updated_at = now
        self.db.flush()
        return True

    def _expire_due(self, client_id: int, now: datetime):
        for reservation_id in self.repository.list_due_ids(client_id, now):
            reservation = self.repository.get_owned_reservation(
                reservation_id, client_id, for_update=True
            )
            if reservation is not None:
                self._expire_locked(reservation, now)

    def list_reservations(
        self, user_id: int, *, state=None, page=1, page_size=20
    ):
        def operation():
            client = self._client(user_id)
            self._expire_due(client.id_cliente, self._now())
            rows, total = self.repository.list_reservations(
                client.id_cliente, state=state, page=page, page_size=page_size
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
            client = self._client(user_id)
            reservation = self.repository.get_owned_reservation(
                reservation_id, client.id_cliente, for_update=True
            )
            if reservation is None:
                raise ReservationNotFoundError("Reserva no encontrada")
            self._expire_locked(reservation, self._now())
            return self._get_detail(reservation_id, client.id_cliente)

        return self._transaction(operation)

    def cancel_reservation(self, user_id: int, reservation_id: int):
        expired = False

        def operation():
            nonlocal expired
            client = self._client(user_id)
            reservation = self.repository.get_owned_reservation(
                reservation_id, client.id_cliente, for_update=True
            )
            if reservation is None:
                raise ReservationNotFoundError("Reserva no encontrada")
            now = self._now()
            expired = self._expire_locked(reservation, now)
            if not expired:
                if reservation.estado not in HOLDING_STATES:
                    raise ReservationConflictError(
                        "La reserva ya no se puede cancelar"
                    )
                self._release(reservation, now)
                reservation.estado = "CANCELADA"
                reservation.updated_at = now
                self.db.flush()
            return self._get_detail(reservation_id, client.id_cliente)

        result = self._transaction(operation)
        if expired:
            raise ReservationConflictError(
                "La reserva vencio y fue marcada como EXPIRADA"
            )
        return result
