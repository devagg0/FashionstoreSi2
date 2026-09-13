"""CU19: pruebas sin conexiones ni escrituras en la BD del proyecto."""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import get_db
from app.models.cart import Cart
from app.models.cart_detail import CartDetail
from app.repositories.client_cart import ClientCartRepository
from app.routers import client_cart as routes
from app.schemas.client_cart import CartItemCreate, CartQuantityUpdate
from app.services.auth_service import InvalidAccessTokenError
from app.services.catalog import CatalogService
from app.services.client_cart import (
    CartAccessError, CartConflictError, CartNotFoundError, CartPersistenceError,
    CartValidationError, ClientCartService,
)


def request(app, method="GET", path="/api/client/cart", body=None, token=True):
    messages = []
    payload = json.dumps(body).encode() if body is not None else b""

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        messages.append(message)

    headers = [(b"content-type", b"application/json")]
    if token:
        headers.append((b"authorization", b"Bearer token"))
    scope = dict(
        type="http", asgi={"version": "3.0"}, http_version="1.1",
        method=method, scheme="http", path=path, raw_path=path.encode(),
        query_string=b"", root_path="", headers=headers,
        client=("127.0.0.1", 1), server=("test", 80),
    )
    asyncio.run(app(scope, receive, send))
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(content)


