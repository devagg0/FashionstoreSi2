"""CU14: mocks y compilación SQL; no abre conexiones a la BD."""

from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.core.database import get_db
from app.repositories.inventory import InventoryRepository
from app.routers import admin_inventory as routes
from app.routers.admin_users import require_administrator
from app.schemas.admin_inventory import InventoryCreateRequest, InventoryUpdateRequest
from app.services.admin_inventory import (
    AdminInventoryService, InventoryConflictError, InventoryNotFoundError,
    InventoryPersistenceError, InventoryValidationError,
)


def payload(**values):
    return InventoryCreateRequest(**(dict(id_sucursal=1, id_variante_producto=2) | values))


def row(**values):
    return dict(
        id_inventario_sucursal=3, id_sucursal=1, sucursal="Centro", sucursal_estado=True,
        id_ciudad=4, ciudad="La Paz", id_producto=5, producto="Camisa", producto_estado=True,
        id_variante_producto=2, sku="CAM-2", variante_estado=True,
        id_talla=6, talla="M", id_color=7, color="Azul",
        stock_actual=10, stock_reservado=3, stock_minimo=0,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    ) | values


class InventorySchemaTests(TestCase):
    def test_default_minimum(self):
        self.assertEqual(payload().stock_minimo, 0)

    def test_custom_minimum(self):
        self.assertEqual(payload(stock_minimo=8).stock_minimo, 8)

    def test_negative_and_non_integer_minimum(self):
        for value in (-1, 1.5, True, "2", None):
            for schema in (payload, InventoryUpdateRequest):
                with self.subTest(value=value, schema=schema), self.assertRaises(ValidationError):
                    schema(stock_minimo=value)

    def test_create_forbidden_fields(self):
        for field in ("stock_actual", "stock_reservado", "estado"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                payload(**{field: 1})

    def test_patch_forbidden_fields(self):
        for field in ("stock_actual", "stock_reservado", "id_sucursal", "id_variante_producto", "estado"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                InventoryUpdateRequest(stock_minimo=1, **{field: 1})

    def test_patch_requires_minimum(self):
        with self.assertRaises(ValidationError):
            InventoryUpdateRequest()


class InventoryServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminInventoryService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.repo.get_branch.return_value = SimpleNamespace(estado=True)
        self.repo.get_variant.return_value = (SimpleNamespace(estado=True), SimpleNamespace(estado=True))
        self.repo.get_by_branch_variant.return_value = None
        self.inventory = SimpleNamespace(**row())
        self.repo.create.return_value = self.inventory
        self.repo.get_inventory.return_value = self.inventory
        self.repo.get_detail.side_effect = lambda _: vars(self.inventory)

    def assert_create_error(self, error):
        with self.assertRaises(error):
            self.service.create_inventory(payload())
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.repo.create.assert_not_called()

    def test_create_valid_default(self):
        result = self.service.create_inventory(payload())
        self.assertEqual(result.id_inventario_sucursal, 3)
        self.repo.create.assert_called_once_with(1, 2, 0)
        self.db.flush.assert_called_once()
        self.db.commit.assert_called_once()

    def test_create_custom_minimum(self):
        self.service.create_inventory(payload(stock_minimo=8))
        self.repo.create.assert_called_once_with(1, 2, 8)

    def test_missing_branch(self):
        self.repo.get_branch.return_value = None
        self.assert_create_error(InventoryNotFoundError)

    def test_inactive_branch(self):
        self.repo.get_branch.return_value.estado = False
        self.assert_create_error(InventoryValidationError)

    def test_missing_variant(self):
        self.repo.get_variant.return_value = None
        self.assert_create_error(InventoryNotFoundError)

    def test_inactive_variant(self):
        self.repo.get_variant.return_value[0].estado = False
        self.assert_create_error(InventoryValidationError)

    def test_missing_product(self):
        self.repo.get_variant.return_value = (SimpleNamespace(estado=True), None)
        self.assert_create_error(InventoryNotFoundError)

    def test_inactive_product(self):
        self.repo.get_variant.return_value[1].estado = False
        self.assert_create_error(InventoryValidationError)

    def test_duplicate(self):
        self.repo.get_by_branch_variant.return_value = self.inventory
        self.assert_create_error(InventoryConflictError)

    def test_concurrent_unique_conflict(self):
        self.db.flush.side_effect = IntegrityError("insert", {}, Exception())
        with self.assertRaises(InventoryConflictError):
            self.service.create_inventory(payload())
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_concurrent_database_conflicts(self):
        for code in ("40001", "40P01", "55P03"):
            with self.subTest(code=code):
                self.db.reset_mock()
                self.db.commit.side_effect = DBAPIError("update", {}, SimpleNamespace(sqlstate=code))
                with self.assertRaises(InventoryConflictError):
                    self.service.update_inventory(3, InventoryUpdateRequest(stock_minimo=2))
                self.db.rollback.assert_called_once()

    def test_patch_only_minimum_and_timestamp(self):
        before = vars(self.inventory).copy()
        result = self.service.update_inventory(3, InventoryUpdateRequest(stock_minimo=9))
        self.assertEqual(result.stock_minimo, 9)
        self.assertGreater(result.updated_at, before["updated_at"])
        for key in before.keys() - {"stock_minimo", "updated_at"}:
            self.assertEqual(getattr(self.inventory, key), before[key])
        self.db.flush.assert_called_once()
        self.db.commit.assert_called_once()

    def test_patch_missing_inventory(self):
        self.repo.get_inventory.return_value = None
        with self.assertRaises(InventoryNotFoundError):
            self.service.update_inventory(3, InventoryUpdateRequest(stock_minimo=1))
        self.db.rollback.assert_called_once()

    def test_detail_missing_inventory(self):
        self.repo.get_detail.side_effect = None
        self.repo.get_detail.return_value = None
        with self.assertRaises(InventoryNotFoundError):
            self.service.get_inventory(3)

    def test_enriched_detail_and_available_stock(self):
        result = self.service.get_inventory(3)
        self.assertEqual(result.model_dump(), row() | {"stock_disponible": 7})

    def test_available_stock_clamped(self):
        self.inventory.stock_actual = 1
        self.assertEqual(self.service.get_inventory(3).stock_disponible, 0)

    def test_list_pagination(self):
        self.repo.list_inventory.return_value = ([row()], 21)
        data, pagination = self.service.list_inventory(page=2, page_size=20, id_sucursal=1)
        self.assertEqual(data[0].stock_disponible, 7)
        self.assertEqual(pagination.model_dump(), dict(page=2, page_size=20, total=21, total_pages=2))
        self.repo.list_inventory.assert_called_once_with(page=2, page_size=20, id_sucursal=1)

    def test_empty_list(self):
        self.repo.list_inventory.return_value = ([], 0)
        data, pagination = self.service.list_inventory()
        self.assertEqual(data, [])
        self.assertEqual(pagination.total_pages, 0)

    def test_inactive_history_visible(self):
        for field in ("sucursal_estado", "variante_estado", "producto_estado"):
            with self.subTest(field=field):
                setattr(self.inventory, field, False)
                self.repo.list_inventory.return_value = ([vars(self.inventory)], 1)
                self.assertFalse(getattr(self.service.get_inventory(3), field))
                data, _ = self.service.list_inventory()
                self.assertFalse(getattr(data[0], field))
        self.repo.get_branch.assert_not_called()
        self.repo.get_variant.assert_not_called()

    def test_rollback_post_and_patch(self):
        for operation in (lambda: self.service.create_inventory(payload()),
                          lambda: self.service.update_inventory(3, InventoryUpdateRequest(stock_minimo=1))):
            for error in (SQLAlchemyError(), RuntimeError(), DBAPIError("sql", {}, Exception())):
                with self.subTest(operation=operation, error=error):
                    self.db.reset_mock()
                    self.db.commit.side_effect = error
                    with self.assertRaises(InventoryPersistenceError):
                        operation()
                    self.db.rollback.assert_called_once()


class InventoryRepositoryTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.repo = InventoryRepository(self.db)

    def test_create_zero_stock_without_commit(self):
        for minimum in (0, 8):
            inventory = self.repo.create(1, 2, minimum)
            self.assertEqual(inventory.stock_actual, 0)
            self.assertEqual(inventory.stock_reservado, 0)
            self.assertEqual(inventory.stock_minimo, minimum)
            self.assertEqual((inventory.id_sucursal, inventory.id_variante_producto), (1, 2))
        self.db.commit.assert_not_called()
        self.db.flush.assert_not_called()

    def statements(self, **filters):
        self.repo.list_inventory(**filters)
        return self.db.scalar.call_args.args[0], self.db.execute.call_args.args[0]

    def test_all_filters_shared_by_count_and_list(self):
        for field, column in (
            ("id_sucursal", "t_inventario_sucursal.id_sucursal"),
            ("id_ciudad", "t_sucursal.id_ciudad"),
            ("id_categoria", "t_producto.id_categoria"),
            ("id_producto", "t_producto.id_producto"),
            ("id_variante_producto", "t_inventario_sucursal.id_variante_producto"),
            ("id_talla", "t_variante_producto.id_talla"),
            ("id_color", "t_variante_producto.id_color"),
        ):
            with self.subTest(field=field):
                count, listing = self.statements(**{field: 17})
                for statement in (count, listing):
                    compiled = statement.compile(dialect=postgresql.dialect())
                    self.assertIn(column + " =", str(compiled))
                    self.assertIn(17, compiled.params.values())
                self.assertEqual(str(count.get_final_froms()[0].element.whereclause), str(listing.whereclause))

    def test_product_and_sku_search_escaped(self):
        for search in ("Camisa", "CAM-2", " %_\\ "):
            with self.subTest(search=search):
                for statement in self.statements(search=search):
                    compiled = statement.compile(dialect=postgresql.dialect())
                    self.assertIn("t_producto.nombre ILIKE", str(compiled))
                    self.assertIn("t_variante_producto.sku ILIKE", str(compiled))
                    expected = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                    self.assertEqual(list(compiled.params.values()).count(expected), 2)
                    self.assertIn("ESCAPE", str(compiled))

    def test_pagination_and_order(self):
        count, listing = self.statements(page=3, page_size=5)
        self.assertEqual(listing._offset_clause.value, 10)
        self.assertEqual(listing._limit_clause.value, 5)
        self.assertIn("ORDER BY t_inventario_sucursal.id_inventario_sucursal", str(listing))
        self.assertNotIn("LIMIT", str(count))

    def test_explicit_detail_joins_and_history(self):
        self.repo.get_detail(3)
        statement = self.db.execute.call_args.args[0]
        sql = str(statement)
        for table in ("t_sucursal", "t_ciudad", "t_producto", "t_variante_producto", "t_talla", "t_color"):
            self.assertIn("JOIN " + table + " ON", sql)
        for table in ("t_proveedor", "t_promocion", "t_coleccion", "t_imagen"):
            self.assertNotIn(table, sql)
        self.assertNotIn("estado", str(statement.whereclause))
        _, listing = self.statements()
        self.assertIsNone(listing.whereclause)


class InventoryRouterTests(TestCase):
    def test_exact_endpoints_and_validation_contract(self):
        app = FastAPI()
        app.include_router(routes.router)
        paths = app.openapi()["paths"]
        self.assertEqual(set(paths), {"/api/admin/inventory", "/api/admin/inventory/{id_inventario_sucursal}"})
        self.assertEqual(set(paths["/api/admin/inventory"]), {"get", "post"})
        self.assertEqual(set(paths["/api/admin/inventory/{id_inventario_sucursal}"]), {"get", "patch"})
        for operations in paths.values():
            for operation in operations.values():
                self.assertIn("422", operation["responses"])
        params = {p["name"]: p["schema"] for p in paths["/api/admin/inventory"]["get"]["parameters"]}
        self.assertEqual(params["page"]["minimum"], 1)
        self.assertEqual(params["page_size"]["maximum"], 100)
        self.assertIn("201", paths["/api/admin/inventory"]["post"]["responses"])

    def test_create_response(self):
        with patch.object(routes, "AdminInventoryService") as service:
            service.return_value.create_inventory.return_value = AdminInventoryService._data(row(stock_actual=0, stock_reservado=0))
            response = routes.create_inventory(payload(), SimpleNamespace(), MagicMock())
        self.assertTrue(response.success)
        self.assertEqual(response.data.stock_disponible, 0)

    def test_list_and_patch_responses(self):
        db = MagicMock()
        with patch.object(routes, "AdminInventoryService") as service:
            service.return_value.list_inventory.return_value = (
                [AdminInventoryService._data(row())],
                dict(page=1, page_size=20, total=1, total_pages=1),
            )
            response = routes.list_inventory(SimpleNamespace(), search="CAM", id_sucursal=1, db=db)
            self.assertEqual(response.pagination.total, 1)
            self.assertEqual(service.return_value.list_inventory.call_args.kwargs["search"], "CAM")
            service.return_value.update_inventory.return_value = AdminInventoryService._data(row(stock_minimo=2))
            result = routes.update_inventory(3, InventoryUpdateRequest(stock_minimo=2), SimpleNamespace(), db)
            self.assertEqual(result.data.stock_minimo, 2)

    def test_error_mapping(self):
        for error, status in ((InventoryNotFoundError("missing"), 404),
                              (InventoryValidationError("inactive"), 400),
                              (InventoryConflictError("duplicate"), 409), (RuntimeError("secret"), 500)):
            with self.subTest(status=status), patch.object(routes, "AdminInventoryService") as service:
                service.return_value.get_inventory.side_effect = error
                response = routes.get_inventory(3, SimpleNamespace(), MagicMock())
                self.assertEqual(response.status_code, status)
                self.assertNotIn(b"secret", response.body)

    def test_auth_denial_all_endpoints(self):
        for status in (401, 403):
            denied = routes.JSONResponse(status_code=status, content={"success": False})
            with patch.object(routes, "AdminInventoryService") as service:
                responses = [
                    routes.list_inventory(denied, db=MagicMock()),
                    routes.get_inventory(3, denied, MagicMock()),
                    routes.create_inventory(payload(), denied, MagicMock()),
                    routes.update_inventory(3, InventoryUpdateRequest(stock_minimo=2), denied, MagicMock()),
                ]
                for response in responses:
                    self.assertIs(response, denied)
                service.assert_not_called()
        for route in routes.router.routes:
            self.assertIn(require_administrator, [dependency.call for dependency in route.dependant.dependencies])
