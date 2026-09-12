"""CU13: unittest, mocks y SQL PostgreSQL compilado; sin conexion a BD."""

import asyncio
import json
from datetime import time
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit
from unittest import TestCase
from unittest.mock import MagicMock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.main import app
from app.repositories.catalog_availability import CatalogAvailabilityRepository
from app.routers import catalog_availability as routes
from app.services.catalog_availability import (
    AvailabilityNotFoundError, AvailabilityValidationError, CatalogAvailabilityService,
)


def row(**changes):
    return dict(
        id_variante_producto=25, sku="CAM-OXF-M-BLANCO", variante_estado=True,
        id_talla=3, talla="M", id_color=4, color="Blanco", codigo_hex="#FFFFFF",
        id_sucursal=1, nombre_sucursal="Centro", id_ciudad=2, nombre_ciudad="La Paz",
        direccion="Av. Principal", hora_apertura=time(8), hora_cierre=time(20),
        stock_actual=20, stock_reservado=0,
    ) | changes


def http_get(url, params=None):
    """Ejecuta el stack HTTP ASGI real sin dependencias HTTP adicionales."""
    parsed = urlsplit(url)
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = dict(type="http", asgi={"version": "3.0"}, http_version="1.1",
                 method="GET", scheme="http", path=parsed.path,
                 raw_path=parsed.path.encode(), root_path="",
                 query_string=(urlencode(params) if params else parsed.query).encode(),
                 headers=[], client=("127.0.0.1", 1234), server=("test", 80))
    asyncio.run(app(scope, receive, send))
    body = b"".join(item.get("body", b"") for item in messages).decode()
    return SimpleNamespace(status_code=messages[0]["status"], text=body,
                           json=lambda: json.loads(body))


class AvailabilityServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = CatalogAvailabilityService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.repo.get_product.return_value = SimpleNamespace(
            id_producto=10, nombre="Camisa Oxford", estado=True,
        )
        self.repo.get_variant.return_value = SimpleNamespace(id_producto=10, estado=True)
        self.repo.list_availability.return_value = [row()]

    def test_valid_product(self):
        result = self.service.get_availability(10)
        self.assertEqual(result.producto.id_producto, 10)
        self.assertEqual(result.producto.nombre, "Camisa Oxford")
        self.assertTrue(result.producto.estado)

    def test_valid_variant(self):
        result = self.service.get_availability(10, id_variante_producto=25)
        variant = result.disponibilidad[0].variante
        self.assertEqual(variant.id_variante_producto, 25)
        self.assertEqual((variant.talla.nombre, variant.color.nombre), ("M", "Blanco"))
        self.assertTrue(variant.estado)
        self.repo.get_variant.assert_called_once_with(25)

    def test_missing_product(self):
        self.repo.get_product.return_value = None
        with self.assertRaises(AvailabilityNotFoundError):
            self.service.get_availability(10)
        self.repo.list_availability.assert_not_called()

    def test_inactive_product(self):
        self.repo.get_product.return_value.estado = False
        with self.assertRaises(AvailabilityNotFoundError):
            self.service.get_availability(10)

    def test_missing_variant(self):
        self.repo.get_variant.return_value = None
        with self.assertRaises(AvailabilityNotFoundError):
            self.service.get_availability(10, id_variante_producto=25)

    def test_inactive_variant(self):
        self.repo.get_variant.return_value.estado = False
        with self.assertRaises(AvailabilityNotFoundError):
            self.service.get_availability(10, id_variante_producto=25)

    def test_variant_belongs_to_another_product(self):
        self.repo.get_variant.return_value.id_producto = 11
        with self.assertRaises(AvailabilityValidationError):
            self.service.get_availability(10, id_variante_producto=25)
        self.repo.list_availability.assert_not_called()

    def test_one_branch(self):
        result = self.service.get_availability(10).disponibilidad
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0].nombre_sucursal, result[0].nombre_ciudad),
                         ("Centro", "La Paz"))
        self.assertEqual((result[0].hora_apertura, result[0].hora_cierre),
                         (time(8), time(20)))

    def test_multiple_branches_preserve_query_order(self):
        self.repo.list_availability.return_value = [row(), row(id_sucursal=2, nombre_sucursal="Norte")]
        result = self.service.get_availability(10).disponibilidad
        self.assertEqual([item.id_sucursal for item in result], [1, 2])

    def test_actual_stock_twenty(self):
        self.assertEqual(self.service.get_availability(10).disponibilidad[0].stock_actual, 20)

    def test_reserved_stock_zero(self):
        self.assertEqual(self.service.get_availability(10).disponibilidad[0].stock_reservado, 0)

    def test_available_stock_twenty(self):
        self.assertEqual(self.service.get_availability(10).disponibilidad[0].stock_disponible, 20)

    def test_reserved_stock_subtracted(self):
        self.repo.list_availability.return_value = [row(stock_reservado=2)]
        self.assertEqual(self.service.get_availability(10).disponibilidad[0].stock_disponible, 18)

    def test_available_stock_never_negative(self):
        self.repo.list_availability.return_value = [row(stock_reservado=30)]
        self.assertEqual(self.service.get_availability(10).disponibilidad[0].stock_disponible, 0)

    def test_zero_stock_visible(self):
        self.repo.list_availability.return_value = [row(stock_actual=0)]
        result = self.service.get_availability(10).disponibilidad
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].stock_disponible, 0)

    def test_variant_without_inventory(self):
        self.repo.list_availability.return_value = []
        self.assertEqual(self.service.get_availability(10, id_variante_producto=25).disponibilidad, [])

    def test_product_without_inventory(self):
        self.repo.list_availability.return_value = []
        self.assertEqual(self.service.get_availability(10).disponibilidad, [])

    def test_no_inventory_mutation(self):
        original = row()
        self.repo.list_availability.return_value = [original]
        self.service.get_availability(10)
        self.assertEqual(original, row())
        for name in ("add", "delete", "flush", "merge", "commit"):
            getattr(self.db, name).assert_not_called()


class AvailabilityRepositoryTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.execute.return_value.mappings.return_value.all.return_value = []
        self.repo = CatalogAvailabilityRepository(self.db)

    def query(self, **filters):
        self.repo.list_availability(10, **filters)
        return self.db.execute.call_args.args[0].compile(dialect=postgresql.dialect())

    def test_inactive_branches_products_variants_excluded(self):
        sql = str(self.query())
        for table in ("t_sucursal", "t_producto", "t_variante_producto"):
            self.assertIn(f"{table}.estado IS true", sql)
        self.assertNotIn("stock_actual >", sql)

    def test_branch_filter(self):
        self.assert_filter("id_sucursal", "t_sucursal.id_sucursal")

    def test_city_filter(self):
        self.assert_filter("id_ciudad", "t_ciudad.id_ciudad")

    def test_size_filter(self):
        self.assert_filter("id_talla", "t_variante_producto.id_talla")

    def test_color_filter(self):
        self.assert_filter("id_color", "t_variante_producto.id_color")

    def test_variant_filter(self):
        self.assert_filter("id_variante_producto", "t_variante_producto.id_variante_producto")

    def assert_filter(self, name, column):
        query = self.query(**{name: 37})
        self.assertIn(f"{column} =", str(query).split("WHERE")[1])
        self.assertIn(37, query.params.values())

    def test_stable_order_with_tie_breakers(self):
        self.assertIn("ORDER BY t_ciudad.nombre, t_ciudad.id_ciudad, "
                      "t_sucursal.nombre, t_sucursal.id_sucursal, "
                      "t_variante_producto.id_variante_producto", str(self.query()))

    def test_only_required_explicit_joins_and_read_operations(self):
        sql = str(self.query())
        self.assertEqual(sql.count(" JOIN "), 6)
        self.assertEqual(sql.count(" ON "), 6)
        for unwanted in ("t_promocion", "t_proveedor", "t_temporada", "t_coleccion", "t_usuario", "FOR UPDATE"):
            self.assertNotIn(unwanted, sql)
        self.assertTrue(sql.startswith("SELECT"))
        for name in ("commit", "flush", "add", "delete", "merge"):
            getattr(self.db, name).assert_not_called()


class AvailabilityRouteTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        app.dependency_overrides[get_db] = lambda: self.db
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.client = SimpleNamespace(get=http_get)
        self.url = "/api/catalog/products/10/availability"

    def test_public_http_without_jwt_and_empty_inventory(self):
        with patch.object(routes, "CatalogAvailabilityService") as service:
            service.return_value.get_availability.return_value = dict(
                producto=dict(id_producto=10, nombre="Camisa", estado=True), disponibilidad=[],
            )
            response = self.client.get(self.url + "?id_variante_producto=25&id_sucursal=1&id_ciudad=2&id_talla=3&id_color=4")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["data"]["disponibilidad"], [])
            self.assertEqual(set(response.json()), {"success", "data", "message"})
            service.return_value.get_availability.assert_called_once_with(
                10, id_variante_producto=25, id_sucursal=1, id_ciudad=2, id_talla=3, id_color=4,
            )
        self.db.commit.assert_not_called()

    def test_openapi_public_and_unique_route(self):
        spec = app.openapi()["paths"]["/api/catalog/products/{id_producto}/availability"]
        self.assertEqual(set(spec), {"get"})
        self.assertFalse(spec["get"].get("security"))
        self.assertEqual(len(routes.router.routes), 1)

    def test_error_statuses_and_private_details_hidden(self):
        for error, expected in ((AvailabilityNotFoundError("No encontrado"), 404),
                                (AvailabilityValidationError("Variante ajena"), 400),
                                (SQLAlchemyError("private database"), 500),
                                (RuntimeError("private unexpected"), 500)):
            with self.subTest(error=error), patch.object(routes, "CatalogAvailabilityService") as service, patch.object(routes.logger, "exception"):
                service.return_value.get_availability.side_effect = error
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, expected)
                self.assertFalse(response.json()["success"])
                self.assertIsNone(response.json()["data"])
                self.assertNotIn("private", response.text)
        self.db.commit.assert_not_called()

    def test_nonpositive_ids_rejected_before_service(self):
        with patch.object(routes, "CatalogAvailabilityService") as service:
            for name in ("id_variante_producto", "id_sucursal", "id_ciudad", "id_talla", "id_color"):
                self.assertEqual(self.client.get(self.url, params={name: 0}).status_code, 422)
            self.assertEqual(self.client.get("/api/catalog/products/0/availability").status_code, 422)
            service.assert_not_called()
