"""CU16: mocks, SQL PostgreSQL y SELECT sobre fixtures CTE en memoria; sin BD externa."""

import asyncio
import json
import sqlite3
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

from fastapi import FastAPI
from sqlalchemy.dialects import postgresql, sqlite

from app.core.database import get_db
from app.repositories.global_inventory import GlobalInventoryRepository
from app.routers import admin_global_inventory as routes
from app.routers.admin_users import require_administrator
from app.services.admin_global_inventory import AdminGlobalInventoryService, GlobalInventoryNotFoundError


class ASGIClient:
    """Cliente mínimo como CU13, sin dependencias HTTP adicionales."""

    def __init__(self, app):
        self.app = app

    def get(self, url):
        parsed = urlsplit(url)
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        scope = dict(type="http", asgi={"version": "3.0"}, http_version="1.1",
                     method="GET", scheme="http", path=parsed.path,
                     raw_path=parsed.path.encode(), query_string=parsed.query.encode(),
                     root_path="", headers=[], client=("127.0.0.1", 1234), server=("test", 80))
        asyncio.run(self.app(scope, receive, send))
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return SimpleNamespace(status_code=status, text=body.decode(), json=lambda: json.loads(body))


# Cada consulta contiene sus datos como constantes. No se crea ni modifica tabla alguna.
FIXTURES = """WITH
t_categoria(id_categoria,nombre) AS (VALUES (1,'Camisas'),(2,'Pantalones')),
t_producto(id_producto,nombre,estado,id_categoria) AS
 (VALUES (1,'Camisa Oxford',0,1),(2,'Pantalon',1,2),(3,'Literal %_\\',1,1)),
t_talla(id_talla,nombre) AS (VALUES (1,'M'),(2,'L')),
t_color(id_color,nombre) AS (VALUES (1,'Blanco'),(2,'Azul')),
t_variante_producto(id_variante_producto,id_producto,id_talla,id_color,sku,estado) AS
 (VALUES (1,1,1,1,'OX-M',0),(2,2,2,2,'PA-L',1),(3,1,2,1,'SIN',1),(4,3,1,1,'LIT',1)),
t_ciudad(id_ciudad,nombre) AS (VALUES (1,'Santa Cruz'),(2,'La Paz')),
t_sucursal(id_sucursal,nombre,estado,id_ciudad) AS
 (VALUES (1,'Equipetrol',0,1),(2,'Centro',1,1),(3,'Norte',1,2)),
t_inventario_sucursal(id_inventario_sucursal,id_sucursal,id_variante_producto,
 stock_actual,stock_reservado,stock_minimo) AS
 (VALUES (1,1,1,20,2,5),(2,2,1,10,10,3),(3,3,1,5,7,1),
         (4,1,2,8,1,2),(5,2,4,0,0,4))
"""


