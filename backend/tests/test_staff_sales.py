"""CU20 sin conexiones ni DDL: reglas, ASGI, persistencia y SQL PostgreSQL."""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import get_db
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.repositories.staff_sales import StaffSalesRepository
from app.routers import staff_sales as routes
from app.schemas.auth import AuthenticatedUserData
from app.schemas.staff_sales import SaleRequest
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError
from app.services.staff_sales import SaleError, StaffSalesService

KEY = UUID("11111111-2222-4333-8444-555555555555")
NOW = datetime(2026, 9, 12, 15)
BRANCH = dict(id_sucursal=2, nombre="Centro", direccion="Av. 1", ciudad="La Paz", id_empleado_sucursal=8)


def request(items=None, **kwargs):
    return SaleRequest.model_validate({"items": items if items is not None else [
        {"id_variante_producto": 3, "cantidad": 2}
    ], **kwargs})


def asgi_request(app, method, path, payload=None, headers=None):
    messages = []

    async def receive():
        return {"type": "http.request", "body": json.dumps(payload).encode() if payload is not None else b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": b"", "root_path": "", "server": ("test", 80), "client": ("test", 1),
             "headers": [(b"content-type", b"application/json"), *(headers or [])]}
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(body)


class SaleRequestTests(TestCase):
    def test_valid_direct_and_reserved_requests(self):
        self.assertIsNone(request().id_sucursal)
        self.assertEqual(request(id_reserva=9, id_sucursal=2).id_reserva, 9)

    def test_empty_items(self):
        with self.assertRaises(ValidationError):
            request([])

    def test_duplicate_variants(self):
        with self.assertRaises(ValidationError):
            request([dict(id_variante_producto=3, cantidad=1)] * 2)

    def test_quantities_are_strict_positive_integers(self):
        for value in (0, -1, True, False, "2", 2.0, None, 2147483648):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                request([dict(id_variante_producto=3, cantidad=value)])

    def test_ids_are_strict_positive_integers(self):
        for field in ("id_sucursal", "id_reserva"):
            for value in (True, "2", 2.0, 0, -1):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    request(**{field: value})
        for value in (True, "2", 2.0, 0, -1):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                request([dict(id_variante_producto=value, cantidad=1)])

    def test_forbidden_header_fields(self):
        for field in ("id_cliente", "id_empleado", "precio", "descuento", "subtotal", "total", "estado", "id_movimiento", "otro"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                request(**{field: 1})

    def test_forbidden_line_fields(self):
        for field in ("precio", "precio_unitario", "descuento", "id_promocion", "total", "estado", "otro"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                request([dict(id_variante_producto=3, cantidad=1, **{field: 1})])


class SaleServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = StaffSalesService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.catalog = self.service.catalog = MagicMock()
        self.repo.get_employee.return_value = NS(id_empleado=5, id_usuario=11)
        self.repo.branches.return_value = [BRANCH.copy()]
        self.repo.get_branch.return_value = NS(estado=True)
        self.repo.sale_for_reservation.return_value = None
        self.repo.sale_for_number.return_value = None
        self.inventory = NS(id_variante_producto=3, stock_actual=20, stock_reservado=2, updated_at=None)
        self.repo.inventories.return_value = [self.inventory]
        self.variant = NS(id_variante_producto=3, id_producto=4, sku="CAM-M", estado=True)
        self.product = NS(id_producto=4, nombre="Camisa", estado=True)
        self.repo.variant.return_value = (self.variant, self.product, "M", "Negro")
        self.catalog.get_product.return_value = NS(precio_base=Decimal("99.90"), precio_final=Decimal("79.92"), promocion_destacada=NS(id_promocion=6))
        self.reservation = NS(id_reserva=9, id_sucursal=2, id_cliente=7, estado="ATENDIDA", codigo="RSV-9")
        self.repo.get_reservation.return_value = self.reservation
        self.repo.reservation_details.return_value = [NS(id_variante_producto=3, cantidad=2, precio_unitario=Decimal("69.90"))]
        self.repo.create_sale.side_effect = self.make_sale
        self.repo.detail.side_effect = self.detail

    def make_sale(self, **values):
        self.sale = NS(id_venta=10, **values)
        return self.sale

    def detail(self, sale):
        items = self.repo.create_details.call_args.args[1] if self.repo.create_details.called else [
            dict(id_variante_producto=3, cantidad=2, precio_unitario=Decimal("99.90"), descuento_unitario=Decimal("19.98"), subtotal_linea=Decimal("159.84"), id_promocion=6)
        ]
        return {**vars(sale), "sucursal": BRANCH,
                "cajero": dict(id_empleado=5, id_usuario=11, nombre="Cajero", apellido="Uno"),
                "cliente": dict(id_cliente=7, id_usuario=12, nombre="Ana", apellido="Lopez") if sale.id_cliente else None,
                "reserva": dict(id_reserva=9, codigo="RSV-9", estado="ATENDIDA") if sale.id_reserva else None,
                "detalles": [{**item, "sku": "CAM-M", "producto": "Camisa", "talla": "M", "color": "Negro"} for item in items],
                "movimiento": dict(id_movimiento_inventario=20, id_empleado_sucursal=8, tipo_movimiento="VENTA", estado="PENDIENTE")}

    def assert_error(self, code, operation):
        with self.assertRaises(SaleError) as caught:
            operation()
        self.assertEqual(caught.exception.status_code, code)
        self.db.commit.assert_not_called()
        return caught.exception

    def test_employee_missing(self):
        self.repo.get_employee.return_value = None
        self.assert_error(403, lambda: self.service.list_branches(11))

    def test_no_active_assignments(self):
        self.repo.branches.return_value = []
        self.assert_error(403, lambda: self.service.list_branches(11))

    def test_single_branch_is_resolved_from_employee(self):
        result = self.service.quote(11, request())
        self.assertEqual(result.sucursal.id_sucursal, 2)
        self.assertEqual(result.id_empleado, 5)
        self.repo.get_employee.assert_called_once_with(11)
        self.repo.branches.assert_called_once_with(5, for_update=False)

    def test_list_multiple_branches(self):
        self.repo.branches.return_value.append({**BRANCH, "id_sucursal": 4, "id_empleado_sucursal": 12})
        self.assertEqual([row.id_sucursal for row in self.service.list_branches(11)], [2, 4])

    def test_multiple_branches_require_selection(self):
        self.repo.branches.return_value.append({**BRANCH, "id_sucursal": 4})
        self.assert_error(422, lambda: self.service.quote(11, request()))

    def test_multiple_branches_allow_own_selection(self):
        self.repo.branches.return_value.append({**BRANCH, "id_sucursal": 4, "id_empleado_sucursal": 12})
        result = self.service.quote(11, request(id_sucursal=4))
        self.assertEqual(result.sucursal.id_empleado_sucursal, 12)
        self.repo.inventories.assert_called_once_with(4, [3], for_update=False)

    def test_foreign_branch(self):
        self.assert_error(403, lambda: self.service.quote(11, request(id_sucursal=99)))

    def test_inactive_branch(self):
        self.repo.get_branch.return_value = NS(estado=False)
        self.assert_error(403, lambda: self.service.quote(11, request(id_sucursal=4)))

    def test_missing_branch(self):
        self.repo.get_branch.return_value = None
        self.assert_error(404, lambda: self.service.quote(11, request(id_sucursal=99)))

    def test_quote_decimal_promotion_and_no_writes(self):
        result = self.service.quote(11, request())
        self.assertEqual((result.subtotal, result.descuento_total, result.total), (Decimal("199.80"), Decimal("39.96"), Decimal("159.84")))
        self.assertEqual(result.detalles[0].id_promocion, 6)
        self.assertEqual(result.detalles[0].cantidad_disponible, 18)
        self.assertEqual((self.inventory.stock_actual, self.inventory.stock_reservado), (20, 2))
        self.db.commit.assert_not_called()
        self.db.flush.assert_not_called()
        self.repo.create_sale.assert_not_called()
        self.repo.create_movement.assert_not_called()
        self.catalog.get_product.assert_called_once_with(4, branch_id=None)

    def test_no_promotion(self):
        self.catalog.get_product.return_value = NS(precio_base=Decimal("0.10"), precio_final=Decimal("0.10"), promocion_destacada=None)
        result = self.service.quote(11, request())
        self.assertEqual(result.total, Decimal("0.20"))
        self.assertIsNone(result.detalles[0].id_promocion)
        self.assertEqual(result.descuento_total, Decimal("0.00"))

    def test_missing_variant(self):
        self.repo.variant.return_value = None
        self.assert_error(404, lambda: self.service.quote(11, request()))

    def test_missing_product(self):
        self.repo.variant.return_value = (self.variant, None, "M", "Negro")
        self.assert_error(404, lambda: self.service.quote(11, request()))

    def test_inactive_product(self):
        self.product.estado = False
        self.assert_error(422, lambda: self.service.quote(11, request()))

    def test_inactive_variant(self):
        self.variant.estado = False
        self.assert_error(422, lambda: self.service.quote(11, request()))

    def test_missing_inventory(self):
        self.repo.inventories.return_value = []
        self.assert_error(404, lambda: self.service.quote(11, request()))

    def test_reserved_stock_cannot_be_sold_directly(self):
        self.inventory.stock_actual = 3
        self.assert_error(409, lambda: self.service.quote(11, request()))

    def test_stock_revalidated_after_quote(self):
        self.service.quote(11, request())
        self.inventory.stock_actual = 2
        self.assert_error(409, lambda: self.service.create(11, request(), KEY))
        self.repo.create_sale.assert_not_called()

    def test_prices_recalculated_after_quote(self):
        self.service.quote(11, request())
        self.catalog.get_product.return_value.precio_final = Decimal("89.91")
        result = self.service.create(11, request(), KEY)
        self.assertEqual(result.total, Decimal("179.82"))

    def test_direct_sale_pending_correct_responsible_and_stock_untouched(self):
        result = self.service.create(11, request(), KEY)
        self.assertEqual((result.estado, result.id_empleado, result.id_sucursal), ("PENDIENTE", 5, 2))
        self.assertIsNone(result.id_cliente)
        self.assertIsNone(result.id_reserva)
        self.assertEqual(result.movimiento.estado, "PENDIENTE")
        self.assertEqual(result.movimiento.tipo_movimiento, "VENTA")
        self.assertEqual(self.repo.create_movement.call_args.args[1], 8)
        self.assertEqual(self.repo.create_details.call_args.args[1][0]["cantidad"], 2)
        self.assertEqual((self.inventory.stock_actual, self.inventory.stock_reservado), (20, 2))
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()

    def test_missing_reservation(self):
        self.repo.get_reservation.return_value = None
        self.assert_error(404, lambda: self.service.quote(11, request(id_reserva=9)))

    def test_only_attended_reservations(self):
        for state in ("PENDIENTE", "CONFIRMADA", "CANCELADA", "EXPIRADA"):
            self.reservation.estado = state
            with self.subTest(state=state):
                self.assert_error(409, lambda: self.service.create(11, request(id_reserva=9), KEY))

    def test_reservation_branch_must_match(self):
        self.reservation.id_sucursal = 4
        self.assert_error(403, lambda: self.service.quote(11, request(id_reserva=9)))

    def test_reservation_already_sold(self):
        self.repo.sale_for_reservation.return_value = NS(estado="ANULADA")
        self.assert_error(409, lambda: self.service.create(11, request(id_reserva=9), KEY))

    def test_variant_outside_reservation(self):
        self.assert_error(422, lambda: self.service.quote(11, request([dict(id_variante_producto=4, cantidad=1)], id_reserva=9)))

    def test_quantity_above_reserved(self):
        self.assert_error(422, lambda: self.service.quote(11, request([dict(id_variante_producto=3, cantidad=3)], id_reserva=9)))

    def test_reserved_quote_is_read_only_and_keeps_snapshot_price(self):
        result = self.service.quote(11, request([dict(id_variante_producto=3, cantidad=1)], id_reserva=9))
        self.assertEqual(result.total, Decimal("69.90"))
        self.assertEqual(result.descuento_total, Decimal("0.00"))
        self.assertIsNone(result.detalles[0].id_promocion)
        self.assertEqual(result.liberaciones[0].cantidad_liberar, 1)
        self.assertEqual(self.inventory.stock_reservado, 2)
        self.assertEqual(self.reservation.estado, "ATENDIDA")
        self.catalog.get_product.assert_not_called()
        self.db.commit.assert_not_called()
        self.repo.get_reservation.assert_called_once_with(9, for_update=False)
        self.repo.inventories.assert_called_once_with(2, [3], for_update=False)

    def test_full_reservation_purchase_keeps_all_stock_reserved(self):
        result = self.service.create(11, request(id_reserva=9), KEY)
        self.assertEqual(result.total, Decimal("139.80"))
        self.assertEqual((result.id_cliente, result.id_reserva), (7, 9))
        self.assertEqual(self.inventory.stock_reservado, 2)
        self.assertEqual(self.inventory.stock_actual, 20)
        self.assertEqual(self.reservation.estado, "ATENDIDA")
        self.assertEqual(result.reserva.codigo, "RSV-9")
        self.assertEqual(result.cliente.id_cliente, 7)

    def test_partial_purchase_releases_only_surplus(self):
        result = self.service.create(11, request([dict(id_variante_producto=3, cantidad=1)], id_reserva=9), KEY)
        self.assertEqual(self.inventory.stock_reservado, 1)
        self.assertEqual(self.inventory.stock_actual, 20)
        self.assertEqual(result.estado, "PENDIENTE")
        self.assertEqual(result.movimiento.estado, "PENDIENTE")
        self.assertEqual(self.reservation.estado, "ATENDIDA")
        self.db.commit.assert_called_once()

    def test_partial_multiple_items_omission_releases_all(self):
        omitted = NS(id_variante_producto=4, stock_actual=10, stock_reservado=3, updated_at=None)
        bought = NS(id_variante_producto=5, stock_actual=10, stock_reservado=1, updated_at=None)
        self.repo.inventories.return_value = [self.inventory, omitted, bought]
        self.repo.reservation_details.return_value += [NS(id_variante_producto=4, cantidad=1, precio_unitario=Decimal("10")), NS(id_variante_producto=5, cantidad=1, precio_unitario=Decimal("20"))]
        result = self.service.create(11, request([dict(id_variante_producto=5, cantidad=1), dict(id_variante_producto=3, cantidad=1)], id_reserva=9), KEY)
        self.assertEqual([self.inventory.stock_reservado, omitted.stock_reservado, bought.stock_reservado], [1, 2, 1])
        self.assertEqual([self.inventory.stock_actual, omitted.stock_actual, bought.stock_actual], [20, 10, 10])
        self.assertEqual([line.id_variante_producto for line in result.detalles], [3, 5])
        movement_items = self.repo.create_movement.call_args.args[2]
        self.assertEqual([item["id_variante_producto"] for item in movement_items], [3, 5])
        self.repo.inventories.assert_called_once_with(2, [3, 4, 5], for_update=True)

    def test_reservation_and_inventories_locked_in_order(self):
        self.service.create(11, request(id_reserva=9), KEY)
        self.repo.get_reservation.assert_called_once_with(9, for_update=True)
        self.repo.inventories.assert_called_once_with(2, [3], for_update=True)
        names = [call[0] for call in self.repo.mock_calls]
        self.assertLess(names.index("get_reservation"), names.index("inventories"))
        self.assertLess(names.index("inventories"), names.index("create_sale"))

    def test_inconsistent_reserved_stock(self):
        self.inventory.stock_reservado = 1
        self.assert_error(409, lambda: self.service.create(11, request(id_reserva=9), KEY))
        self.assertEqual(self.inventory.stock_reservado, 1)

    def test_missing_reserved_inventory(self):
        self.repo.inventories.return_value = []
        self.assert_error(409, lambda: self.service.create(11, request(id_reserva=9), KEY))

    def test_inactive_reserved_variant_keeps_agreed_price(self):
        self.variant.estado = False
        result = self.service.quote(11, request(id_reserva=9))
        self.assertEqual(result.total, Decimal("139.80"))

    def test_idempotency_duplicate_is_conflict(self):
        self.repo.sale_for_number.return_value = NS(id_venta=10)
        self.assert_error(409, lambda: self.service.create(11, request(), KEY))
        self.repo.create_sale.assert_not_called()

    def test_number_is_stable_scoped_and_fits_column(self):
        number = self.service.sale_number(2147483647, KEY)
        self.assertLessEqual(len(number), 50)
        self.assertEqual(number, self.service.sale_number(2147483647, KEY))
        self.assertNotEqual(number, self.service.sale_number(11, KEY))
        self.assertNotEqual(number, self.service.sale_number(2147483647, uuid4()))

    def test_integrity_errors_rollback_all_write_stages(self):
        for name in ("create_sale", "create_details", "create_movement", "detail"):
            with self.subTest(stage=name):
                method = getattr(self.repo, name)
                original = method.side_effect
                method.side_effect = IntegrityError("SQL privado", {}, Exception("duplicate"))
                self.assert_error(409, lambda: self.service.create(11, request(), KEY))
                method.side_effect = original
        self.assertEqual(self.db.rollback.call_count, 4)

    def test_failed_commit_rolls_back(self):
        self.db.commit.side_effect = IntegrityError("SQL privado", {}, Exception("numero_venta"))
        with self.assertRaises(SaleError) as caught:
            self.service.create(11, request(), KEY)
        self.assertEqual(caught.exception.status_code, 409)
        self.db.rollback.assert_called_once()

    def test_partial_release_and_all_entities_share_rollback(self):
        # La sesion simulada restaura el estado como haria rollback en SQLAlchemy.
        staged = []
        original = vars(self.inventory).copy()

        def rollback():
            vars(self.inventory).update(original)
            staged.clear()

        def create_sale(**values):
            self.assertEqual(self.inventory.stock_reservado, 1)
            sale = self.make_sale(**values)
            staged.append(sale)
            return sale

        self.db.rollback.side_effect = rollback
        self.repo.create_sale.side_effect = create_sale
        self.repo.create_details.side_effect = lambda *args: staged.append(args)
        self.repo.create_movement.side_effect = IntegrityError("SQL", {}, Exception("movimiento duplicado"))
        self.assert_error(409, lambda: self.service.create(11, request([dict(id_variante_producto=3, cantidad=1)], id_reserva=9), KEY))
        self.assertEqual(staged, [])
        self.assertEqual(vars(self.inventory), original)
        self.assertEqual(self.reservation.estado, "ATENDIDA")
        self.db.rollback.assert_called_once()

    def test_second_sale_from_same_reservation_is_rejected(self):
        self.service.create(11, request(id_reserva=9), KEY)
        self.db.reset_mock()
        self.repo.sale_for_reservation.return_value = self.sale
        self.assert_error(409, lambda: self.service.create(11, request(id_reserva=9), uuid4()))
        self.assertEqual(self.repo.create_sale.call_count, 1)
        self.assertEqual(self.inventory.stock_reservado, 2)

    def test_numeric_overflow_is_validation_error(self):
        self.inventory.stock_actual = 2147483647
        self.assert_error(422, lambda: self.service.quote(11, request([dict(id_variante_producto=3, cantidad=2147483640)])))

    def test_nonconcurrent_database_error_is_sanitized(self):
        self.repo.create_sale.side_effect = DBAPIError("SQL privado", {}, Exception("connection lost"))
        error = self.assert_error(500, lambda: self.service.create(11, request(), KEY))
        self.assertNotIn("SQL", str(error))

    def test_concurrent_database_errors_are_conflicts(self):
        for code in ("40001", "40P01", "55P03"):
            orig = Exception("SQL privado")
            orig.sqlstate = code
            self.repo.create_sale.side_effect = DBAPIError("SQL privado", {}, orig)
            with self.subTest(code=code):
                self.assert_error(409, lambda: self.service.create(11, request(), KEY))

    def test_unexpected_error_is_sanitized_and_rolled_back(self):
        self.repo.create_movement.side_effect = RuntimeError("SQL secreto")
        error = self.assert_error(500, lambda: self.service.create(11, request(), KEY))
        self.assertNotIn("SQL", str(error))
        self.db.rollback.assert_called_once()

    def test_get_own_sale(self):
        created = self.service.create(11, request(), KEY)
        self.db.reset_mock()
        self.repo.get_sale.return_value = self.sale
        result = self.service.get_sale(11, 10)
        self.assertEqual(result, created)
        self.db.commit.assert_not_called()

    def test_get_foreign_sale_is_forbidden(self):
        self.repo.get_sale.return_value = NS(id_sucursal=99)
        self.assert_error(403, lambda: self.service.get_sale(11, 10))

    def test_get_missing_sale(self):
        self.repo.get_sale.return_value = None
        self.assert_error(404, lambda: self.service.get_sale(11, 10))


class SaleRepositoryTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.repo = StaffSalesRepository(self.db)

    def sql(self, statement):
        return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    def test_branches_filter_employee_assignment_and_branch_state(self):
        self.repo.branches(5, for_update=True)
        sql = self.sql(self.db.execute.call_args.args[0])
        for fragment in ("t_empleado_sucursal.id_empleado = 5", "t_empleado_sucursal.estado IS true", "t_sucursal.estado IS true", "JOIN t_ciudad", "FOR UPDATE OF t_empleado_sucursal, t_sucursal"):
            self.assertIn(fragment, sql)

    def test_branch_listing_has_no_locks(self):
        self.repo.branches(5)
        self.assertNotIn("FOR UPDATE", self.sql(self.db.execute.call_args.args[0]))

    def test_inventory_locks_are_branch_scoped_and_sorted(self):
        self.repo.inventories(2, [9, 3, 5], for_update=True)
        sql = self.sql(self.db.scalars.call_args.args[0])
        for fragment in ("id_sucursal = 2", "IN (3, 5, 9)", "ORDER BY t_inventario_sucursal.id_variante_producto", "FOR UPDATE"):
            self.assertIn(fragment, sql)
        self.assertNotIn("sum(", sql.lower())

    def test_quote_inventory_has_no_locks(self):
        self.repo.inventories(2, [3])
        self.assertNotIn("FOR UPDATE", self.sql(self.db.scalars.call_args.args[0]))

    def test_reservation_is_locked_and_refreshed(self):
        self.repo.get_reservation(9, for_update=True)
        statement = self.db.scalar.call_args.args[0]
        self.assertIn("t_reserva.id_reserva = 9", self.sql(statement))
        self.assertIn("FOR UPDATE", self.sql(statement))
        self.assertTrue(statement.get_execution_options()["populate_existing"])

    def test_reservation_sale_lookup_includes_all_states(self):
        self.repo.sale_for_reservation(9)
        sql = self.sql(self.db.scalar.call_args.args[0])
        self.assertIn("WHERE t_venta.id_reserva = 9", sql)
        self.assertNotIn("AND t_venta.estado", sql)

    def test_writes_existing_entities_pending_without_commit(self):
        sale = self.repo.create_sale(id_sucursal=2, id_empleado=5, numero_venta="VTA-X", estado="PENDIENTE", subtotal=Decimal("20"), descuento_total=Decimal("0"), total=Decimal("20"))
        sale.id_venta = 10
        items = [dict(id_variante_producto=3, cantidad=2, precio_unitario=Decimal("10"), descuento_unitario=Decimal("0"), id_promocion=None, subtotal_linea=Decimal("20"))]
        self.repo.create_details(10, items)
        movement = self.repo.create_movement(sale, 8, items)
        self.assertIsInstance(sale, Sale)
        self.assertIsInstance(movement, InventoryMovement)
        self.assertEqual((movement.tipo_movimiento, movement.estado, movement.id_sucursal_origen, movement.id_empleado_sucursal, movement.id_venta), ("VENTA", "PENDIENTE", 2, 8, 10))
        self.assertIsNone(movement.id_sucursal_destino)
        entities = [call.args[0] for call in self.db.add.call_args_list]
        entities += [entity for call in self.db.add_all.call_args_list for entity in call.args[0]]
        self.assertEqual({type(entity) for entity in entities}, {Sale, SaleDetail, InventoryMovement, InventoryMovementDetail})
        movement_detail = next(entity for entity in entities if isinstance(entity, InventoryMovementDetail))
        self.assertEqual((movement_detail.id_variante_producto, movement_detail.cantidad), (3, 2))
        self.assertIsNone(movement_detail.costo_unitario)
        self.db.commit.assert_not_called()


class SaleRouterTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.app = FastAPI()
        self.app.include_router(routes.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.user = AuthenticatedUserData(id_usuario=11, nombre="Cajero", apellido="Uno", correo="cajero@example.com", rol="CAJERO")
        self.headers = [(b"authorization", b"Bearer test")]

    def test_no_token(self):
        status, _ = asgi_request(self.app, "GET", "/api/staff/sales/branches")
        self.assertEqual(status, 401)

    def test_only_cashier_role(self):
        for role in ("CLIENTE", "ADMINISTRADOR", "ADMIN", "ENCARGADO_SUCURSAL", "PROVEEDOR"):
            with self.subTest(role=role), patch.object(routes.AuthService, "get_current_user", return_value=self.user.model_copy(update={"rol": role})):
                status, _ = asgi_request(self.app, "GET", "/api/staff/sales/branches", headers=self.headers)
                self.assertEqual(status, 403)

    def test_invalid_and_inactive_auth(self):
        for error, expected in ((InvalidAccessTokenError(), 401), (InactiveAccountError(), 403)):
            with self.subTest(expected=expected), patch.object(routes.AuthService, "get_current_user", side_effect=error):
                status, _ = asgi_request(self.app, "GET", "/api/staff/sales/branches", headers=self.headers)
                self.assertEqual(status, expected)

    def test_cashier_authorized(self):
        with patch.object(routes.AuthService, "get_current_user", return_value=self.user), patch.object(routes.StaffSalesService, "list_branches", return_value=[BRANCH]):
            status, body = asgi_request(self.app, "GET", "/api/staff/sales/branches", headers=self.headers)
        self.assertEqual(status, 200)
        self.assertEqual(body["data"][0]["id_empleado_sucursal"], 8)

    def test_all_routes_reject_other_roles(self):
        for method, path in (("GET", "/branches"), ("POST", "/quote"), ("POST", ""), ("GET", "/10")):
            with self.subTest(path=path), patch.object(routes.AuthService, "get_current_user", return_value=self.user.model_copy(update={"rol": "ADMINISTRADOR"})):
                status, _ = asgi_request(self.app, method, "/api/staff/sales" + path, request().model_dump(), self.headers + [(b"idempotency-key", str(KEY).encode())])
                self.assertEqual(status, 403)

    def test_register_requires_uuid_idempotency_header(self):
        self.app.dependency_overrides[routes.require_cashier] = lambda: self.user
        for headers in ([], [(b"idempotency-key", b"invalid")]):
            with self.subTest(headers=headers):
                status, _ = asgi_request(self.app, "POST", "/api/staff/sales", request().model_dump(), headers)
                self.assertEqual(status, 422)

    def test_invalid_payload_http_422(self):
        self.app.dependency_overrides[routes.require_cashier] = lambda: self.user
        status, _ = asgi_request(self.app, "POST", "/api/staff/sales/quote", {"items": [{"id_variante_producto": 3, "cantidad": True}]})
        self.assertEqual(status, 422)

    def test_service_errors_http_mapping(self):
        self.app.dependency_overrides[routes.require_cashier] = lambda: self.user
        for code in (403, 404, 409, 422, 500):
            with self.subTest(code=code), patch.object(routes.logger, "exception"), patch.object(routes.StaffSalesService, "list_branches", side_effect=SaleError(code, "Mensaje seguro")):
                status, body = asgi_request(self.app, "GET", "/api/staff/sales/branches")
                self.assertEqual(status, code)
                self.assertFalse(body["success"])

    def test_create_http_201_and_get_http_200_with_serialized_decimals(self):
        fixture = SaleServiceTests()
        fixture.setUp()
        sale = fixture.service.create(11, request(id_reserva=9), KEY)
        self.app.dependency_overrides[routes.require_cashier] = lambda: self.user
        with patch.object(routes.StaffSalesService, "create", return_value=sale) as create:
            status, body = asgi_request(self.app, "POST", "/api/staff/sales", request(id_reserva=9).model_dump(), [(b"idempotency-key", str(KEY).encode())])
            self.assertEqual(status, 201)
            self.assertEqual(body["data"]["total"], "139.80")
            self.assertEqual(body["data"]["estado"], "PENDIENTE")
            self.assertEqual(create.call_args.args[0], 11)
            self.assertEqual(create.call_args.args[2], KEY)
        with patch.object(routes.StaffSalesService, "get_sale", return_value=sale):
            status, body = asgi_request(self.app, "GET", "/api/staff/sales/10")
            self.assertEqual(status, 200)
            self.assertEqual(body["data"]["reserva"]["id_reserva"], 9)
            self.assertEqual(body["data"]["movimiento"]["estado"], "PENDIENTE")

    def test_quote_http_200_without_idempotency_key(self):
        fixture = SaleServiceTests()
        fixture.setUp()
        quote = fixture.service.quote(11, request())
        self.app.dependency_overrides[routes.require_cashier] = lambda: self.user
        with patch.object(routes.StaffSalesService, "quote", return_value=quote):
            status, body = asgi_request(self.app, "POST", "/api/staff/sales/quote", request().model_dump())
            self.assertEqual(status, 200)
            self.assertEqual(body["data"]["total"], "159.84")

    def test_unexpected_http_error_does_not_expose_sql(self):
        self.app.dependency_overrides[routes.require_cashier] = lambda: self.user
        with patch.object(routes.logger, "exception"), patch.object(routes.StaffSalesService, "get_sale", side_effect=RuntimeError("SQL secreto")):
            status, body = asgi_request(self.app, "GET", "/api/staff/sales/10")
            self.assertEqual(status, 500)
            self.assertNotIn("SQL", json.dumps(body))

    def test_only_four_endpoints_and_no_payments(self):
        paths = self.app.openapi()["paths"]
        self.assertEqual(set(paths), {"/api/staff/sales", "/api/staff/sales/quote", "/api/staff/sales/branches", "/api/staff/sales/{id_venta}"})
        self.assertEqual(set(paths["/api/staff/sales"]), {"post"})
        from app.main import app
        self.assertTrue(set(paths).issubset(app.openapi()["paths"]))
