"""CU21: transacciones reales en SQLite local y SQL de bloqueos PostgreSQL."""
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

import app.models  # registra las tablas referenciadas por las claves foráneas
from app.models.cart import Cart
from app.models.cart_detail import CartDetail
from app.models.branch_inventory import BranchInventory
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.repositories.client_checkout import ClientCheckoutRepository
from app.routers import client_checkout as routes
from app.schemas.client_checkout import CheckoutRequest
from app.services.client_cart import CartConflictError, CartNotFoundError, CartPersistenceError, CartValidationError
from app.services.client_checkout import ClientCheckoutService
from app.core.database import get_db
from app.routers.client_reservations import require_client
from tests.test_client_cart import request


class CheckoutTransactionTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        for table in (Cart.__table__, CartDetail.__table__, BranchInventory.__table__, Sale.__table__, SaleDetail.__table__):
            table.create(self.engine)
        self.db = Session(self.engine)
        self.db.add(Cart(id_carrito=9, id_cliente=7, estado="ACTIVO"))
        self.db.add(CartDetail(id_carrito=9, id_variante_producto=3, cantidad=2))
        self.db.add(BranchInventory(id_sucursal=2, id_variante_producto=3, stock_actual=10, stock_reservado=3, stock_minimo=0))
        self.db.commit()
        self.service = ClientCheckoutService(self.db)
        self.service.repository.get_client = MagicMock(return_value=NS(id_cliente=7))
        self.service.checkout.lock_branch = MagicMock(return_value=NS(id_sucursal=2, estado=True))
        self.service.checkout.lock_variant = MagicMock(return_value=(NS(estado=True), NS(estado=True, id_producto=4, precio=Decimal("10.10"))))
        self.service.catalog_repository.list_current_promotions = MagicMock(return_value=[])
        self.payload = CheckoutRequest(id_carrito=9, id_sucursal=2)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def confirm(self):
        return self.service.confirm(11, self.payload)

    def inventory(self):
        return self.db.scalar(select(BranchInventory))

    def assert_unchanged(self):
        self.assertEqual(self.db.get(Cart, 9).estado, "ACTIVO")
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (10, 3))
        self.assertEqual(self.db.scalars(select(Sale)).all(), [])
        self.assertEqual(self.db.scalars(select(SaleDetail)).all(), [])

    def test_valid_cart_historical_prices_pending_digital_stock_and_cart(self):
        result = self.confirm()
        self.assertEqual((result.canal, result.estado, result.moneda), ("DIGITAL", "PENDIENTE", "BOB"))
        self.assertEqual((result.id_cliente, result.id_carrito, result.id_sucursal), (7, 9, 2))
        self.assertEqual((result.subtotal, result.total), (Decimal("20.20"), Decimal("20.20")))
        self.assertEqual(result.items[0].precio_unitario, Decimal("10.10"))
        self.assertTrue(result.stock_comprometido)
        sale = self.db.get(Sale, result.id_venta)
        self.assertIsNone(sale.id_empleado)
        self.assertIsNone(sale.fecha_completada)
        self.assertIsNone(sale.id_reserva)
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (10, 5))
        self.assertEqual(self.db.get(Cart, 9).estado, "CONVERTIDO")
        self.assertEqual(len(self.db.scalars(select(CartDetail)).all()), 1)

    def test_configurable_expiration(self):
        with patch("app.services.client_checkout.settings") as config:
            config.DIGITAL_CHECKOUT_TTL_MINUTES = 45
            result = self.confirm()
        sale = self.db.get(Sale, result.id_venta)
        self.assertEqual(sale.fecha_expiracion_pago - sale.created_at, timedelta(minutes=45))

    def test_empty_cart(self):
        self.db.delete(self.db.scalar(select(CartDetail)))
        self.db.commit()
        with self.assertRaises(CartValidationError):
            self.confirm()
        self.assert_unchanged()

    def test_insufficient_stock_includes_existing_reservations(self):
        self.db.scalar(select(CartDetail)).cantidad = 8
        self.db.commit()
        with self.assertRaises(CartConflictError):
            self.confirm()
        self.assert_unchanged()

    def test_exact_available_stock(self):
        self.db.scalar(select(CartDetail)).cantidad = 7
        self.db.commit()
        self.confirm()
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (10, 10))

    def test_missing_inventory(self):
        self.service.checkout.lock_inventories = MagicMock(return_value=[])
        with self.assertRaises(CartConflictError):
            self.confirm()
        self.assert_unchanged()

    def test_inactive_variant_or_product(self):
        for variant, product in ((False, True), (True, False)):
            self.service.checkout.lock_variant.return_value = (NS(estado=variant), NS(estado=product))
            with self.assertRaises(CartValidationError):
                self.confirm()
            self.assert_unchanged()

    def test_promotions_follow_catalog_policy_and_persist_discount(self):
        self.service.catalog_repository.list_current_promotions.return_value = [dict(
            id_promocion=8, promocion_nombre="Oferta", promocion_codigo=None,
            promocion_descripcion=None, tipo_descuento="PORCENTAJE", valor_descuento=Decimal("10"),
            precio_resultante=Decimal("9.09"), fecha_inicio=datetime(2026, 1, 1),
            fecha_fin=datetime(2027, 1, 1), acumulable=False,
        )]
        result = self.confirm()
        self.assertEqual((result.subtotal, result.descuento_total, result.total),
                         (Decimal("20.20"), Decimal("2.02"), Decimal("18.18")))
        self.assertEqual((result.items[0].id_promocion, result.items[0].descuento_unitario), (8, Decimal("1.01")))

    def test_double_attempt_returns_same_sale_without_reserving_again(self):
        first, second = self.confirm(), self.confirm()
        self.assertEqual(first.model_dump(), second.model_dump())
        self.assertEqual(self.inventory().stock_reservado, 5)
        self.assertEqual(len(self.db.scalars(select(Sale)).all()), 1)

    def test_retry_different_branch_rejected(self):
        self.confirm()
        self.payload.id_sucursal = 5
        with self.assertRaises(CartConflictError):
            self.confirm()
        self.assertEqual(self.inventory().stock_reservado, 5)

    def test_expired_sale_not_reserved_again(self):
        result = self.confirm()
        sale = self.db.get(Sale, result.id_venta)
        sale.created_at = datetime(2025, 1, 1)
        sale.fecha_expiracion_pago = datetime(2025, 1, 2)
        self.db.commit()
        with self.assertRaises(CartConflictError):
            self.confirm()
        self.assertEqual(self.inventory().stock_reservado, 5)

    def test_error_after_stock_and_cart_changes_rolls_back_everything(self):
        self.service._sale_data = MagicMock(side_effect=RuntimeError("fallo posterior al flush"))
        with self.assertRaises(CartPersistenceError):
            self.confirm()
        self.assert_unchanged()

    def test_bad_second_item_rolls_back(self):
        self.db.add(CartDetail(id_carrito=9, id_variante_producto=5, cantidad=2))
        self.db.commit()
        with self.assertRaises(CartConflictError):
            self.confirm()
        self.assert_unchanged()

    def test_owned_pending_sale_and_other_client_denied(self):
        result = self.confirm()
        self.assertEqual(self.service.get_pending_sale(11, result.id_venta).model_dump(), result.model_dump())
        self.service.repository.get_client.return_value = NS(id_cliente=99)
        with self.assertRaises(CartNotFoundError):
            self.service.get_pending_sale(12, result.id_venta)

    def test_cart_of_other_client_denied(self):
        self.service.repository.get_client.return_value = NS(id_cliente=99)
        with self.assertRaises(CartNotFoundError):
            self.confirm()
        self.assert_unchanged()