class GlobalInventoryQueryTests(TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.db = MagicMock()
        self.statements = []

        def query(statement):
            self.assertTrue(statement.is_select)
            self.statements.append(statement)
            compiled = statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            return [dict(row) for row in self.connection.execute(FIXTURES + str(compiled)).fetchall()]

        def execute(statement):
            rows = query(statement)
            result = MagicMock()
            result.mappings.return_value.all.return_value = rows
            result.mappings.return_value.one_or_none.return_value = rows[0] if rows else None
            return result

        self.db.execute.side_effect = execute
        self.db.scalar.side_effect = lambda statement: next(iter(query(statement)[0].values()))
        self.service = AdminGlobalInventoryService(self.db)

    def test_global_list(self):
        data, pagination = self.service.list_inventory()
        self.assertEqual([item.variante.id_variante_producto for item in data], [1, 2, 4])
        self.assertEqual(pagination.total, 3)

    def test_single_branch(self):
        data = self.service.get_inventory(2)
        self.assertEqual((data.total_stock_actual, data.total_stock_reservado, data.total_stock_disponible), (8, 1, 7))
        self.assertEqual(data.cantidad_sucursales, 1)

    def test_multiple_branches(self):
        self.assertEqual(len(self.service.get_inventory(1).sucursales), 3)

    def test_sum_actual(self):
        self.assertEqual(self.service.list_inventory()[0][0].total_stock_actual, 35)

    def test_sum_reserved(self):
        self.assertEqual(self.service.list_inventory()[0][0].total_stock_reservado, 19)

    def test_sum_available_clamps_each_branch_before_sum(self):
        self.assertEqual(self.service.list_inventory()[0][0].total_stock_disponible, 18)

    def test_availability_never_negative(self):
        self.assertEqual([b.stock_disponible for b in self.service.get_inventory(1).sucursales], [18, 0, 0])

    def test_branch_count(self):
        self.assertEqual(self.service.list_inventory()[0][0].cantidad_sucursales, 3)

    def test_branches_with_stock_count(self):
        self.assertEqual(self.service.list_inventory()[0][0].cantidad_sucursales_con_stock, 1)

    def test_product(self):
        self.assertEqual(self.service.get_inventory(1).producto.model_dump(), dict(id_producto=1, nombre="Camisa Oxford", estado=False))

    def test_sku(self):
        self.assertEqual(self.service.get_inventory(1).variante.sku, "OX-M")

    def test_size(self):
        self.assertEqual(self.service.get_inventory(1).talla.model_dump(), dict(id_talla=1, nombre="M"))

    def test_color(self):
        self.assertEqual(self.service.get_inventory(1).color.model_dump(), dict(id_color=1, nombre="Blanco"))

    def test_category(self):
        self.assertEqual(self.service.get_inventory(1).categoria.model_dump(), dict(id_categoria=1, nombre="Camisas"))

    def test_catalog_filters(self):
        for field in ("id_categoria", "id_producto", "id_talla", "id_color"):
            with self.subTest(field=field):
                data, pagination = self.service.list_inventory(**{field: 2})
                self.assertEqual([item.variante.id_variante_producto for item in data], [2])
                self.assertEqual(pagination.total, 1)

    def test_city_filter_scopes_totals(self):
        data, pagination = self.service.list_inventory(id_ciudad=2)
        self.assertEqual(pagination.total, 1)
        self.assertEqual((data[0].total_stock_actual, data[0].total_stock_reservado, data[0].total_stock_disponible), (5, 7, 0))
        self.assertEqual((data[0].cantidad_sucursales, data[0].cantidad_sucursales_con_stock), (1, 0))

    def test_branch_filter_scopes_totals(self):
        data, pagination = self.service.list_inventory(id_sucursal=1)
        self.assertEqual(pagination.total, 2)
        self.assertEqual((data[0].total_stock_actual, data[0].total_stock_reservado, data[0].total_stock_disponible), (20, 2, 18))
        self.assertEqual((data[0].cantidad_sucursales, data[0].cantidad_sucursales_con_stock), (1, 1))

    def test_combined_filters(self):
        data, pagination = self.service.list_inventory(id_ciudad=2, id_sucursal=1)
        self.assertEqual(data, [])
        self.assertEqual(pagination.total, 0)

    def test_search_product(self):
        self.assertEqual(self.service.list_inventory(search="oxford")[1].total, 1)

    def test_search_sku(self):
        self.assertEqual(self.service.list_inventory(search="ox-m")[1].total, 1)

    def test_search_special_characters(self):
        data, pagination = self.service.list_inventory(search=" %_\\ ")
        self.assertEqual(pagination.total, 1)
        self.assertEqual(data[0].variante.sku, "LIT")

    def test_blank_search(self):
        self.assertEqual(self.service.list_inventory(search="  ")[1].total, 3)

    def test_pagination(self):
        data, pagination = self.service.list_inventory(page=2, page_size=2)
        self.assertEqual([item.variante.id_variante_producto for item in data], [4])
        self.assertEqual(pagination.model_dump(), dict(page=2, page_size=2, total=3, total_pages=2))

    def test_count_variants_not_inventory_rows(self):
        self.assertEqual(self.service.list_inventory(id_producto=1)[1].total, 1)

    def test_detail_matches_global_totals(self):
        for item in self.service.list_inventory()[0]:
            detail = self.service.get_inventory(item.variante.id_variante_producto)
            self.assertEqual(detail.model_dump(exclude={"sucursales"}), item.model_dump())

    def test_branch_breakdown_and_minimum(self):
        branch = self.service.get_inventory(1).sucursales[0]
        self.assertEqual(branch.model_dump(), dict(
            id_sucursal=1, nombre_sucursal="Equipetrol", estado_sucursal=False,
            id_ciudad=1, nombre_ciudad="Santa Cruz", id_inventario_sucursal=1,
            stock_actual=20, stock_reservado=2, stock_disponible=18, stock_minimo=5,
        ))

    def test_variant_without_inventory(self):
        data = self.service.get_inventory(3)
        self.assertEqual(data.sucursales, [])
        for field in ("total_stock_actual", "total_stock_reservado", "total_stock_disponible",
                      "cantidad_sucursales", "cantidad_sucursales_con_stock"):
            self.assertEqual(getattr(data, field), 0)

    def test_missing_variant(self):
        with self.assertRaises(GlobalInventoryNotFoundError):
            self.service.get_inventory(999)
        self.assertEqual(len(self.statements), 1)

    def test_inactive_history(self):
        detail = self.service.get_inventory(1)
        self.assertFalse(detail.producto.estado)
        self.assertFalse(detail.variante.estado)
        self.assertFalse(detail.sucursales[0].estado_sucursal)
        self.assertEqual(detail.total_stock_actual, 35)

    def test_only_select_no_commit_or_stock_mutations(self):
        self.service.list_inventory()
        self.service.get_inventory(1)
        self.assertTrue(all(s.is_select for s in self.statements))
        self.assertEqual({call[0] for call in self.db.method_calls}, {"scalar", "execute"})
        self.db.commit.assert_not_called()

    def test_stable_order(self):
        self.assertEqual([self.service.list_inventory(page=p, page_size=1)[0][0].variante.id_variante_producto
                          for p in (1, 2, 3)], [1, 2, 4])
        self.assertEqual([b.id_sucursal for b in self.service.get_inventory(1).sucursales], [1, 2, 3])


class GlobalInventorySQLTests(TestCase):
    def test_postgres_search_and_shared_filters(self):
        db = MagicMock()
        repo = GlobalInventoryRepository(db)
        repo.list_inventory(search="%_\\", id_categoria=1, id_producto=2, id_talla=3,
                            id_color=4, id_ciudad=5, id_sucursal=6, page=3, page_size=7)
        count = db.scalar.call_args.args[0]
        listing = db.execute.call_args.args[0]
        base = count.get_final_froms()[0].element
        self.assertEqual(str(base), str(listing.limit(None).offset(None).order_by(None)))
        for statement in (count, listing):
            compiled = statement.compile(dialect=postgresql.dialect())
            sql = str(compiled)
            self.assertIn("t_producto.nombre ILIKE", sql)
            self.assertIn("t_variante_producto.sku ILIKE", sql)
            self.assertEqual(list(compiled.params.values()).count("%\\%\\_\\\\%"), 2)
            self.assertIn("ESCAPE", sql)
            self.assertIn("GROUP BY t_inventario_sucursal.id_variante_producto", sql)
            for table in ("t_producto", "t_categoria", "t_talla", "t_color", "t_sucursal", "t_ciudad"):
                self.assertIn("JOIN " + table + " ON", sql)
        self.assertEqual(listing._offset_clause.value, 14)
        self.assertEqual(listing._limit_clause.value, 7)

    def test_service_does_not_modify_input_rows(self):
        db = MagicMock()
        service = AdminGlobalInventoryService(db)
        repo = service.repository = MagicMock()
        variant = dict(id_producto=1, producto="Camisa", producto_estado=False,
                       id_categoria=1, categoria="Camisas", id_variante_producto=1, sku="OX",
                       variante_estado=False, id_talla=1, talla="M", id_color=1, color="Blanco")
        branch = dict(id_sucursal=1, nombre_sucursal="Centro", estado_sucursal=False,
                      id_ciudad=1, nombre_ciudad="La Paz", id_inventario_sucursal=1,
                      stock_actual=1, stock_reservado=3, stock_minimo=2)
        before = deepcopy((variant, branch))
        repo.get_variant.return_value = variant
        repo.list_branches.return_value = [branch]
        service.get_inventory(1)
        self.assertEqual((variant, branch), before)
        self.assertEqual(db.method_calls, [])


class GlobalInventoryRouterTests(TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(routes.router)
        self.db = MagicMock()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.app.dependency_overrides[require_administrator] = lambda: SimpleNamespace()
        self.client = ASGIClient(self.app)

    def test_endpoints_security_and_error_contract(self):
        paths = self.app.openapi()["paths"]
        self.assertEqual(set(paths), {"/api/admin/global-inventory", "/api/admin/global-inventory/{id_variante_producto}"})
        for path in paths.values():
            self.assertEqual(set(path), {"get"})
            self.assertTrue({"401", "403", "404", "422", "500"} <= set(path["get"]["responses"]))
        for route in routes.router.routes:
            self.assertIn(require_administrator, [d.call for d in route.dependant.dependencies])
            self.assertIn(get_db, [d.call for d in route.dependant.dependencies])

    def test_invalid_parameters(self):
        for query in ("page=0", "page_size=0", "page_size=101", "page=x", "search=" + "a" * 201,
                      *[f"{field}=0" for field in ("id_categoria", "id_producto", "id_talla", "id_color", "id_ciudad", "id_sucursal")]):
            with self.subTest(query=query), patch.object(routes, "AdminGlobalInventoryService") as service:
                self.assertEqual(self.client.get("/api/admin/global-inventory?" + query).status_code, 422)
                service.assert_not_called()
        for value in ("0", "-1", "abc"):
            self.assertEqual(self.client.get("/api/admin/global-inventory/" + value).status_code, 422)

    def test_auth_denials(self):
        for status in (401, 403):
            self.app.dependency_overrides[require_administrator] = lambda: routes.JSONResponse(
                status_code=status, content={"success": False})
            with patch.object(routes, "AdminGlobalInventoryService") as service:
                for path in ("", "/1"):
                    self.assertEqual(self.client.get("/api/admin/global-inventory" + path).status_code, status)
                service.assert_not_called()

    def test_actual_missing_auth(self):
        del self.app.dependency_overrides[require_administrator]
        self.assertEqual(self.client.get("/api/admin/global-inventory").status_code, 401)

    def test_list_response_and_filter_forwarding(self):
        with patch.object(routes, "AdminGlobalInventoryService") as service:
            service.return_value.list_inventory.return_value = ([], dict(page=2, page_size=5, total=0, total_pages=0))
            response = self.client.get("/api/admin/global-inventory?page=2&page_size=5&id_ciudad=2&search=OX")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), {"success", "data", "message", "pagination"})
            self.assertEqual(service.return_value.list_inventory.call_args.kwargs["id_ciudad"], 2)
            self.assertEqual(service.return_value.list_inventory.call_args.kwargs["search"], "OX")

    def test_detail_without_inventory_http_200(self):
        self.db.execute.return_value.mappings.return_value.one_or_none.return_value = dict(
            id_producto=1, producto="Camisa", producto_estado=True, id_categoria=1, categoria="Camisas",
            id_variante_producto=3, sku="SIN", variante_estado=True, id_talla=1, talla="M", id_color=1, color="Blanco")
        self.db.execute.return_value.mappings.return_value.all.return_value = []
        response = self.client.get("/api/admin/global-inventory/3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"success", "data", "message"})
        self.assertEqual(response.json()["data"]["sucursales"], [])

    def test_errors_hide_internal_details(self):
        for error, status in ((GlobalInventoryNotFoundError(), 404), (RuntimeError("secret"), 500)):
            with patch.object(routes, "AdminGlobalInventoryService") as service:
                service.return_value.get_inventory.side_effect = error
                response = self.client.get("/api/admin/global-inventory/1")
                self.assertEqual(response.status_code, status)
                self.assertNotIn("secret", response.text)
        with patch.object(routes, "AdminGlobalInventoryService") as service:
            service.return_value.list_inventory.side_effect = RuntimeError("secret")
            response = self.client.get("/api/admin/global-inventory")
            self.assertEqual(response.status_code, 500)
            self.assertNotIn("secret", response.text)
