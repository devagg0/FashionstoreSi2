"""CU29: ASGI, SQL real aislado, autorizacion y ausencia de escrituras/N+1."""

import asyncio
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.color import Color
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.size import Size
from app.routers.admin_inventory_report import router
from app.schemas.admin_inventory_report import InventoryReportFilters
from app.services.admin_inventory_report import AdminInventoryReportService
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError


ROUTE = "/api/admin/inventory-report"


def request(app, query="", token=True):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": ROUTE,
        "raw_path": ROUTE.encode(), "query_string": query.encode(),
        "root_path": "", "server": ("test", 80), "client": ("test", 1),
        "headers": [(b"authorization", b"Bearer fake")] if token else [],
    }
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(body)


class AdminInventoryReportTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        self.models = (Branch, Category, Size, Color, Product, ProductVariant, BranchInventory)
        for model in self.models:
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add(Size(id_talla=1, nombre="M"))
        self.db.add(Color(id_color=1, nombre="Azul"))
        for i in (1, 2, 3):
            self.db.add(Branch(id_sucursal=i, id_ciudad=1, nombre=f"Sucursal {i}", direccion="Av 1", estado=i != 2))
            self.db.add(Category(id_categoria=i, nombre=f"Categoria {i}", estado=i != 2))
            self.db.add(Product(id_producto=i, id_categoria=i, nombre=f"Producto {i}",
                                seccion="UNISEX", precio=10, estado=i != 2))
        for vid, pid in ((1, 1), (2, 1), (3, 2), (4, 3)):
            # Tallas distintas para respetar la unicidad de variantes del producto 1.
            if vid > 1:
                self.db.add(Size(id_talla=vid, nombre=f"Talla {vid}"))
            self.db.add(ProductVariant(id_variante_producto=vid, id_producto=pid,
                                      id_talla=vid, id_color=1, sku=f"SKU-{vid}", estado=vid != 3))
        self.db.flush()
        for iid, branch, variant, actual, reserved, minimum in (
            (1, 1, 1, 0, 0, 5),       # agotado fisico
            (2, 1, 2, 8, 5, 5),       # bajo stock: 3
            (3, 2, 1, 10, 10, 0),     # agotado por reservas
            (4, 2, 3, 5, 0, 5),       # igual al minimo: normal, inactivo
            (5, 1, 3, 2, 0, 0),       # normal sin umbral
        ):
            self.db.add(BranchInventory(id_inventario_sucursal=iid, id_sucursal=branch,
                                       id_variante_producto=variant, stock_actual=actual,
                                       stock_reservado=reserved, stock_minimo=minimum))
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.auth = self.enterContext(patch("app.services.admin_user_service.AuthService.get_current_user"))
        self.auth.return_value = SimpleNamespace(id_usuario=1, rol="ADMINISTRADOR")

    def report(self, query=""):
        status, body = request(self.app, query)
        self.assertEqual(status, 200, body)
        self.assertTrue(body["success"])
        return body["data"]

    def test_complete_report(self):
        data = self.report()
        self.assertEqual(data["kpis"], {
            "total_productos": 2, "total_variantes": 3, "total_registros_inventario": 5,
            "unidades_actuales": 25, "unidades_reservadas": 15, "unidades_disponibles": 10,
            "registros_agotados": 2, "registros_bajo_stock": 1,
            "productos_con_agotados": 1, "productos_con_bajo_stock": 1,
            "registros_con_stock_minimo_cero": 2,
        })
        self.assertEqual(data["advertencias"], [])
        self.assertEqual(data["detalle"]["pagination"], {"page": 1, "page_size": 20, "total": 5, "total_pages": 1})
        for key in ("por_sucursal", "por_categoria"):
            for metric in ("unidades_actuales", "unidades_reservadas", "unidades_disponibles", "total_registros_inventario"):
                self.assertEqual(sum(row[metric] for row in data[key]), data["kpis"][metric])
        item = data["detalle"]["items"][1]
        self.assertEqual(item["variante"]["sku"], "SKU-2")
        self.assertEqual(item["variante"]["color"], "Azul")
        self.assertEqual(item["faltante_hasta_minimo"], 2)

    def test_branch_filter(self):
        data = self.report("id_sucursal=2")
        self.assertEqual(data["kpis"]["unidades_actuales"], 15)
        self.assertEqual(data["kpis"]["unidades_disponibles"], 5)
        self.assertEqual([r["id_sucursal"] for r in data["por_sucursal"]], [2])

    def test_category_filter(self):
        data = self.report("id_categoria=1")
        self.assertEqual(data["kpis"]["total_registros_inventario"], 3)
        self.assertEqual(data["kpis"]["total_variantes"], 2)
        self.assertEqual([r["id_categoria"] for r in data["por_categoria"]], [1])

    def test_product_filter_and_mixed_variant_states(self):
        data = self.report("id_producto=1")
        self.assertEqual(data["kpis"]["total_productos"], 1)
        self.assertEqual(data["kpis"]["productos_con_agotados"], 1)
        self.assertEqual(data["kpis"]["productos_con_bajo_stock"], 1)
        self.assertEqual(data["kpis"]["unidades_disponibles"], 3)

    def test_stock_state_filters_apply_to_all_blocks(self):
        for state, ids, available in (("AGOTADO", [1, 3], 0), ("BAJO_STOCK", [2], 3), ("NORMAL", [4, 5], 7)):
            with self.subTest(state=state):
                data = self.report(f"estado_stock={state}")
                self.assertEqual([r["id_inventario_sucursal"] for r in data["detalle"]["items"]], ids)
                self.assertEqual(data["kpis"]["total_registros_inventario"], len(ids))
                self.assertEqual(data["kpis"]["unidades_disponibles"], available)
                for key in ("por_sucursal", "por_categoria"):
                    self.assertEqual(sum(r["unidades_disponibles"] for r in data[key]), available)

    def test_equal_minimum_is_normal(self):
        item = self.report()["detalle"]["items"][3]
        self.assertEqual(item["stock_disponible"], item["stock_minimo"])
        self.assertEqual(item["estado_stock"], "NORMAL")
        self.assertEqual(item["faltante_hasta_minimo"], 0)

    def test_zero_minimum_and_fully_reserved(self):
        rows = self.report()["detalle"]["items"]
        self.assertEqual((rows[2]["stock_actual"], rows[2]["stock_reservado"]), (10, 10))
        self.assertEqual(rows[2]["estado_stock"], "AGOTADO")
        self.assertEqual(rows[4]["estado_stock"], "NORMAL")
        self.assertEqual(self.report("estado_stock=AGOTADO")["kpis"]["registros_con_stock_minimo_cero"], 1)

    def test_inactive_inventory_is_included(self):
        data = self.report()
        item = data["detalle"]["items"][3]
        for key in ("sucursal", "categoria", "producto", "variante"):
            self.assertFalse(item[key]["estado"])
        self.assertFalse(data["por_sucursal"][1]["estado"])
        self.assertFalse(data["por_categoria"][1]["estado"])

    def test_pagination_does_not_change_kpis_or_breakdowns(self):
        full = self.report()
        seen = []
        for page in (1, 2, 3, 4):
            data = self.report(f"page={page}&page_size=2")
            for key in ("kpis", "por_sucursal", "por_categoria", "advertencias"):
                self.assertEqual(data[key], full[key])
            seen.extend(row["id_inventario_sucursal"] for row in data["detalle"]["items"])
            self.assertEqual(data["detalle"]["pagination"]["total_pages"], 3)
        self.assertEqual(seen, [1, 2, 3, 4, 5])

    def test_empty_valid_combinations_and_no_cartesian_inventory(self):
        for query in ("id_sucursal=3", "id_producto=3", "id_categoria=3", "id_producto=1&id_categoria=2"):
            with self.subTest(query=query):
                data = self.report(query)
                self.assertTrue(all(value == 0 for value in data["kpis"].values()))
                self.assertEqual(data["por_sucursal"], [])
                self.assertEqual(data["por_categoria"], [])
                self.assertEqual(data["detalle"]["items"], [])
                self.assertEqual(data["detalle"]["pagination"]["total_pages"], 0)

    def test_invalid_filters(self):
        queries = [f"{key}={value}" for key in ("id_sucursal", "id_categoria", "id_producto")
                   for value in ("0", "-1", "999", "abc", "1.5")]
        queries += ["estado_stock=OTRO", "estado_stock=normal", "page=0", "page=-1", "page=abc",
                    "page_size=0", "page_size=-1", "page_size=101", "page_size=1.5"]
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(request(self.app, query)[0], 422)
        self.assertEqual(request(self.app, "page_size=100")[0], 200)

    def test_security(self):
        with patch("app.routers.admin_inventory_report.AdminInventoryReportService") as service:
            self.assertEqual(request(self.app, token=False)[0], 401)
            for error, expected in ((InvalidAccessTokenError, 401), (InactiveAccountError, 403)):
                self.auth.side_effect = error
                self.assertEqual(request(self.app)[0], expected)
            self.auth.side_effect = None
            for role in ("CLIENTE", "CAJERO", "ENCARGADO_SUCURSAL", "PROVEEDOR"):
                self.auth.return_value = SimpleNamespace(id_usuario=1, rol=role)
                self.assertEqual(request(self.app)[0], 403)
            service.assert_not_called()

    def test_negative_available_is_preserved_and_warned_even_off_page_or_filtered(self):
        # Simular datos heredados corruptos SOLO en SQLite aislado de pruebas.
        with self.engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA ignore_check_constraints = ON")
            conn.exec_driver_sql("UPDATE t_inventario_sucursal SET stock_reservado = 7 WHERE id_inventario_sucursal = 5")
            conn.exec_driver_sql("PRAGMA ignore_check_constraints = OFF")
        data = self.report()
        item = data["detalle"]["items"][-1]
        self.assertEqual(item["stock_disponible"], -5)
        self.assertIsNone(item["estado_stock"])
        self.assertEqual(data["kpis"]["unidades_disponibles"], 3)
        for query in ("", "page_size=1", "estado_stock=NORMAL"):
            warning = self.report(query)["advertencias"][0]
            self.assertEqual(warning["registros"], 1)
            self.assertEqual(warning["alcance"], "FILTROS_SIN_ESTADO_STOCK")
        self.assertEqual(self.report("id_producto=1")["advertencias"], [])

    def test_query_count_bounded_as_products_grow_and_postgres_compilation(self):
        statements = []

        def capture(conn, clause, multiparams, params, execution_options):
            statements.append(clause)

        event.listen(self.engine, "before_execute", capture)
        try:
            self.report()
            self.assertEqual(len(statements), 5)
            for i in range(10, 60):
                self.db.add(Product(id_producto=i, id_categoria=1, nombre=f"P{i}", seccion="UNISEX", precio=1))
                self.db.add(ProductVariant(id_variante_producto=i, id_producto=i, id_talla=1, id_color=1, sku=f"S{i}"))
                self.db.add(BranchInventory(id_sucursal=1, id_variante_producto=i, stock_actual=1))
            self.db.commit()
            statements.clear()
            self.assertEqual(self.report()["kpis"]["total_productos"], 52)
            self.assertEqual(len(statements), 5)
            statements.clear()
            self.report("id_sucursal=1&id_categoria=1&id_producto=1&estado_stock=AGOTADO")
            self.assertEqual(len(statements), 8)
            for statement in statements:
                self.assertTrue(statement.is_select)
                sql = str(statement.compile(dialect=postgresql.dialect()))
                for forbidden in ("t_movimiento", "t_reserva", "t_venta"):
                    self.assertNotIn(forbidden, sql)
        finally:
            event.remove(self.engine, "before_execute", capture)

    def test_read_only_no_flush_commit_or_dml_and_all_tables_unchanged(self):
        def snapshot():
            return [self.db.execute(select(model.__table__)).all() for model in self.models]

        before = snapshot()
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            with patch.object(self.db, "commit", side_effect=AssertionError("commit forbidden")), \
                 patch.object(self.db, "flush", side_effect=AssertionError("flush forbidden")):
                self.report()
                self.report("id_sucursal=1&estado_stock=AGOTADO")
            self.assertTrue(all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in statements))
            self.assertEqual(snapshot(), before)
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)

    def test_service_suppresses_autoflush_for_dirty_session(self):
        self.db.autoflush = True
        inventory = self.db.get(BranchInventory, 1)
        inventory.stock_actual = 99
        with patch.object(self.db, "flush", side_effect=AssertionError("flush forbidden")):
            data = AdminInventoryReportService(self.db).report(InventoryReportFilters())
        self.assertEqual(data.kpis.unidades_actuales, 25)
        self.db.rollback()

    def test_database_errors_are_sanitized(self):
        with patch("app.routers.admin_inventory_report.AdminInventoryReportService.report",
                   side_effect=SQLAlchemyError("private details")):
            status, body = request(self.app)
        self.assertEqual(status, 500)
        self.assertNotIn("private", json.dumps(body))

    def test_router_registered(self):
        from app.main import app
        self.assertIn(ROUTE, app.openapi()["paths"])