class CartFixture(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = ClientCartService(self.db)
        self.repo = MagicMock(spec=ClientCartRepository)
        self.service.repository = self.repo
        self.service.catalog_repository = MagicMock()
        self.service.catalog_repository.list_current_promotions.return_value = []
        self.cart = SimpleNamespace(id_carrito=9, id_cliente=7, estado="ACTIVO", updated_at=None)
        self.client = SimpleNamespace(id_cliente=7, id_usuario=11)
        self.variant = SimpleNamespace(id_variante_producto=3, estado=True)
        self.product = SimpleNamespace(id_producto=4, estado=True)
        self.rows = {}
        self.inventory = {"stock_actual": 10, "stock_reservado": 3, "stock_minimo": 2}
        self.repo.get_client.return_value = self.client
        self.repo.get_active_cart.return_value = self.cart
        self.repo.create_cart.return_value = self.cart
        self.repo.get_variant.return_value = (self.variant, self.product)
        self.repo.availability.return_value = [self.inventory]
        self.repo.list_items.side_effect = lambda _: list(self.rows.values())
        self.repo.get_item.side_effect = lambda cart, variant: (
            SimpleNamespace(**self.rows[variant]) if variant in self.rows else None
        )
        self.repo.create_item.side_effect = lambda cart, variant, quantity: self.add_row(variant, quantity)
        self.repo.update_quantity.side_effect = lambda item, quantity: self.rows[item.id_variante_producto].update(cantidad=quantity)
        self.repo.delete_item.side_effect = lambda item: self.rows.pop(item.id_variante_producto)
        self.repo.clear_items.side_effect = lambda cart: self.rows.clear()

    def add_row(self, variant=3, quantity=2, **changes):
        row = dict(
            id_detalle_carrito=variant + 10, id_variante_producto=variant,
            id_producto=4, nombre_producto="Camisa", sku=f"SKU-{variant}",
            id_talla=1, talla="M", id_color=2, color="Blanco", codigo_hex="#ffffff",
            imagen_principal=None, cantidad=quantity, precio=Decimal("10.10"),
            estado_producto=True, estado_variante=True,
        )
        row.update(changes)
        self.rows[variant] = row

    def post(self, quantity=2):
        return self.service.add_item(11, CartItemCreate(id_variante_producto=3, cantidad=quantity))

    def update(self, quantity=3):
        return self.service.update_item(11, 3, CartQuantityUpdate(cantidad=quantity))

    def promotion(self):
        return dict(
            id_promocion=8, promocion_nombre="Oferta", promocion_codigo=None,
            promocion_descripcion=None, tipo_descuento="MONTO_FIJO",
            valor_descuento=Decimal("0.10"), precio_resultante=Decimal("10.00"),
            fecha_inicio=datetime(2026, 1, 1), fecha_fin=datetime(2027, 1, 1), acumulable=False,
        )


class CartServiceTests(CartFixture):
    def test_empty_get_does_not_create_or_commit(self):
        self.repo.get_active_cart.return_value = None
        data = self.service.get_cart(11)
        self.assertEqual(data.model_dump(mode="json"), dict(
            id_carrito=None, estado=None, items=[], cantidad_items=0,
            cantidad_unidades=0, subtotal="0.00", descuento_total="0.00", total="0.00",
        ))
        self.repo.create_cart.assert_not_called()
        self.db.commit.assert_not_called()

    def test_get_existing(self):
        self.add_row()
        data = self.service.get_cart(11)
        self.assertEqual((data.id_carrito, data.estado, data.cantidad_items), (9, "ACTIVO", 1))
        self.assertEqual(data.items[0].sku, "SKU-3")
        self.db.commit.assert_not_called()

    def test_missing_client(self):
        self.repo.get_client.return_value = None
        with self.assertRaises(CartAccessError):
            self.post()
        self.db.rollback.assert_called_once()

    def test_post_creates_cart_and_detail(self):
        self.repo.get_active_cart.return_value = None
        data = self.post()
        self.repo.create_cart.assert_called_once_with(7)
        self.repo.create_item.assert_called_once_with(9, 3, 2)
        self.assertEqual(data.items[0].cantidad, 2)
        self.db.commit.assert_called_once()

    def test_post_reuses_cart(self):
        self.post()
        self.repo.create_cart.assert_not_called()

    def test_repeated_variant_increments_without_duplicate(self):
        self.add_row()
        data = self.post(1)
        self.assertEqual((data.cantidad_items, data.items[0].cantidad), (1, 3))
        self.repo.create_item.assert_not_called()

    def test_repeated_variant_validates_accumulated_quantity(self):
        self.add_row(quantity=6)
        with self.assertRaises(CartConflictError):
            self.post(2)
        self.repo.update_quantity.assert_not_called()
        self.assertEqual(self.rows[3]["cantidad"], 6)

    def test_missing_variant_or_product(self):
        for row in (None, (self.variant, None)):
            with self.subTest(row=row):
                self.repo.get_variant.return_value = row
                with self.assertRaises(CartNotFoundError):
                    self.post()

    def test_post_inactive_product_or_variant(self):
        for target in (self.product, self.variant):
            with self.subTest(target=target):
                target.estado = False
                with self.assertRaises(CartValidationError):
                    self.post()
                target.estado = True
        self.repo.create_item.assert_not_called()

    def test_exact_available_quantity_accepted(self):
        self.assertEqual(self.post(7).cantidad_unidades, 7)

    def test_stock_insufficient_no_partial_cart(self):
        self.repo.get_active_cart.return_value = None
        with self.assertRaises(CartConflictError):
            self.post(8)
        self.repo.create_cart.assert_not_called()
        self.repo.create_item.assert_not_called()
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once()

    def test_no_inventory_is_unavailable(self):
        self.repo.availability.return_value = []
        with self.assertRaises(CartConflictError):
            self.post()

    def test_availability_never_sums_branches(self):
        self.repo.availability.return_value = [
            dict(stock_actual=4, stock_reservado=1),
            dict(stock_actual=5, stock_reservado=1),
        ]
        with self.assertRaises(CartConflictError):
            self.post(5)
        self.assertEqual(self.post(4).items[0].disponibilidad_actual, 4)

    def test_patch_sets_final_quantity(self):
        self.add_row(quantity=2)
        data = self.update(5)
        self.assertEqual(data.items[0].cantidad, 5)
        self.repo.create_item.assert_not_called()
        self.db.commit.assert_called_once()

    def test_patch_reduction_also_checks_available(self):
        self.add_row(quantity=9)
        with self.assertRaises(CartConflictError):
            self.update(8)
        self.assertEqual(self.rows[3]["cantidad"], 9)
        self.db.rollback.assert_called_once()

    def test_patch_missing_item(self):
        with self.assertRaises(CartNotFoundError):
            self.update()

    def test_patch_inactive_product_or_variant(self):
        self.add_row()
        for target in (self.product, self.variant):
            with self.subTest(target=target):
                target.estado = False
                with self.assertRaises(CartValidationError):
                    self.update(1)
                target.estado = True
        self.repo.update_quantity.assert_not_called()

    def test_delete_only_target_and_keeps_active_header(self):
        self.add_row()
        self.add_row(5)
        data = self.service.delete_item(11, 3)
        self.assertEqual([item.id_variante_producto for item in data.items], [5])
        self.assertEqual(data.estado, "ACTIVO")
        self.db.commit.assert_called_once()

    def test_delete_missing_item(self):
        with self.assertRaises(CartNotFoundError):
            self.service.delete_item(11, 3)
        self.db.rollback.assert_called_once()

    def test_patch_and_delete_without_active_cart(self):
        self.repo.get_active_cart.return_value = None
        for operation in (self.update, lambda: self.service.delete_item(11, 3)):
            with self.subTest(operation=operation):
                with self.assertRaises(CartNotFoundError):
                    operation()

    def test_ownership_comes_from_authenticated_user(self):
        self.post()
        self.repo.get_client.assert_called_once_with(11, for_update=True)
        self.repo.get_active_cart.assert_called_once_with(7, for_update=True)
        self.repo.get_item.assert_called_once_with(9, 3)

    def test_wrong_owner_or_state_defensively_rejected(self):
        for field, value in (("id_cliente", 999), ("estado", "CONVERTIDO"), ("estado", "ABANDONADO")):
            with self.subTest(field=field, value=value):
                previous = getattr(self.cart, field)
                setattr(self.cart, field, value)
                with self.assertRaises(CartConflictError):
                    self.post()
                setattr(self.cart, field, previous)

    def test_get_inactive_items_preserved_with_current_prices(self):
        for field in ("estado_producto", "estado_variante"):
            with self.subTest(field=field):
                self.add_row(**{field: False})
                data = self.service.get_cart(11)
                self.assertEqual(len(data.items), 1)
                self.assertFalse(getattr(data.items[0], field))
                self.assertEqual(data.items[0].disponibilidad_actual, 0)
                self.assertEqual(data.items[0].precio_final, Decimal("10.10"))
        self.repo.delete_item.assert_not_called()

    def test_get_out_of_stock_preserves_item(self):
        self.add_row()
        self.repo.availability.return_value = []
        item = self.service.get_cart(11).items[0]
        self.assertEqual((item.cantidad, item.disponibilidad_actual), (2, 0))

    def test_catalog_promotion_and_decimal_totals(self):
        self.add_row(quantity=3)
        self.add_row(5, quantity=2)
        self.service.catalog_repository.list_current_promotions.return_value = [self.promotion()]
        with patch.object(CatalogService, "_to_promotion", wraps=CatalogService._to_promotion) as converter:
            data = self.service.get_cart(11)
        converter.assert_called_once()
        self.service.catalog_repository.list_current_promotions.assert_called_once_with(4)
        self.assertEqual((data.cantidad_items, data.cantidad_unidades), (2, 5))
        self.assertEqual(data.items[0].subtotal_linea, Decimal("30.00"))
        self.assertEqual(data.items[0].promocion.id_promocion, 8)
        self.assertEqual(data.subtotal, Decimal("50.50"))
        self.assertEqual(data.descuento_total, Decimal("0.50"))
        self.assertEqual(data.total, Decimal("50.00"))
        self.assertIsInstance(data.total, Decimal)
        self.assertEqual(data.subtotal - data.descuento_total, data.total)

    def test_catalog_current_price_is_not_frozen(self):
        self.add_row()
        self.assertEqual(self.service.get_cart(11).total, Decimal("20.20"))
        self.rows[3]["precio"] = Decimal("11.15")
        self.assertEqual(self.service.get_cart(11).total, Decimal("22.30"))

    def test_expired_promotion_disappears_using_catalog_result(self):
        self.add_row()
        self.service.catalog_repository.list_current_promotions.return_value = [self.promotion()]
        self.assertEqual(self.service.get_cart(11).total, Decimal("20.00"))
        self.service.catalog_repository.list_current_promotions.return_value = []
        data = self.service.get_cart(11)
        self.assertIsNone(data.items[0].promocion)
        self.assertEqual(data.total, Decimal("20.20"))

    def test_precision_uses_catalog_rounding(self):
        self.add_row(quantity=3, precio=Decimal("0.10"))
        data = self.service.get_cart(11)
        self.assertEqual(data.total, Decimal("0.30"))
        self.assertEqual(data.model_dump(mode="json")["total"], "0.30")

    def test_all_operations_leave_inventory_untouched(self):
        before = dict(self.inventory)
        self.post()
        self.assertEqual(self.inventory, before)
        self.update()
        self.assertEqual(self.inventory, before)
        self.service.delete_item(11, 3)
        self.assertEqual(self.inventory, before)
        self.service.clear_cart(11)
        self.assertEqual(self.inventory, before)

    def test_clear_keeps_active_cart(self):
        self.add_row()
        data = self.service.clear_cart(11)
        self.assertEqual((data.id_carrito, data.estado, data.items), (9, "ACTIVO", []))
        self.assertEqual(data.total, Decimal("0.00"))
        self.db.commit.assert_called_once()

    def test_clear_without_cart_does_not_create(self):
        self.repo.get_active_cart.return_value = None
        self.assertIsNone(self.service.clear_cart(11).id_carrito)
        self.repo.create_cart.assert_not_called()

    def test_integrity_conflicts_on_cart_or_detail(self):
        for method in ("create_cart", "create_item"):
            with self.subTest(method=method):
                self.setUp()
                self.repo.get_active_cart.return_value = None
                getattr(self.repo, method).side_effect = IntegrityError("sql", {}, Exception("internal"))
                with self.assertRaises(CartConflictError):
                    self.post()
                self.db.rollback.assert_called_once()
                self.db.commit.assert_not_called()

    def test_commit_failure_rolls_back_every_write(self):
        for action in ("post", "patch", "delete", "clear"):
            with self.subTest(action=action):
                self.setUp()
                self.add_row()
                self.db.commit.side_effect = RuntimeError("private SQL")
                operation = {
                    "post": self.post, "patch": self.update,
                    "delete": lambda: self.service.delete_item(11, 3),
                    "clear": lambda: self.service.clear_cart(11),
                }[action]
                with self.assertRaises(CartPersistenceError):
                    operation()
                self.db.rollback.assert_called_once()
                self.db.commit.assert_called_once()

    def test_db_concurrency_errors(self):
        for code in ("40001", "40P01", "55P03", "08006"):
            with self.subTest(code=code):
                self.setUp()
                original = Exception("private")
                original.sqlstate = code
                self.repo.get_client.side_effect = DBAPIError("sql", {}, original)
                expected = CartPersistenceError if code == "08006" else CartConflictError
                with self.assertRaises(expected):
                    self.post()
                self.db.rollback.assert_called_once()


class CartSchemaTests(TestCase):
    def test_invalid_quantities_and_extra_fields(self):
        for schema, base in ((CartItemCreate, {"id_variante_producto": 3}), (CartQuantityUpdate, {})):
            for quantity in (0, -1, 1.5, "2", True, None, 2147483648):
                with self.subTest(schema=schema, quantity=quantity):
                    with self.assertRaises(ValidationError):
                        schema(**base, cantidad=quantity)
            for field in ("id_cliente", "id_usuario", "precio", "precio_final", "subtotal", "total", "descuento", "stock", "stock_actual", "stock_reservado", "stock_minimo", "sucursal", "id_sucursal", "promocion", "id_promocion", "reserva"):
                with self.subTest(schema=schema, field=field):
                    with self.assertRaises(ValidationError):
                        schema(**base, cantidad=1, **{field: 1})


class CartHttpTests(CartFixture):
    def setUp(self):
        super().setUp()
        self.app = FastAPI()
        self.app.include_router(routes.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.auth_patch = patch("app.routers.client_reservations.AuthService")
        self.auth = self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.auth.return_value.get_current_user.return_value = SimpleNamespace(id_usuario=11, rol="CLIENTE")
        service_patch = patch.object(routes, "ClientCartService", return_value=self.service)
        service_patch.start()
        self.addCleanup(service_patch.stop)

    def test_empty_get_200(self):
        self.repo.get_active_cart.return_value = None
        status, body = request(self.app)
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["total"], "0.00")
        self.assertIsNone(body["data"]["id_carrito"])

    def test_no_token_401_all_routes(self):
        for method, path, body in (
            ("GET", "", None), ("POST", "/items", dict(id_variante_producto=3, cantidad=1)),
            ("PATCH", "/items/3", dict(cantidad=1)), ("DELETE", "/items/3", None),
            ("DELETE", "/items", None),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(request(self.app, method, "/api/client/cart" + path, body, token=False)[0], 401)
        self.repo.get_client.assert_not_called()

    def test_invalid_token_401(self):
        self.auth.return_value.get_current_user.side_effect = InvalidAccessTokenError
        self.assertEqual(request(self.app)[0], 401)

    def test_non_client_roles_403(self):
        for role in ("ADMINISTRADOR", "CAJERO", "ENCARGADO_SUCURSAL", "PROVEEDOR"):
            with self.subTest(role=role):
                self.auth.return_value.get_current_user.return_value.rol = role
                self.assertEqual(request(self.app)[0], 403)
        self.repo.get_client.assert_not_called()

    def test_client_profile_missing_403(self):
        self.repo.get_client.return_value = None
        self.assertEqual(request(self.app)[0], 403)

    def test_full_http_lifecycle_without_branch(self):
        status, body = request(self.app, "POST", "/api/client/cart/items", dict(id_variante_producto=3, cantidad=2))
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["cantidad_unidades"], 2)
        status, body = request(self.app, "PATCH", "/api/client/cart/items/3", dict(cantidad=5))
        self.assertEqual((status, body["data"]["cantidad_unidades"]), (200, 5))
        status, body = request(self.app, "DELETE", "/api/client/cart/items/3")
        self.assertEqual((status, body["data"]["items"]), (200, []))
        self.assertEqual(request(self.app, "DELETE", "/api/client/cart/items")[0], 200)

    def test_http_conflict_409(self):
        self.assertEqual(request(self.app, "POST", "/api/client/cart/items", dict(id_variante_producto=3, cantidad=8))[0], 409)

    def test_http_missing_variant_404(self):
        self.repo.get_variant.return_value = None
        self.assertEqual(request(self.app, "POST", "/api/client/cart/items", dict(id_variante_producto=3, cantidad=1))[0], 404)

    def test_http_missing_items_404(self):
        self.assertEqual(request(self.app, "PATCH", "/api/client/cart/items/3", dict(cantidad=1))[0], 404)
        self.assertEqual(request(self.app, "DELETE", "/api/client/cart/items/3")[0], 404)

    def test_http_inactive_422(self):
        self.variant.estado = False
        self.assertEqual(request(self.app, "POST", "/api/client/cart/items", dict(id_variante_producto=3, cantidad=1))[0], 422)

    def test_http_extra_fields_422(self):
        for field in ("id_cliente", "precio", "stock", "sucursal"):
            with self.subTest(field=field):
                self.assertEqual(request(self.app, "POST", "/api/client/cart/items", dict(id_variante_producto=3, cantidad=1, **{field: 9}))[0], 422)
        self.repo.create_item.assert_not_called()

    def test_http_zero_and_invalid_path_422(self):
        self.assertEqual(request(self.app, "PATCH", "/api/client/cart/items/3", dict(cantidad=0))[0], 422)
        self.assertEqual(request(self.app, "DELETE", "/api/client/cart/items/0")[0], 422)

    def test_unexpected_errors_are_sanitized(self):
        self.repo.get_client.side_effect = RuntimeError("private SQL password")
        with self.assertLogs(routes.logger, level="ERROR"):
            status, body = request(self.app)
        self.assertEqual(status, 500)
        self.assertNotIn("private", json.dumps(body))
        self.assertNotIn("password", json.dumps(body))

    def test_only_requested_endpoints(self):
        paths = self.app.openapi()["paths"]
        self.assertEqual(set(paths), {"/api/client/cart", "/api/client/cart/items", "/api/client/cart/items/{id_variante_producto}"})
        self.assertEqual(set(paths["/api/client/cart/items"]), {"post", "delete"})

    def test_router_registered_in_main_without_removing_reservations(self):
        from app.main import app

        paths = app.openapi()["paths"]
        self.assertIn("/api/client/cart", paths)
        self.assertIn("/api/client/reservations", paths)
        self.assertIn("/api/staff/reservations", paths)


class CartRepositoryTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.repo = ClientCartRepository(self.db)

    def sql(self, statement):
        return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    def test_active_cart_scoped_to_owner_and_locked(self):
        self.repo.get_active_cart(7, for_update=True)
        sql = self.sql(self.db.scalar.call_args.args[0])
        self.assertIn("t_carrito.id_cliente = 7", sql)
        self.assertIn("t_carrito.estado = 'ACTIVO'", sql)
        self.assertIn("FOR UPDATE", sql)

    def test_client_lock_serializes_creation(self):
        self.repo.get_client(11, for_update=True)
        sql = self.sql(self.db.scalar.call_args.args[0])
        self.assertIn("t_cliente.id_usuario = 11", sql)
        self.assertIn("FOR UPDATE", sql)

    def test_item_lookup_requires_cart_and_variant(self):
        self.repo.get_item(9, 3)
        sql = self.sql(self.db.scalar.call_args.args[0])
        self.assertIn("t_detalle_carrito.id_carrito = 9", sql)
        self.assertIn("t_detalle_carrito.id_variante_producto = 3", sql)

    def test_get_items_does_not_filter_inactive(self):
        self.repo.list_items(9)
        sql = self.sql(self.db.execute.call_args.args[0])
        self.assertIn("t_detalle_carrito.id_carrito = 9", sql)
        self.assertNotIn("estado IS true", sql)
        self.assertNotIn("FOR UPDATE", sql)

    def test_availability_reuses_cu13_without_stock_locks(self):
        self.repo.availability(4, 3)
        sql = self.sql(self.db.execute.call_args.args[0])
        self.assertIn("t_sucursal.estado IS true", sql)
        self.assertIn("t_variante_producto.id_variante_producto = 3", sql)
        self.assertNotIn("FOR UPDATE", sql)
        self.assertNotIn("sum(", sql.lower())

    def test_repository_writes_only_cart_entities_never_commits(self):
        cart = self.repo.create_cart(7)
        item = self.repo.create_item(9, 3, 2)
        self.repo.update_quantity(item, 5)
        self.assertEqual(item.cantidad, 5)
        self.repo.delete_item(item)
        self.repo.clear_items(9)
        self.assertIsInstance(cart, Cart)
        self.assertEqual(cart.estado, "ACTIVO")
        self.assertEqual([type(call.args[0]) for call in self.db.add.call_args_list], [Cart, CartDetail])
        self.db.delete.assert_called_once_with(item)
        sql = self.sql(self.db.execute.call_args.args[0])
        self.assertTrue(sql.startswith("DELETE FROM t_detalle_carrito"))
        self.assertIn("t_detalle_carrito.id_carrito = 9", sql)
        self.db.commit.assert_not_called()
