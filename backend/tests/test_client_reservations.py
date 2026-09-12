"""CU17: reglas, ownership, stock reservado, expiracion y bloqueos."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.dialects import postgresql

from app.repositories.client_reservations import ClientReservationRepository
from app.routers.client_reservations import require_client
from app.schemas.client_reservations import ReservationCreateRequest
from app.services.client_reservations import (
    ClientReservationService,
    ReservationConflictError,
    ReservationNotFoundError,
    ReservationValidationError,
)


NOW = datetime(2026, 9, 11, 12, 0, 0)
SCHEDULED_INPUT = datetime.fromisoformat("2026-09-11T16:00:00-04:00")
SCHEDULED_UTC = datetime(2026, 9, 11, 20, 0, 0)


def payload(**changes):
    values = {
        "id_sucursal": 2,
        "fecha_atencion_programada": SCHEDULED_INPUT,
        "items": [{"id_variante_producto": 3, "cantidad": 2}],
    }
    values.update(changes)
    return ReservationCreateRequest(**values)


class ClientReservationServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = ClientReservationService(self.db)
        self.repo = MagicMock()
        self.service.repository = self.repo
        self.service.catalog = MagicMock()
        self.service._now = MagicMock(return_value=NOW)
        self.client = SimpleNamespace(id_cliente=7, id_usuario=11)
        self.branch = SimpleNamespace(
            id_sucursal=2,
            estado=True,
            hora_apertura=time(8),
            hora_cierre=time(20),
        )
        self.variant = SimpleNamespace(id_variante_producto=3, estado=True)
        self.product = SimpleNamespace(id_producto=4, estado=True)
        self.inventory = SimpleNamespace(
            id_variante_producto=3,
            stock_actual=10,
            stock_reservado=3,
            updated_at=None,
        )
        self.reservation = SimpleNamespace(
            id_reserva=9,
            id_cliente=7,
            id_sucursal=2,
            codigo="RSV-20260911-ABCDEF1234",
            estado="PENDIENTE",
            created_at=NOW,
            fecha_atencion_programada=SCHEDULED_UTC,
            fecha_expiracion=SCHEDULED_UTC + timedelta(minutes=60),
            updated_at=NOW,
        )
        self.detail = SimpleNamespace(id_variante_producto=3, cantidad=2)
        self.repo.get_client_by_user.return_value = self.client
        self.repo.get_branch.return_value = self.branch
        self.repo.get_variant.return_value = (self.variant, self.product)
        self.repo.lock_inventories.return_value = [self.inventory]
        self.repo.code_exists.return_value = False
        self.repo.create_reservation.return_value = self.reservation
        self.repo.get_owned_reservation.return_value = self.reservation
        self.repo.get_details.return_value = [self.detail]
        self.repo.list_due_ids.return_value = []
        self.service.catalog.get_product.return_value = SimpleNamespace(
            precio_final=Decimal("79.90")
        )
        self.repo.get_detail.side_effect = lambda *_: self._detail_row()

    def _detail_row(self, *, reservation=None, items=None):
        reservation = reservation or self.reservation
        return {
            "id_reserva": reservation.id_reserva,
            "codigo": reservation.codigo,
            "estado": reservation.estado,
            "created_at": reservation.created_at,
            "fecha_atencion_programada": reservation.fecha_atencion_programada,
            "fecha_expiracion": reservation.fecha_expiracion,
            "id_sucursal": 2,
            "sucursal": "Centro",
            "direccion": "Av. Principal 1",
            "id_ciudad": 1,
            "ciudad": "La Paz",
            "cantidad_prendas": 2,
            "total": Decimal("159.80"),
            "items": items
            or [
                {
                    "id_variante_producto": 3,
                    "sku": "CAM-M-NEG",
                    "id_producto": 4,
                    "producto": "Camisa",
                    "imagen_principal": "https://example.test/camisa.jpg",
                    "id_talla": 1,
                    "talla": "M",
                    "id_color": 2,
                    "color": "Negro",
                    "codigo_hex": "#000000",
                    "cantidad": 2,
                    "precio_unitario": Decimal("79.90"),
                }
            ],
        }

    def test_create_increments_reserved_and_commits_once(self):
        result = self.service.create_reservation(11, payload())
        self.assertEqual(self.inventory.stock_reservado, 5)
        self.assertEqual(self.inventory.stock_actual, 10)
        self.assertEqual(result.total, Decimal("159.80"))
        created = self.repo.create_reservation.call_args.kwargs
        self.assertEqual(created["scheduled_at"], SCHEDULED_UTC)
        self.assertEqual(created["expires_at"], SCHEDULED_UTC + timedelta(minutes=60))
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()

    def test_scheduled_date_must_be_future(self):
        with self.assertRaisesRegex(ReservationValidationError, "debe ser futura"):
            self.service.create_reservation(
                11,
                payload(
                    fecha_atencion_programada=datetime.fromisoformat(
                        "2026-09-11T07:59:00-04:00"
                    )
                ),
            )
        self.repo.lock_inventories.assert_not_called()

    def test_scheduled_date_requires_timezone(self):
        with self.assertRaisesRegex(ReservationValidationError, "zona horaria"):
            self.service.create_reservation(
                11, payload(fecha_atencion_programada=datetime(2026, 9, 12, 10))
            )

    def test_hour_before_opening_is_rejected(self):
        with self.assertRaisesRegex(ReservationValidationError, "horario"):
            self.service.create_reservation(
                11,
                payload(
                    fecha_atencion_programada=datetime.fromisoformat(
                        "2026-09-12T07:30:00-04:00"
                    )
                ),
            )

    def test_valid_1630_bolivia_slot_is_accepted_without_changing_wall_time(self):
        self.service.create_reservation(
            11,
            payload(
                fecha_atencion_programada=datetime.fromisoformat(
                    "2026-09-13T16:30:00-04:00"
                )
            ),
        )
        created = self.repo.create_reservation.call_args.kwargs
        self.assertEqual(created["scheduled_at"], datetime(2026, 9, 13, 20, 30))

    def test_non_half_hour_value_is_rejected(self):
        with self.assertRaisesRegex(ReservationValidationError, "slot valido"):
            self.service.create_reservation(
                11,
                payload(
                    fecha_atencion_programada=datetime.fromisoformat(
                        "2026-09-13T16:45:00-04:00"
                    )
                ),
            )

    def test_only_the_next_seven_local_dates_are_allowed(self):
        for value in (
            "2026-09-10T16:30:00-04:00",
            "2026-09-18T16:30:00-04:00",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                ReservationValidationError, "proximos 7 dias"
            ):
                self.service.create_reservation(
                    11,
                    payload(fecha_atencion_programada=datetime.fromisoformat(value)),
                )

    def test_timestamp_offset_must_match_application_timezone(self):
        with self.assertRaisesRegex(ReservationValidationError, "Bolivia"):
            self.service.create_reservation(
                11,
                payload(
                    fecha_atencion_programada=datetime.fromisoformat(
                        "2026-09-13T16:30:00-03:00"
                    )
                ),
            )

    def test_last_slot_must_finish_before_branch_closes(self):
        self.branch.hora_cierre = time(22, 50)
        self.service.create_reservation(
            11,
            payload(
                fecha_atencion_programada=datetime.fromisoformat(
                    "2026-09-13T22:00:00-04:00"
                )
            ),
        )
        self.db.reset_mock()
        with self.assertRaisesRegex(ReservationValidationError, "slot valido"):
            self.service.create_reservation(
                11,
                payload(
                    fecha_atencion_programada=datetime.fromisoformat(
                        "2026-09-13T22:30:00-04:00"
                    )
                ),
            )

    def test_hour_at_or_after_closing_is_rejected(self):
        for value in ("2026-09-12T20:00:00-04:00", "2026-09-12T22:00:00-04:00"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ReservationValidationError, "horario"
            ):
                self.service.create_reservation(
                    11,
                    payload(fecha_atencion_programada=datetime.fromisoformat(value)),
                )

    def test_missing_or_ambiguous_branch_hours_are_rejected(self):
        for opening, closing in ((None, time(20)), (time(8), None), (time(8), time(8))):
            self.branch.hora_apertura = opening
            self.branch.hora_cierre = closing
            with self.subTest(opening=opening, closing=closing), self.assertRaises(
                ReservationValidationError
            ):
                self.service.create_reservation(11, payload())

    def test_overnight_branch_hours_are_supported(self):
        self.branch.hora_apertura = time(22)
        self.branch.hora_cierre = time(6)
        self.service.create_reservation(
            11,
            payload(
                fecha_atencion_programada=datetime.fromisoformat(
                    "2026-09-12T01:00:00-04:00"
                )
            ),
        )
        self.db.commit.assert_called_once()

    def test_multiple_details_are_locked_in_deterministic_order(self):
        second_variant = SimpleNamespace(id_variante_producto=1, estado=True)
        second_product = SimpleNamespace(id_producto=8, estado=True)
        second_inventory = SimpleNamespace(
            id_variante_producto=1,
            stock_actual=5,
            stock_reservado=0,
            updated_at=None,
        )
        self.repo.get_variant.side_effect = [
            (self.variant, self.product),
            (second_variant, second_product),
        ]
        self.repo.lock_inventories.return_value = [second_inventory, self.inventory]
        self.service.catalog.get_product.side_effect = [
            SimpleNamespace(precio_final=Decimal("20")),
            SimpleNamespace(precio_final=Decimal("79.90")),
        ]
        request = payload(
            items=[
                {"id_variante_producto": 3, "cantidad": 2},
                {"id_variante_producto": 1, "cantidad": 1},
            ]
        )
        self.service.create_reservation(11, request)
        self.repo.lock_inventories.assert_called_once_with(2, [1, 3])
        self.assertEqual((second_inventory.stock_reservado, self.inventory.stock_reservado), (1, 5))

    def test_price_is_snapshot_from_catalog(self):
        self.service.create_reservation(11, payload())
        created = self.repo.create_details.call_args.args[1][0]
        self.assertEqual(created["precio_unitario"], Decimal("79.90"))
        self.service.catalog.get_product.assert_called_once_with(4, branch_id=None)

    def test_duplicate_variant_rejected(self):
        with self.assertRaises(ReservationValidationError):
            self.service.create_reservation(
                11,
                payload(
                    items=[
                        {"id_variante_producto": 3, "cantidad": 1},
                        {"id_variante_producto": 3, "cantidad": 2},
                    ]
                ),
            )
        self.repo.lock_inventories.assert_not_called()

    def test_inactive_branch_rejected(self):
        self.branch.estado = False
        with self.assertRaises(ReservationValidationError):
            self.service.create_reservation(11, payload())

    def test_inactive_variant_and_product_rejected(self):
        for target in (self.variant, self.product):
            target.estado = False
            with self.subTest(target=target), self.assertRaises(ReservationValidationError):
                self.service.create_reservation(11, payload())
            target.estado = True

    def test_missing_inventory_rejected(self):
        self.repo.lock_inventories.return_value = []
        with self.assertRaises(ReservationNotFoundError):
            self.service.create_reservation(11, payload())

    def test_insufficient_stock_rolls_back_without_mutation(self):
        self.inventory.stock_actual = 4
        with self.assertRaises(ReservationConflictError):
            self.service.create_reservation(11, payload())
        self.assertEqual(self.inventory.stock_reservado, 3)
        self.db.rollback.assert_called_once()
        self.repo.create_reservation.assert_not_called()

    def test_second_item_failure_keeps_all_stock_unchanged(self):
        first = SimpleNamespace(
            id_variante_producto=1, stock_actual=8, stock_reservado=0, updated_at=None
        )
        second = SimpleNamespace(
            id_variante_producto=3, stock_actual=3, stock_reservado=3, updated_at=None
        )
        self.repo.get_variant.side_effect = [
            (SimpleNamespace(estado=True), SimpleNamespace(id_producto=4, estado=True)),
            (SimpleNamespace(estado=True), SimpleNamespace(id_producto=4, estado=True)),
        ]
        self.repo.lock_inventories.return_value = [first, second]
        with self.assertRaises(ReservationConflictError):
            self.service.create_reservation(
                11,
                payload(items=[
                    {"id_variante_producto": 1, "cantidad": 1},
                    {"id_variante_producto": 3, "cantidad": 1},
                ]),
            )
        self.assertEqual((first.stock_reservado, second.stock_reservado), (0, 3))

    @patch("app.services.client_reservations.secrets.token_hex")
    def test_code_is_unique_and_system_generated(self, token_hex):
        token_hex.side_effect = ["aaaaaaaaaa", "bbbbbbbbbb"]
        self.repo.code_exists.side_effect = [True, False]
        self.service.create_reservation(11, payload())
        code = self.repo.create_reservation.call_args.kwargs["code"]
        self.assertEqual(code, "RSV-20260911-BBBBBBBBBB")

    def test_cancel_releases_stock_once(self):
        result = self.service.cancel_reservation(11, 9)
        self.assertEqual(self.inventory.stock_reservado, 1)
        self.assertEqual(self.inventory.stock_actual, 10)
        self.assertEqual(result.estado, "CANCELADA")
        self.assertFalse(result.cancelable)
        self.db.commit.assert_called_once()

    def test_double_cancel_rejected(self):
        self.service.cancel_reservation(11, 9)
        with self.assertRaises(ReservationConflictError):
            self.service.cancel_reservation(11, 9)
        self.assertEqual(self.inventory.stock_reservado, 1)
        self.db.commit.assert_called_once()

    def test_attended_reservation_is_not_cancelable(self):
        self.reservation.estado = "ATENDIDA"
        with self.assertRaises(ReservationConflictError):
            self.service.cancel_reservation(11, 9)

    def test_expiration_releases_stock_and_is_exactly_once(self):
        self.reservation.fecha_expiracion = NOW - timedelta(seconds=1)
        result = self.service.get_reservation(11, 9)
        self.assertEqual(result.estado, "EXPIRADA")
        self.assertEqual(self.inventory.stock_reservado, 1)
        self.assertFalse(result.cancelable)
        self.service.get_reservation(11, 9)
        self.assertEqual(self.inventory.stock_reservado, 1)
        self.assertEqual(self.inventory.stock_actual, 10)
        self.assertEqual(self.repo.lock_inventories.call_count, 1)

    def test_cancel_of_due_reservation_commits_expiration_then_conflicts(self):
        self.reservation.fecha_expiracion = NOW - timedelta(seconds=1)
        with self.assertRaises(ReservationConflictError):
            self.service.cancel_reservation(11, 9)
        self.assertEqual(self.reservation.estado, "EXPIRADA")
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()

    def test_inconsistent_reserved_stock_is_never_clamped(self):
        self.inventory.stock_reservado = 1
        with self.assertRaises(ReservationConflictError):
            self.service.cancel_reservation(11, 9)
        self.assertEqual(self.inventory.stock_reservado, 1)

    def test_ownership_is_hidden_as_not_found(self):
        self.repo.get_owned_reservation.return_value = None
        with self.assertRaises(ReservationNotFoundError):
            self.service.get_reservation(11, 99)
        self.repo.get_owned_reservation.assert_called_once_with(99, 7, for_update=True)

    def test_list_scopes_owner_and_expires_before_query(self):
        self.repo.list_due_ids.return_value = []
        self.repo.list_reservations.return_value = ([], 0)
        data, pagination = self.service.list_reservations(11, state="PENDIENTE")
        self.assertEqual(data, [])
        self.assertEqual(pagination.total, 0)
        self.repo.list_due_ids.assert_called_once_with(7, NOW)
        self.repo.list_reservations.assert_called_once_with(
            7, state="PENDIENTE", page=1, page_size=20
        )


class ClientReservationRepositoryTests(TestCase):
    def test_inventory_query_uses_for_update_and_order(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        ClientReservationRepository(db).lock_inventories(2, [7, 1, 4])
        sql = str(
            db.scalars.call_args.args[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("ORDER BY t_inventario_sucursal.id_variante_producto", sql)
        self.assertIn("IN (1, 4, 7)", sql)


class ClientAuthorizationTests(TestCase):
    @patch("app.routers.client_reservations.AuthService")
    def test_client_role_authorized(self, auth):
        user = SimpleNamespace(id_usuario=11, rol="CLIENTE")
        auth.return_value.get_current_user.return_value = user
        result = require_client(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            MagicMock(),
        )
        self.assertIs(result, user)

    @patch("app.routers.client_reservations.AuthService")
    def test_non_client_role_forbidden(self, auth):
        auth.return_value.get_current_user.return_value = SimpleNamespace(
            id_usuario=1, rol="ADMINISTRADOR"
        )
        result = require_client(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            MagicMock(),
        )
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 403)

    def test_bearer_is_required(self):
        result = require_client(None, MagicMock())
        self.assertEqual(result.status_code, 401)