class CheckoutContractTests(TestCase):
    def test_rejects_prices_and_reservation_payloads(self):
        for extra in (dict(total=1), dict(id_reserva=3), dict(items=[])):
            with self.assertRaises(ValidationError):
                CheckoutRequest(id_carrito=9, id_sucursal=2, **extra)

    def test_postgresql_locking(self):
        db = MagicMock()
        repo = ClientCheckoutRepository(db)
        for operation, method, expected in (
            (lambda: repo.lock_cart(9, 7), db.scalar, "FOR UPDATE"),
            (lambda: repo.lock_items(9), db.scalars, "FOR UPDATE"),
            (lambda: repo.lock_variant(3), db.execute, "FOR SHARE"),
            (lambda: repo.lock_branch(2), db.scalar, "FOR SHARE"),
            (lambda: repo.lock_inventories(2, [5, 3]), db.scalars, "FOR UPDATE"),
        ):
            operation()
            sql = str(method.call_args.args[0].compile(dialect=postgresql.dialect()))
            self.assertIn(expected, sql)
        self.assertIn("ORDER BY", sql)

    def test_routes_require_authentication(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        for method, path, body in (
            ("POST", "/api/client/cart/checkout", dict(id_carrito=9, id_sucursal=2)),
            ("GET", "/api/client/sales/1", None),
        ):
            status, _ = request(app, method, path, body, token=False)
            self.assertEqual(status, 401)

    def test_route_validation_and_conflict(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[require_client] = lambda: NS(id_usuario=11)
        status, _ = request(app, "POST", "/api/client/cart/checkout", dict(id_carrito=9, id_sucursal=2, total=1))
        self.assertEqual(status, 422)
        with patch.object(routes.ClientCheckoutService, "confirm", side_effect=CartConflictError("Stock insuficiente")):
            status, _ = request(app, "POST", "/api/client/cart/checkout", dict(id_carrito=9, id_sucursal=2))
        self.assertEqual(status, 409)
