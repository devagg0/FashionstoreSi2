"""CU18: autorizacion, sucursal, transiciones, stock y concurrencia."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.dialects import postgresql

from app.repositories.staff_reservations import StaffReservationRepository
from app.routers import staff_reservations as routes
from app.services.client_reservations import (
    ReservationConflictError,
    ReservationNotFoundError,
)
from app.services.staff_reservations import (
    StaffReservationAccessError,
    StaffReservationService,
)


NOW = datetime(2026, 9, 12, 14, 0, 0)


class StaffReservationServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = StaffReservationService(self.db)
        self.repo = MagicMock()
        self.service.repository = self.repo
        self.service._now = MagicMock(return_value=NOW)
        self.employee = SimpleNamespace(id_empleado=5, id_usuario=11)
        self.reservation = SimpleNamespace(
            id_reserva=9,
            id_sucursal=2,
            estado="PENDIENTE",
            fecha_expiracion=NOW + timedelta(hours=1),
            fecha_atencion=None,
            id_empleado_atencion=None,
            updated_at=NOW - timedelta(days=1),
        )
        self.repo.get_employee_by_user.return_value = self.employee
        self.repo.list_active_branch_ids.return_value = [2]
        self.repo.get_scoped_reservation.return_value = self.reservation
        self.repo.get_scoped_reservation_by_code.return_value = self.reservation
        self.repo.list_due_ids.return_value = []
        self.repo.get_detail.side_effect = lambda *_: self._detail_row()

    def _detail_row(self):
        return {
            "id_reserva": 9,
            "codigo": "RSV-20260912-ABCDEF1234",
            "estado": self.reservation.estado,
            "created_at": NOW - timedelta(days=1),
            "fecha_atencion_programada": NOW + timedelta(minutes=30),
            "fecha_expiracion": self.reservation.fecha_expiracion,
            "fecha_atencion": self.reservation.fecha_atencion,
            "id_cliente": 7,
            "cliente_nombre": "Ana",
            "cliente_apellido": "Lopez",
            "cliente_correo": "ana@example.test",
            "cliente_telefono": "70000000",
            "id_sucursal": 2,
            "sucursal": "Centro",
            "direccion": "Av. Principal 1",
            "id_ciudad": 1,
            "ciudad": "La Paz",
            "cantidad_prendas": 2,
            "total": Decimal("159.80"),
            "items": [
                {
                    "id_variante_producto": 3,
                    "sku": "CAM-M-NEG",
                    "id_producto": 4,
                    "producto": "Camisa",
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

    def test_employee_without_profile_is_forbidden(self):
        self.repo.get_employee_by_user.return_value = None
        with self.assertRaises(StaffReservationAccessError):
            self.service.list_reservations(11)

    def test_employee_without_active_branch_is_forbidden(self):
        self.repo.list_active_branch_ids.return_value = []
        with self.assertRaises(StaffReservationAccessError):
            self.service.list_reservations(11)

    def test_other_branch_is_hidden_as_not_found(self):
        self.repo.get_scoped_reservation.return_value = None
        with self.assertRaises(ReservationNotFoundError):
            self.service.get_reservation(11, 99)
        self.repo.get_scoped_reservation.assert_called_once_with(
            99, [2], for_update=True
        )

    def test_confirm_pending_reservation(self):
        result = self.service.confirm_reservation(11, 9)
        self.assertEqual(result.estado, "CONFIRMADA")
        self.assertEqual(self.reservation.estado, "CONFIRMADA")
        self.assertIsNone(self.reservation.id_empleado_atencion)
        self.repo.list_active_branch_ids.assert_called_once_with(5, for_update=True)
        self.repo.get_scoped_reservation.assert_called_once_with(
            9, [2], for_update=True
        )
        self.db.flush.assert_called_once()
        self.db.commit.assert_called_once()

    def test_attend_confirmed_reservation_preserves_stock(self):
        self.reservation.estado = "CONFIRMADA"
        result = self.service.attend_reservation(11, 9)
        self.assertEqual(result.estado, "ATENDIDA")
        self.assertEqual(self.reservation.id_empleado_atencion, 5)
        self.assertEqual(self.reservation.fecha_atencion, NOW)
        self.assertEqual(result.prendas[0].precio_reservado, Decimal("79.90"))
        self.repo.get_details.assert_not_called()
        self.repo.lock_inventories.assert_not_called()

    def test_invalid_transition_is_rejected(self):
        self.reservation.estado = "PENDIENTE"
        with self.assertRaisesRegex(ReservationConflictError, "CONFIRMADA"):
            self.service.attend_reservation(11, 9)
        self.assertEqual(self.reservation.estado, "PENDIENTE")
        self.db.rollback.assert_called_once()

    def test_cancelled_and_attended_cannot_be_confirmed(self):
        for state in ("CANCELADA", "EXPIRADA", "ATENDIDA"):
            self.reservation.estado = state
            with self.subTest(state=state), self.assertRaises(
                ReservationConflictError
            ):
                self.service.confirm_reservation(11, 9)

    def test_due_reservation_is_expired_not_confirmed(self):
        self.reservation.fecha_expiracion = NOW - timedelta(seconds=1)
        self.repo.get_details.return_value = [
            SimpleNamespace(id_variante_producto=3, cantidad=2)
        ]
        inventory = SimpleNamespace(
            id_variante_producto=3,
            stock_actual=10,
            stock_reservado=4,
            updated_at=None,
        )
        self.repo.lock_inventories.return_value = [inventory]
        with self.assertRaisesRegex(ReservationConflictError, "EXPIRADA"):
            self.service.confirm_reservation(11, 9)
        self.assertEqual(self.reservation.estado, "EXPIRADA")
        self.assertEqual(inventory.stock_reservado, 2)
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()

    def test_list_uses_active_branches_state_and_local_date(self):
        self.repo.list_reservations.return_value = ([], 0)
        data, pagination = self.service.list_reservations(
            11, state="PENDIENTE", scheduled_date=date(2026, 9, 12)
        )
        self.assertEqual(data, [])
        self.assertEqual(pagination.total, 0)
        kwargs = self.repo.list_reservations.call_args.kwargs
        self.assertEqual(self.repo.list_reservations.call_args.args[0], [2])
        self.assertEqual(kwargs["state"], "PENDIENTE")
        self.assertEqual(kwargs["scheduled_from"], datetime(2026, 9, 12, 4))
        self.assertEqual(kwargs["scheduled_until"], datetime(2026, 9, 13, 4))

    def test_search_by_code_is_normalized_and_scoped(self):
        result = self.service.get_reservation_by_code(
            11, " rsv-20260912-abcdef1234 "
        )
        self.assertEqual(result.codigo, "RSV-20260912-ABCDEF1234")
        self.repo.get_scoped_reservation_by_code.assert_called_once_with(
            "RSV-20260912-ABCDEF1234", [2], for_update=True
        )


class StaffReservationRepositoryTests(TestCase):
    def test_state_change_query_uses_for_update_and_branch_scope(self):
        db = MagicMock()
        StaffReservationRepository(db).get_scoped_reservation(
            9, [2, 4], for_update=True
        )
        statement = db.scalar.call_args.args[0]
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("t_reserva.id_sucursal IN (2, 4)", sql)
        self.assertIn("t_reserva.id_reserva = 9", sql)

    def test_active_assignment_query_can_be_locked(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        StaffReservationRepository(db).list_active_branch_ids(5, for_update=True)
        statement = db.scalars.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("t_empleado_sucursal.estado IS true", sql)


class StaffReservationAuthorizationTests(TestCase):
    @patch("app.routers.staff_reservations.AuthService")
    def test_cashier_and_branch_manager_are_authorized(self, auth):
        for role in ("CAJERO", "ENCARGADO_SUCURSAL"):
            user = SimpleNamespace(id_usuario=11, rol=role)
            auth.return_value.get_current_user.return_value = user
            with self.subTest(role=role):
                result = routes.require_reservation_staff(
                    HTTPAuthorizationCredentials(
                        scheme="Bearer", credentials="token"
                    ),
                    MagicMock(),
                )
                self.assertIs(result, user)

    @patch("app.routers.staff_reservations.AuthService")
    def test_other_roles_are_forbidden(self, auth):
        auth.return_value.get_current_user.return_value = SimpleNamespace(
            id_usuario=1, rol="ADMINISTRADOR"
        )
        result = routes.require_reservation_staff(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            MagicMock(),
        )
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 403)

    def test_exact_endpoint_contract(self):
        app = FastAPI()
        app.include_router(routes.router)
        paths = app.openapi()["paths"]
        self.assertEqual(
            set(paths),
            {
                "/api/staff/reservations",
                "/api/staff/reservations/code/{codigo}",
                "/api/staff/reservations/{id_reserva}",
                "/api/staff/reservations/{id_reserva}/confirm",
                "/api/staff/reservations/{id_reserva}/attend",
            },
        )
        self.assertEqual(set(paths["/api/staff/reservations"]), {"get"})
        self.assertEqual(
            set(paths["/api/staff/reservations/{id_reserva}/confirm"]),
            {"patch"},
        )
        parameters = {
            parameter["name"]: parameter
            for parameter in paths["/api/staff/reservations"]["get"]["parameters"]
        }
        self.assertIn("estado", parameters)
        self.assertIn("fecha_programada", parameters)
