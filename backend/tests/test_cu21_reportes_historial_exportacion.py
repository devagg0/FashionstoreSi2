"""CU21: Consultar y exportar reportes generados.
Pruebas de backend: persistencia automatica en PostgreSQL/SQLite, consulta de historial con aislamiento tenant,
recuperacion de detalle completo y exportacion a Excel (.xlsx).
"""

import io
import json
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import openpyxl

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.user import User
from app.models.generated_report import GeneratedReport
from app.routers import admin_nl_report as routes
from app.routers.admin_nl_report import DirectExcelExportRequest
from app.schemas.admin_nl_report import NaturalLanguageReportRequest
from app.services.admin_nl_report import NaturalLanguageReportService


class FakeDeepSeek:
    def __init__(self, intent=None):
        self.intent = intent

    def generate_analysis(self, *, prompt, **kwargs):
        if kwargs.get("json_mode"):
            return self.intent if isinstance(self.intent, str) else json.dumps(self.intent)
        return "Resumen ejecutivo con IA para el reporte."


class CU21ReportHistoryExportTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        for model in (
            User, Branch, Category, Product, ProductVariant, BranchInventory,
            Sale, SaleDetail, Reservation, ReservationDetail, GeneratedReport
        ):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

        # Seed data
        self.seed_company(1)
        self.seed_company(2)
        set_tenant_context(self.db, 1)

        self.enterContext(patch(
            "app.PK07.CU07_ConsultarPlanLimites.service.SaasPlanLimitsService.validate_feature_enabled"
        ))

    def seed_company(self, company_id: int):
        db = self.db
        set_tenant_context(db, company_id)
        bid = 1 if company_id == 1 else 2
        db.add(Branch(id_sucursal=bid, id_ciudad=1, nombre=f"Sucursal {company_id}", direccion="Dir", estado=True))
        db.add(Category(id_categoria=company_id, nombre=f"Cat {company_id}", estado=True))
        db.add(Product(id_producto=company_id, id_categoria=company_id, nombre=f"Prod {company_id}", seccion="UNISEX", precio=100, estado=True))
        db.add(ProductVariant(id_variante_producto=company_id, id_producto=company_id, id_talla=1, id_color=1, sku=f"SKU-{company_id}", estado=True))
        db.flush()
        db.add(BranchInventory(id_inventario_sucursal=company_id, id_sucursal=bid, id_variante_producto=company_id, stock_actual=10, stock_reservado=0, stock_minimo=2))
        db.add(Sale(id_venta=company_id, id_sucursal=bid, numero_venta=f"V-{company_id}", canal="DIGITAL", estado="COMPLETADA",
                    fecha_venta=datetime(2026, 10, 5, 14), fecha_completada=datetime(2026, 10, 5, 15),
                    subtotal=100, descuento_total=0, total=100, id_cliente=1))
        db.flush()
        db.add(SaleDetail(id_venta=company_id, id_variante_producto=company_id, cantidad=1, precio_unitario=100, subtotal_linea=100))
        db.commit()

    def test_1_generate_report_auto_saves_and_appears_in_history(self):
        """Generar un reporte guarda automaticamente el registro en t_reporte_generado y aparece en el historial."""
        admin = SimpleNamespace(id_usuario=42, rol="ADMINISTRADOR", id_empresa=1, nombre="Admin Empresa 1")
        fake = FakeDeepSeek({
            "tipo": "VENTAS",
            "fecha_desde": "2026-10-01",
            "fecha_hasta": "2026-10-31",
            "agrupacion": "canal",
            "visualizacion": "bar"
        })

        with patch.object(routes, "NaturalLanguageReportService",
                          side_effect=lambda db: NaturalLanguageReportService(db, client=fake)):
            res = routes.natural_language_report(admin, NaturalLanguageReportRequest(consulta="Ventas por canal del mes"), self.db)

        self.assertEqual(res.data.estado, "OK")
        self.assertIsNotNone(res.id_reporte)

        # Verificar en base de datos
        db_rep = self.db.query(GeneratedReport).filter(GeneratedReport.id_reporte == res.id_reporte).first()
        self.assertIsNotNone(db_rep)
        self.assertEqual(db_rep.empresa_id, 1)
        self.assertEqual(db_rep.id_usuario, 42)
        self.assertEqual(db_rep.tipo, "VENTAS")
        self.assertEqual(db_rep.consulta, "Ventas por canal del mes")

        # Verificar en endpoint de historial
        history_res = routes.list_report_history(admin, limit=50, db=self.db)
        self.assertEqual(history_res.total, 1)
        self.assertEqual(len(history_res.data), 1)
        item = history_res.data[0]
        self.assertEqual(item.id_reporte, res.id_reporte)
        self.assertEqual(item.tipo, "VENTAS")
        self.assertEqual(item.consulta, "Ventas por canal del mes")

    def test_2_view_saved_report_and_tenant_isolation(self):
        """Abrir un reporte guardado conserva datos, filtros, resumen y respeta aislamiento tenant."""
        # Empresa 1 guarda un reporte
        rep_emp1 = GeneratedReport(
            empresa_id=1,
            id_usuario=42,
            tipo="VENTAS",
            titulo="Ventas Canal Online",
            consulta="Reporte online",
            filtros_aplicados={"Canal": "DIGITAL"},
            resultado={
                "estado": "OK",
                "tipo": "VENTAS",
                "titulo": "Ventas Canal Online",
                "kpis": [{"etiqueta": "Total", "valor": "Bs 500"}],
                "tabla": {"columnas": [{"clave": "canal", "etiqueta": "Canal", "tipo": "texto"}], "filas": [{"canal": "DIGITAL"}], "total_filas": 1},
                "grafico": {"tipo": "bar", "titulo": "Ventas", "puntos": [{"etiqueta": "DIGITAL", "valor": 500}]},
                "resumen": "Resumen ventas online.",
                "generado_en": "2026-11-09T01:00:00Z"
            }
        )
        self.db.add(rep_emp1)
        self.db.commit()
        self.db.refresh(rep_emp1)

        admin1 = SimpleNamespace(id_usuario=42, rol="ADMINISTRADOR", id_empresa=1, nombre="Admin 1")
        detail_res = routes.get_saved_report_detail(rep_emp1.id_reporte, admin1, self.db)
        self.assertEqual(detail_res.data.id_reporte, rep_emp1.id_reporte)
        self.assertEqual(detail_res.data.titulo, "Ventas Canal Online")
        self.assertEqual(detail_res.data.resultado.kpis[0].valor, "Bs 500")

        # Admin de Empresa 2 no puede ver reporte de Empresa 1
        admin2 = SimpleNamespace(id_usuario=99, rol="ADMINISTRADOR", id_empresa=2, nombre="Admin 2")
        err_res = routes.get_saved_report_detail(rep_emp1.id_reporte, admin2, self.db)
        self.assertEqual(err_res.status_code, 404)

        # Historial de Empresa 2 debe estar vacio
        history2 = routes.list_report_history(admin2, limit=50, db=self.db)
        self.assertEqual(history2.total, 0)
        self.assertEqual(len(history2.data), 0)

    def test_3_export_excel_generates_valid_xlsx(self):
        """Exportacion a Excel (.xlsx) genera un archivo binario valido con hojas de Resumen y Detalle."""
        rep = GeneratedReport(
            empresa_id=1,
            id_usuario=42,
            tipo="STOCK",
            titulo="Inventario critico por sucursal",
            consulta="Stock bajo o agotado",
            filtros_aplicados={"Sucursal": "Centro"},
            resultado={
                "estado": "OK",
                "tipo": "STOCK",
                "titulo": "Inventario critico por sucursal",
                "kpis": [
                    {"etiqueta": "Criticos", "valor": "5"},
                    {"etiqueta": "Agotados", "valor": "2"}
                ],
                "tabla": {
                    "columnas": [
                        {"clave": "producto", "etiqueta": "Producto", "tipo": "texto"},
                        {"clave": "actual", "etiqueta": "Actual", "tipo": "numero"},
                        {"clave": "precio", "etiqueta": "Precio", "tipo": "moneda"}
                    ],
                    "filas": [
                        {"producto": "Camisa A", "actual": 0, "precio": 120.0},
                        {"producto": "Pantalon B", "actual": 1, "precio": 180.0}
                    ]
                },
                "resumen": "Se detectaron 5 registros criticos."
            }
        )
        self.db.add(rep)
        self.db.commit()
        self.db.refresh(rep)

        admin = SimpleNamespace(id_usuario=42, rol="ADMINISTRADOR", id_empresa=1, nombre="Admin 1")
        resp = routes.export_saved_report_excel(rep.id_reporte, admin, self.db)

        self.assertEqual(resp.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn(".xlsx", resp.headers["Content-Disposition"])

        # Validar workbook con openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(resp.body))
        self.assertIn("Resumen", wb.sheetnames)
        self.assertIn("Detalle", wb.sheetnames)

        sheet_resumen = wb["Resumen"]
        self.assertEqual(sheet_resumen["A1"].value, "FASHIONSTORE · REPORTE EMPRESARIAL")
        self.assertEqual(sheet_resumen["A2"].value, "Inventario critico por sucursal")

        sheet_detalle = wb["Detalle"]
        headers = [sheet_detalle.cell(row=1, column=col).value for col in range(1, 4)]
        self.assertEqual(headers, ["Producto", "Actual", "Precio"])
        self.assertEqual(sheet_detalle.cell(row=2, column=1).value, "Camisa A")
        self.assertEqual(sheet_detalle.cell(row=2, column=2).value, 0)
        self.assertEqual(sheet_detalle.cell(row=2, column=3).value, 120.0)
