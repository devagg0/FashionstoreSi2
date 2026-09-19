"""CU28: datos reales en SQLite aislado, ASGI y compilacion PostgreSQL."""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.models.branch import Branch
from app.models.category import Category
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.routers.admin_sales_report import router
from app.schemas.admin_sales_report import SalesReportFilters
from app.services.admin_sales_report import AdminSalesReportService
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError


ROUTE = "/api/admin/sales-report"


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


class AdminSalesReportTests(TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for model in (Branch, Category, Product, ProductVariant, Sale, SaleDetail, Payment):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        for i in (1, 2, 3):
            self.db.add(Branch(id_sucursal=i, id_ciudad=1, nombre=f"Sucursal {i}", direccion="Av 1"))
            self.db.add(Category(id_categoria=i, nombre=f"Categoria {i}"))
            self.db.add(Product(
                id_producto=i, id_categoria=i, nombre=f"Producto {i}",
                seccion="UNISEX", precio=Decimal("999.99"), estado=False,
            ))
            self.db.add(ProductVariant(
                id_variante_producto=i, id_producto=i, id_talla=1, id_color=1,
                sku=f"SKU-{i}", estado=False,
            ))
        self.db.flush()
        # Dos categorias en una venta; las ventas 1 y 2 tienen igual total.
        self.add_sale(1, "2026-09-18T03:59:59.999999", [(1, 2, "50", "5"), (2, 1, "20", "0")])
        self.add_sale(2, "2026-09-18T04:00:00", [(1, 1, "120", "10")], client=7, channel="DIGITAL", branch=2)
        self.add_sale(3, "2026-09-19T03:59:59.999999", [(2, 3, "10", "0")], client=7)
        self.add_sale(4, "2026-09-19T04:00:00", [(1, 1, "10", "0")], client=8)
        self.add_sale(5, None, [(1, 1, "500", "0")], state="PENDIENTE")
        self.add_sale(6, "2026-09-18T10:00:00", [(1, 1, "800", "0")], state="ANULADA")
        self.db.commit()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.auth = self.enterContext(patch("app.services.admin_user_service.AuthService.get_current_user"))
        self.auth.return_value = SimpleNamespace(id_usuario=1, rol="ADMINISTRADOR")

    def add_sale(self, sid, completed, lines, *, client=None, channel="PRESENCIAL", branch=1, state="COMPLETADA"):
        subtotal = sum((qty * Decimal(price) for _, qty, price, _ in lines), Decimal(0))
        discount = sum((qty * Decimal(discount) for _, qty, _, discount in lines), Decimal(0))
        self.db.add(Sale(
            id_venta=sid, id_sucursal=branch, id_empleado=1 if channel == "PRESENCIAL" else None,
            id_cliente=client, numero_venta=f"V-{sid}", canal=channel, estado=state,
            fecha_venta=datetime(2026, 9, 1),
            fecha_completada=datetime.fromisoformat(completed) if completed else None,
            subtotal=subtotal, descuento_total=discount, total=subtotal - discount,
        ))
        self.db.flush()
        for variant, qty, price, discount in lines:
            self.db.add(SaleDetail(
                id_venta=sid, id_variante_producto=variant, cantidad=qty,
                precio_unitario=Decimal(price), descuento_unitario=Decimal(discount),
                subtotal_linea=qty * (Decimal(price) - Decimal(discount)),
            ))
        self.db.flush()

    def report(self, query=""):
        status, body = request(self.app, query)
        self.assertEqual(status, 200, body)
        self.assertTrue(body["success"])
        return body["data"]

    def test_unfiltered_multiple_lines_equal_totals_and_distinct_clients(self):
        data = self.report()
        self.assertEqual(data["moneda"], "BOB")
        self.assertEqual(data["zona_horaria"], "America/La_Paz")
        self.assertEqual(data["kpis"], {
            "cantidad_ventas": 4, "importe_antes_descuentos": "280.00",
            "descuentos": "20.00", "importe_vendido": "260.00",
            "ticket_promedio": "65.00", "unidades_vendidas": 8,
            "clientes_identificados": 2, "ventas_sin_cliente": 1,
        })
        self.assertEqual([(r["canal"], r["importe_vendido"]) for r in data["por_canal"]],
                         [("DIGITAL", "110.00"), ("PRESENCIAL", "150.00")])
        self.assertEqual([(r["id_sucursal"], r["importe_vendido"]) for r in data["por_sucursal"]],
                         [(1, "150.00"), (2, "110.00")])

    def test_date_range_inclusive_local_days_uses_completion_not_creation(self):
        data = self.report("fecha_desde=2026-09-18&fecha_hasta=2026-09-18")
        self.assertEqual(data["kpis"]["cantidad_ventas"], 2)
        self.assertEqual(data["kpis"]["importe_vendido"], "140.00")
        self.assertEqual(data["kpis"]["clientes_identificados"], 1)
        self.assertEqual([row["fecha"] for row in data["serie_diaria"]], ["2026-09-18"])

    def test_open_date_bounds(self):
        self.assertEqual(self.report("fecha_desde=2026-09-18")["kpis"]["cantidad_ventas"], 3)
        self.assertEqual(self.report("fecha_hasta=2026-09-18")["kpis"]["cantidad_ventas"], 3)

    def test_daily_series_local_dates_and_order(self):
        rows = self.report()["serie_diaria"]
        self.assertEqual([(r["fecha"], r["importe_vendido"]) for r in rows],
                         [("2026-09-17", "110.00"), ("2026-09-18", "140.00"), ("2026-09-19", "10.00")])

    def test_branch(self):
        data = self.report("id_sucursal=2")
        self.assertEqual(data["kpis"]["importe_vendido"], "110.00")
        self.assertEqual(len(data["por_sucursal"]), 1)

    def test_channel(self):
        data = self.report("canal=PRESENCIAL")
        self.assertEqual(data["kpis"]["cantidad_ventas"], 3)
        self.assertEqual(data["kpis"]["importe_vendido"], "150.00")

    def test_category_mixed_sales_only_matching_lines(self):
        data = self.report("id_categoria=1")
        self.assertEqual(data["kpis"], {
            "cantidad_ventas": 3, "importe_antes_descuentos": "230.00",
            "descuentos": "20.00", "importe_vendido": "210.00",
            "ticket_promedio": "70.00", "unidades_vendidas": 4,
            "clientes_identificados": 2, "ventas_sin_cliente": 1,
        })
        self.assertEqual([r["id_producto"] for r in data["productos_mas_vendidos"]], [1])
        for key in ("por_canal", "por_sucursal", "serie_diaria", "productos_mas_vendidos"):
            self.assertEqual(sum(Decimal(r["importe_vendido"]) for r in data[key]), Decimal("210"))

    def test_combined_filters(self):
        data = self.report("id_categoria=2&id_sucursal=1&canal=PRESENCIAL&fecha_desde=2026-09-18&fecha_hasta=2026-09-18")
        self.assertEqual(data["kpis"]["cantidad_ventas"], 1)
        self.assertEqual(data["kpis"]["importe_vendido"], "30.00")

    def test_multiple_variants_same_product_are_grouped(self):
        self.db.add(ProductVariant(id_variante_producto=4, id_producto=1, id_talla=2, id_color=1, sku="SKU-4"))
        self.db.flush()
        self.add_sale(7, "2026-09-18T12:00:00", [(1, 1, "1", "0"), (4, 2, "2", "0")])
        self.db.commit()
        data = self.report()
        self.assertEqual(len(data["productos_mas_vendidos"]), 2)
        self.assertEqual(data["productos_mas_vendidos"][0]["unidades_vendidas"], 7)
        self.assertEqual(data["kpis"]["cantidad_ventas"], 5)

    def test_historical_values_ignore_current_catalog_prices_and_state(self):
        before = self.report()
        product = self.db.get(Product, 1)
        product.precio = Decimal("0.01")
        product.estado = True
        self.db.commit()
        self.assertEqual(self.report(), before)
        self.assertEqual(before["productos_mas_vendidos"][0]["importe_vendido"], "210.00")

    def test_no_category_uses_sale_header_category_uses_line_history(self):
        sale = self.db.get(Sale, 1)
        sale.subtotal = Decimal("130")
        sale.descuento_total = Decimal("30")
        sale.total = Decimal("100")
        self.db.commit()
        self.assertEqual(self.report()["kpis"]["importe_vendido"], "250.00")
        self.assertEqual(self.report("id_categoria=1")["kpis"]["importe_vendido"], "210.00")

    def test_multiple_payment_attempts_and_refunded_payment_do_not_change_report(self):
        before = self.report()
        for state in ("RECHAZADO", "CANCELADO", "EXPIRADO", "REEMBOLSADO"):
            self.db.add(Payment(
                id_venta=1, medio="EFECTIVO", proveedor="MANUAL", entorno="LOCAL",
                estado=state, monto=Decimal("110"), moneda="BOB", clave_idempotencia=uuid4(),
                fecha_aprobacion=datetime(2026, 9, 18) if state == "REEMBOLSADO" else None,
            ))
        self.db.commit()
        self.assertEqual(self.report(), before)

    def test_completed_sale_without_payment_is_included(self):
        self.assertEqual(self.db.query(Payment).count(), 0)
        self.assertEqual(self.report()["kpis"]["cantidad_ventas"], 4)

    def test_empty_results(self):
        for query in ("fecha_desde=2027-01-01", "id_categoria=3", "id_sucursal=3"):
            with self.subTest(query=query):
                data = self.report(query)
                self.assertEqual(data["kpis"], {
                    "cantidad_ventas": 0, "importe_antes_descuentos": "0.00",
                    "descuentos": "0.00", "importe_vendido": "0.00", "ticket_promedio": None,
                    "unidades_vendidas": 0, "clientes_identificados": 0, "ventas_sin_cliente": 0,
                })
                for key in ("por_canal", "por_sucursal", "productos_mas_vendidos", "serie_diaria"):
                    self.assertEqual(data[key], [])

    def test_invalid_filters(self):
        for query in (
            "fecha_desde=2026-09-19&fecha_hasta=2026-09-18", "fecha_desde=2026-02-30",
            "fecha_desde=2026-9-1", "fecha_desde=0", "fecha_hasta=2026-09-18T00:00:00",
            "fecha_hasta=9999-12-31", "id_sucursal=0", "id_sucursal=-1", "id_sucursal=999",
            "id_categoria=0", "id_categoria=-1", "id_categoria=999", "id_categoria=abc",
            "id_sucursal=1.5", "canal=OTRO", "canal=digital",
        ):
            with self.subTest(query=query):
                status, body = request(self.app, query)
                self.assertEqual(status, 422, body)

    def test_security_missing_invalid_token_inactive_and_non_admin_roles(self):
        with patch("app.routers.admin_sales_report.AdminSalesReportService") as report_service:
            self.assertEqual(request(self.app, token=False)[0], 401)
            for error, expected in ((InvalidAccessTokenError, 401), (InactiveAccountError, 403)):
                self.auth.side_effect = error
                self.assertEqual(request(self.app)[0], expected)
            self.auth.side_effect = None
            for role in ("CLIENTE", "CAJERO", "ENCARGADO_SUCURSAL", "PROVEEDOR"):
                self.auth.return_value = SimpleNamespace(id_usuario=1, rol=role)
                self.assertEqual(request(self.app)[0], 403)
            report_service.assert_not_called()

    def test_query_count_stable_as_sales_grow(self):
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            self.report()
            self.assertEqual(len(statements), 5)
            for sid in range(10, 60):
                self.add_sale(sid, "2026-09-18T12:00:00", [(1, 1, "10", "0"), (2, 2, "5", "1")])
            self.db.commit()
            statements.clear()
            self.assertEqual(self.report()["kpis"]["cantidad_ventas"], 54)
            self.assertEqual(len(statements), 5)
            statements.clear()
            self.report("id_categoria=1&id_sucursal=1")
            self.assertEqual(len(statements), 7)
            self.assertTrue(all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in statements))
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)

    def test_postgresql_queries_compile_and_convert_utc_to_la_paz(self):
        statements = []

        def capture(statement):
            statements.append(statement)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: {}, all=lambda: []))

        service = AdminSalesReportService(self.db)
        with patch.object(self.db, "get_bind", return_value=SimpleNamespace(dialect=postgresql.dialect())):
            with patch.object(self.db, "execute", side_effect=capture):
                service.repository.report(SalesReportFilters(), None, None)
                service.repository.report(SalesReportFilters(id_categoria=1), None, None)
        self.assertEqual(len(statements), 10)
        sql = str(statements[-1].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        self.assertIn("timezone('America/La_Paz', timezone('UTC'", sql)
        self.assertIn("detalles_por_venta", sql)
        for statement in statements:
            sql = str(statement.compile(dialect=postgresql.dialect()))
            self.assertNotIn("t_pago", sql)
            self.assertNotIn("t_producto.precio", sql)

    def test_fractional_money_and_average_round_half_up(self):
        self.add_sale(7, "2026-09-18T12:00:00", [(3, 1, "0.01", "0")], branch=3)
        self.add_sale(8, "2026-09-18T12:00:00", [(3, 1, "0.02", "0")], branch=3)
        self.db.commit()
        kpis = self.report("id_sucursal=3")["kpis"]
        self.assertEqual(kpis["importe_vendido"], "0.03")
        self.assertEqual(kpis["ticket_promedio"], "0.02")

    def test_persistence_error_is_sanitized(self):
        with patch("app.routers.admin_sales_report.AdminSalesReportService.report", side_effect=SQLAlchemyError("private")):
            status, body = request(self.app)
        self.assertEqual(status, 500)
        self.assertNotIn("private", json.dumps(body))

    def test_router_is_registered(self):
        from app.main import app
        self.assertIn(ROUTE, app.openapi()["paths"])
