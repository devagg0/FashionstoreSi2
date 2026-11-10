"""CU20: reportes en lenguaje natural con DeepSeek simulado y SQLite aislado (3 pruebas)."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.integrations.deepseek import DeepSeekError
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.generated_report import GeneratedReport
from app.routers import admin_nl_report as routes
from app.schemas.admin_nl_report import NaturalLanguageReportRequest
from app.services.admin_nl_report import NaturalLanguageReportService


class FakeDeepSeek:
    """Primera llamada (json_mode) = interpretacion; las demas = resumen."""

    def __init__(self, intent=None, error=False):
        self.intent, self.error, self.calls = intent, error, []

    def generate_analysis(self, *, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        if self.error:
            raise DeepSeekError("simulado")
        if kwargs.get("json_mode"):
            return self.intent if isinstance(self.intent, str) else json.dumps(self.intent)
        return "Resumen generado a partir de las cifras."


class NaturalLanguageReportTests(TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        for model in (Branch, Category, Product, ProductVariant, BranchInventory,
                      Sale, SaleDetail, Reservation, ReservationDetail, GeneratedReport):
            model.__table__.create(engine)
        self.db = Session(engine, autoflush=False)
        self.addCleanup(engine.dispose)
        self.addCleanup(self.db.close)
        self.seed(company=1, branch=(1, 2), names=("Sucursal Centro", "Sucursal Norte"))
        self.seed(company=2, branch=(11,), names=("Sucursal Centro",))
        set_tenant_context(self.db, 1)
        self.enterContext(patch(
            "app.PK07.CU07_ConsultarPlanLimites.service.SaasPlanLimitsService.validate_feature_enabled"))

    def seed(self, company, branch, names):
        db = self.db
        set_tenant_context(db, company)
        base = 0 if company == 1 else 10
        for bid, name in zip(branch, names):
            db.add(Branch(id_sucursal=bid, id_ciudad=1, nombre=name, direccion="Av 1", estado=True))
        db.add(Category(id_categoria=base + 1, nombre="Camisas", estado=True))
        db.add(Product(id_producto=base + 1, id_categoria=base + 1, nombre="Camisa A" if company == 1 else "Camisa EMP2",
                       seccion="UNISEX", precio=100, estado=True))
        variants = [base + 1]
        if company == 1:
            db.add(Category(id_categoria=2, nombre="Vestidos", estado=True))
            db.add(Product(id_producto=2, id_categoria=2, nombre="Vestido B", seccion="MUJER", precio=100, estado=True))
            variants.append(2)
        for vid in variants:
            db.add(ProductVariant(id_variante_producto=vid, id_producto=vid, id_talla=vid, id_color=1,
                                  sku=f"SKU-{vid}", estado=True))
        db.flush()
        if company == 1:
            stock = ((1, 1, 1, 0, 0, 5), (2, 1, 2, 8, 5, 5), (3, 2, 1, 10, 10, 0), (4, 2, 2, 50, 0, 5))
            for iid, bid, vid, actual, reserved, minimum in stock:
                db.add(BranchInventory(id_inventario_sucursal=iid, id_sucursal=bid, id_variante_producto=vid,
                                       stock_actual=actual, stock_reservado=reserved, stock_minimo=minimum))
            sales = (
                (1, 1, "DIGITAL", datetime(2026, 10, 5, 15), 1, 2, 90, 180),
                (2, 2, "PRESENCIAL", datetime(2026, 10, 10, 15), 2, 1, 100, 100),
                (3, 1, "DIGITAL", datetime(2026, 9, 1, 15), 1, 5, 100, 500),  # fuera del periodo
            )
        else:
            db.add(BranchInventory(id_inventario_sucursal=11, id_sucursal=11, id_variante_producto=11,
                                   stock_actual=0, stock_reservado=0, stock_minimo=5))
            sales = ((9, 11, "DIGITAL", datetime(2026, 10, 6, 15), 11, 99, 100, 9900),)
        for sid, bid, canal, when, vid, qty, price, total in sales:
            db.add(Sale(id_venta=sid, id_sucursal=bid, numero_venta=f"V-{sid}", canal=canal, estado="COMPLETADA",
                        fecha_venta=when.replace(hour=14), fecha_completada=when, subtotal=total, descuento_total=0, total=total,
                        id_cliente=1 if canal == "DIGITAL" else None,
                        id_empleado=1 if canal == "PRESENCIAL" else None))
            db.flush()
            db.add(SaleDetail(id_venta=sid, id_variante_producto=vid, cantidad=qty, precio_unitario=price,
                              subtotal_linea=total))
        db.commit()

    def run_report(self, intent, consulta="consulta de prueba", company=1, error=False):
        fake = FakeDeepSeek(intent, error=error)
        admin = SimpleNamespace(id_usuario=1, rol="ADMINISTRADOR", id_empresa=company)
        set_tenant_context(self.db, company)
        with patch.object(routes, "NaturalLanguageReportService",
                          side_effect=lambda db: NaturalLanguageReportService(db, client=fake)):
            response = routes.natural_language_report(admin, NaturalLanguageReportRequest(consulta=consulta), self.db)
        return response, fake

    # 1. Ventas con filtros y datos reales
    def test_sales_report_filters_real_data(self):
        response, fake = self.run_report({
            "tipo": "VENTAS", "fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-31",
            "agrupacion": "canal", "visualizacion": "bar"})
        data = response.data
        self.assertEqual(data.estado, "OK")
        kpis = {k.etiqueta: k.valor for k in data.kpis}
        self.assertEqual(kpis["Ventas"], "2")
        self.assertEqual(kpis["Importe vendido"], "Bs 280.00")
        self.assertEqual(kpis["Unidades vendidas"], "3")
        rows = {r["grupo"]: r for r in data.tabla.filas}
        self.assertEqual(rows["DIGITAL"]["importe"], 180.0)
        self.assertEqual(rows["PRESENCIAL"]["cantidad"], 1)
        self.assertEqual(data.grafico.tipo, "bar")
        self.assertEqual(sum(p.valor for p in data.grafico.puntos), 280.0)
        self.assertTrue(data.resumen)
        self.assertEqual(len(fake.calls), 2)

        filtered, _ = self.run_report({
            "tipo": "VENTAS", "fecha_desde": "2026-10-01", "fecha_hasta": "2026-10-31",
            "sucursal": "norte", "agrupacion": "sucursal", "categoria": "vestidos"})
        self.assertEqual([r["grupo"] for r in filtered.data.tabla.filas], ["Sucursal Norte"])
        self.assertEqual(filtered.data.tabla.filas[0]["importe"], 100.0)

    # 2. Inventario con filtros distintos y aislamiento por tenant
    def test_stock_report_filters_and_tenant_isolation(self):
        by_branch, _ = self.run_report({"tipo": "STOCK", "sucursal": "centro", "estado": "ALERTA"})
        rows = by_branch.data.tabla.filas
        self.assertEqual({r["producto"] for r in rows}, {"Camisa A", "Vestido B"})
        self.assertEqual({r["estado"] for r in rows}, {"AGOTADO", "BAJO"})
        self.assertNotIn("Camisa EMP2", {r["producto"] for r in rows})

        depleted, _ = self.run_report({"tipo": "STOCK", "categoria": "camisas", "estado": "AGOTADO"})
        self.assertEqual({(r["producto"], r["sucursal"]) for r in depleted.data.tabla.filas},
                         {("Camisa A", "Sucursal Centro"), ("Camisa A", "Sucursal Norte")})

        other_company, _ = self.run_report({"tipo": "STOCK", "categoria": "camisas", "estado": "AGOTADO"}, company=2)
        self.assertEqual([r["producto"] for r in other_company.data.tabla.filas], ["Camisa EMP2"])

        missing, _ = self.run_report({"tipo": "STOCK", "sucursal": "inexistente"})
        self.assertEqual(missing.data.estado, "VACIO")
        self.assertIsNone(missing.data.tabla)

    # 3. Solicitud ambigua / no soportada / error de IA: respuesta controlada
    def test_ambiguous_unsupported_and_ai_error_are_controlled(self):
        unsupported, fake = self.run_report({"tipo": "NO_SOPORTADO"})
        self.assertEqual(unsupported.data.estado, "NO_SOPORTADO")
        self.assertIn("no está soportada", unsupported.data.mensaje)
        self.assertEqual((unsupported.data.kpis, unsupported.data.tabla, unsupported.data.grafico), ([], None, None))
        self.assertEqual(len(fake.calls), 1)

        ambiguous, _ = self.run_report({"tipo": "AMBIGUO", "aclaracion": "Indica qué reporte necesitas."})
        self.assertEqual(ambiguous.data.estado, "AMBIGUO")
        self.assertEqual(ambiguous.data.mensaje, "Indica qué reporte necesitas.")

        garbage, _ = self.run_report("esto no es json")
        self.assertEqual(garbage.data.estado, "AMBIGUO")

        failed, _ = self.run_report({}, error=True)
        self.assertIsInstance(failed, JSONResponse)
        self.assertEqual(failed.status_code, 502)
