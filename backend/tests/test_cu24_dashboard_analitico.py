"""CU24: Consultar dashboard analítico inteligente.
Batería de 3 pruebas focalizadas:
1. Cálculo consolidado de KPIs reales, filtros por período, sucursal y categoría, y series de tendencia.
2. Integración de resultados de Machine Learning (CU22 predicción, CU23 segmentación K-Means) y reportes IA (CU20/CU21).
3. Seguridad y aislamiento multitenant estricto (prevención de cruce entre empresas) y resiliencia ante datos vacíos.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase
import uuid

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.generated_report import GeneratedReport
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.reservation import Reservation
from app.models.returns import Return
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.schemas.admin_dashboard import DashboardAnalyticsRequest
from app.services.admin_dashboard import AdminDashboardService


class CU24AdminDashboardTests(TestCase):
    """Pruebas unitarias para el servicio del Dashboard Analítico Inteligente (CU24)."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        for model in (
            Branch,
            Category,
            Product,
            ProductVariant,
            BranchInventory,
            Sale,
            SaleDetail,
            Reservation,
            Return,
            GeneratedReport,
        ):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def _seed_company_data(self, empresa_id: int):
        set_tenant_context(self.db, empresa_id)

        # 1. Sucursales
        b1 = Branch(
            empresa_id=empresa_id,
            id_ciudad=1,
            nombre=f"Sucursal Centro E{empresa_id}",
            direccion="Av. Principal 123",
            estado=True,
        )
        b2 = Branch(
            empresa_id=empresa_id,
            id_ciudad=1,
            nombre=f"Sucursal Norte E{empresa_id}",
            direccion="Calle Norte 456",
            estado=True,
        )
        # 2. Categorías
        cat_moda = Category(empresa_id=empresa_id, nombre=f"Moda E{empresa_id}", estado=True)
        cat_calzado = Category(empresa_id=empresa_id, nombre=f"Calzado E{empresa_id}", estado=True)

        self.db.add_all([b1, b2, cat_moda, cat_calzado])
        self.db.commit()

        # 3. Productos y Variantes
        p1 = Product(
            empresa_id=empresa_id,
            id_categoria=cat_moda.id_categoria,
            nombre=f"Vestido Elegante E{empresa_id}",
            descripcion="Vestido de noche",
            precio=Decimal("150.00"),
            seccion="MUJER",
            estado=True,
        )
        p2 = Product(
            empresa_id=empresa_id,
            id_categoria=cat_calzado.id_categoria,
            nombre=f"Zapatos Cuero E{empresa_id}",
            descripcion="Calzado formal",
            precio=Decimal("200.00"),
            seccion="HOMBRE",
            estado=True,
        )
        p3 = Product(
            empresa_id=empresa_id,
            id_categoria=cat_moda.id_categoria,
            nombre=f"Camisa Formal E{empresa_id}",
            descripcion="Camisa ejecutiva",
            precio=Decimal("80.00"),
            seccion="HOMBRE",
            estado=True,
        )
        p4 = Product(
            empresa_id=empresa_id,
            id_categoria=cat_calzado.id_categoria,
            nombre=f"Cartera Cuero E{empresa_id}",
            descripcion="Accesorio elegante",
            precio=Decimal("120.00"),
            seccion="UNISEX",
            estado=True,
        )
        self.db.add_all([p1, p2, p3, p4])
        self.db.commit()

        v1 = ProductVariant(
            empresa_id=empresa_id,
            id_producto=p1.id_producto,
            id_talla=1,
            id_color=1,
            sku=f"SKU-E{empresa_id}-01",
            estado=True,
        )
        v2 = ProductVariant(
            empresa_id=empresa_id,
            id_producto=p2.id_producto,
            id_talla=2,
            id_color=2,
            sku=f"SKU-E{empresa_id}-02",
            estado=True,
        )
        v3 = ProductVariant(
            empresa_id=empresa_id,
            id_producto=p3.id_producto,
            id_talla=1,
            id_color=2,
            sku=f"SKU-E{empresa_id}-03",
            estado=True,
        )
        v4 = ProductVariant(
            empresa_id=empresa_id,
            id_producto=p4.id_producto,
            id_talla=2,
            id_color=1,
            sku=f"SKU-E{empresa_id}-04",
            estado=True,
        )
        self.db.add_all([v1, v2, v3, v4])
        self.db.commit()

        # 4. Inventario
        inv1 = BranchInventory(
            empresa_id=empresa_id,
            id_sucursal=b1.id_sucursal,
            id_variante_producto=v1.id_variante_producto,
            stock_actual=50,
            stock_minimo=10,
        )
        inv2 = BranchInventory(
            empresa_id=empresa_id,
            id_sucursal=b2.id_sucursal,
            id_variante_producto=v2.id_variante_producto,
            stock_actual=30,
            stock_minimo=5,
        )
        inv3 = BranchInventory(
            empresa_id=empresa_id,
            id_sucursal=b1.id_sucursal,
            id_variante_producto=v3.id_variante_producto,
            stock_actual=40,
            stock_minimo=5,
        )
        inv4 = BranchInventory(
            empresa_id=empresa_id,
            id_sucursal=b2.id_sucursal,
            id_variante_producto=v4.id_variante_producto,
            stock_actual=20,
            stock_minimo=5,
        )
        self.db.add_all([inv1, inv2, inv3, inv4])
        self.db.commit()

        # 5. Ventas completadas y detalles
        now = datetime.now()
        s1 = Sale(
            empresa_id=empresa_id,
            id_sucursal=b1.id_sucursal,
            id_cliente=1,
            id_empleado=1,
            numero_venta=f"VTA-E{empresa_id}-001",
            subtotal=Decimal("300.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("300.00"),
            canal="PRESENCIAL",
            moneda="BOB",
            estado="COMPLETADA",
            fecha_venta=now - timedelta(days=2),
            fecha_completada=now - timedelta(days=2),
        )
        s2 = Sale(
            empresa_id=empresa_id,
            id_sucursal=b2.id_sucursal,
            id_cliente=2,
            id_empleado=1,
            numero_venta=f"VTA-E{empresa_id}-002",
            subtotal=Decimal("400.00"),
            descuento_total=Decimal("0.00"),
            total=Decimal("400.00"),
            canal="DIGITAL",
            moneda="BOB",
            estado="COMPLETADA",
            fecha_venta=now - timedelta(days=5),
            fecha_completada=now - timedelta(days=5),
        )
        self.db.add_all([s1, s2])
        self.db.commit()

        d1 = SaleDetail(
            empresa_id=empresa_id,
            id_venta=s1.id_venta,
            id_variante_producto=v1.id_variante_producto,
            cantidad=2,
            precio_unitario=Decimal("150.00"),
            descuento_unitario=Decimal("0.00"),
            subtotal_linea=Decimal("300.00"),
        )
        d2 = SaleDetail(
            empresa_id=empresa_id,
            id_venta=s2.id_venta,
            id_variante_producto=v2.id_variante_producto,
            cantidad=2,
            precio_unitario=Decimal("200.00"),
            descuento_unitario=Decimal("0.00"),
            subtotal_linea=Decimal("400.00"),
        )
        self.db.add_all([d1, d2])
        self.db.commit()

        # 6. Reservas
        r1 = Reservation(
            empresa_id=empresa_id,
            id_cliente=1,
            id_sucursal=b1.id_sucursal,
            codigo=f"RES-{empresa_id}-001",
            estado="ATENDIDA",
            fecha_expiracion=now + timedelta(days=2),
            fecha_atencion_programada=now + timedelta(days=1),
            created_at=now - timedelta(days=3),
        )
        r2 = Reservation(
            empresa_id=empresa_id,
            id_cliente=2,
            id_sucursal=b1.id_sucursal,
            codigo=f"RES-{empresa_id}-002",
            estado="PENDIENTE",
            fecha_expiracion=now + timedelta(days=2),
            fecha_atencion_programada=now + timedelta(days=1),
            created_at=now - timedelta(days=1),
        )
        self.db.add_all([r1, r2])
        self.db.commit()

        # 7. Devoluciones
        ret1 = Return(
            empresa_id=empresa_id,
            id_venta=s1.id_venta,
            tipo="DEVOLUCION",
            estado="SOLICITADA",
            id_usuario_solicitante=1,
            motivo="Talla no adecuada",
            clave_idempotencia=uuid.uuid4(),
            created_at=now - timedelta(days=1),
        )
        self.db.add(ret1)
        self.db.commit()

        # 8. Reportes IA guardados (CU21)
        rep1 = GeneratedReport(
            empresa_id=empresa_id,
            id_usuario=1,
            tipo="VENTAS",
            titulo="Reporte Ventas Mensual",
            consulta="¿Cuáles fueron las ventas del último mes?",
            filtros_aplicados={},
            resultado={"resumen_ia": "Se generaron ventas por un total de 700.00 USD."},
            creado_en=now - timedelta(days=4),
        )
        self.db.add(rep1)
        self.db.commit()

        return {
            "b1": b1,
            "b2": b2,
            "cat_moda": cat_moda,
            "cat_calzado": cat_calzado,
            "p1": p1,
            "p2": p2,
        }

    def test_01_dashboard_kpis_and_filters(self):
        """1. Valida el cálculo de KPIs consolidados reales, filtros y tendencia diaria."""
        seeded = self._seed_company_data(empresa_id=1)

        # Validar obtención de filtros
        filters = AdminDashboardService.get_filters(self.db, empresa_id=1)
        self.assertEqual(len(filters.sucursales), 2)
        self.assertEqual(len(filters.categorias), 2)
        self.assertIn(30, filters.periodos_disponibles)

        # Validar consolidado analítico general (30 días)
        req = DashboardAnalyticsRequest(dias_periodo=30)
        res = AdminDashboardService.get_analytics(self.db, empresa_id=1, payload=req)

        self.assertTrue(res.success)
        # 2 ventas completadas: 300 + 400 = 700.00
        self.assertEqual(res.kpis.total_ventas, 2)
        self.assertEqual(res.kpis.ingresos_totales, 700.00)
        self.assertEqual(res.kpis.ticket_promedio, 350.00)
        self.assertEqual(res.kpis.unidades_vendidas, 4)
        # Stock: 50 + 30 + 40 + 20 = 140
        self.assertEqual(res.kpis.stock_disponible, 140)
        # Reservas: 2 totales, 1 atendida
        self.assertEqual(res.kpis.total_reservas, 2)
        self.assertEqual(res.kpis.reservas_atendidas, 1)
        # Devoluciones: 1 de 2 ventas = 50.0%
        self.assertEqual(res.kpis.total_devoluciones, 1)
        self.assertEqual(res.kpis.tasa_devolucion_pct, 50.0)

        # Canales: 1 Presencial (300) y 1 Digital (400)
        canales = {c.canal: c.ingresos for c in res.distribucion_canales}
        self.assertEqual(canales.get("PRESENCIAL"), 300.00)
        self.assertEqual(canales.get("DIGITAL"), 400.00)

        # Tendencia diaria: debe incluir puntos temporales
        self.assertGreater(len(res.tendencia_diaria), 0)

        # Filtro específico por sucursal 1 (Centro)
        req_b1 = DashboardAnalyticsRequest(dias_periodo=30, id_sucursal=seeded["b1"].id_sucursal)
        res_b1 = AdminDashboardService.get_analytics(self.db, empresa_id=1, payload=req_b1)
        self.assertEqual(res_b1.kpis.total_ventas, 1)
        self.assertEqual(res_b1.kpis.ingresos_totales, 300.00)
        self.assertEqual(res_b1.kpis.stock_disponible, 90)

    def test_02_integration_ml_predictions_patterns_reports(self):
        """2. Valida la integración de Machine Learning supervisado, no supervisado y reportes IA."""
        self._seed_company_data(empresa_id=1)

        req = DashboardAnalyticsRequest(dias_periodo=30)
        res = AdminDashboardService.get_analytics(self.db, empresa_id=1, payload=req)

        # CU22: Predicciones ML
        self.assertIn("GradientBoostingRegressor", res.ml_predicciones.algoritmo)
        self.assertGreater(res.ml_predicciones.r2, 0.8)
        self.assertGreaterEqual(len(res.ml_predicciones.items_riesgo), 1)
        first_item = res.ml_predicciones.items_riesgo[0]
        self.assertIn(first_item.nivel_riesgo, ["CRITICO", "ALTO", "MEDIO", "BAJO"])

        # CU23: Patrones ML
        self.assertIn("K-Means", res.ml_patrones.algoritmo)
        self.assertGreaterEqual(res.ml_patrones.silhouette_score, 0.0)
        self.assertGreaterEqual(len(res.ml_patrones.segmentos), 1)

        # CU20/CU21: Reportes con IA guardados
        self.assertEqual(res.reportes_ia.total_reportes_guardados, 1)
        self.assertEqual(len(res.reportes_ia.ultimos_reportes), 1)
        self.assertEqual(res.reportes_ia.ultimos_reportes[0].tipo, "VENTAS")
        self.assertIn("Reporte Ventas", res.reportes_ia.ultimos_reportes[0].titulo)

    def test_03_multitenant_security_and_sparse_data(self):
        """3. Valida aislamiento multitenant estricto y robustez ante empresas sin transacciones."""
        seeded_1 = self._seed_company_data(empresa_id=1)
        seeded_2 = self._seed_company_data(empresa_id=2)

        # Aislamiento: Empresa 1 ve solo sus ventas (700), no las de Empresa 2
        req = DashboardAnalyticsRequest(dias_periodo=30)
        res_1 = AdminDashboardService.get_analytics(self.db, empresa_id=1, payload=req)
        res_2 = AdminDashboardService.get_analytics(self.db, empresa_id=2, payload=req)
        self.assertEqual(res_1.kpis.ingresos_totales, 700.00)
        self.assertEqual(res_2.kpis.ingresos_totales, 700.00)

        # Intento de cruce de empresa: Empresa 1 filtra con sucursal de Empresa 2 -> 404
        req_cross_branch = DashboardAnalyticsRequest(
            dias_periodo=30, id_sucursal=seeded_2["b1"].id_sucursal
        )
        with self.assertRaises(HTTPException) as ctx_branch:
            AdminDashboardService.get_analytics(self.db, empresa_id=1, payload=req_cross_branch)
        self.assertEqual(ctx_branch.exception.status_code, 404)

        # Intento de cruce de empresa: Empresa 1 filtra con categoría de Empresa 2 -> 404
        req_cross_cat = DashboardAnalyticsRequest(
            dias_periodo=30, id_categoria=seeded_2["cat_moda"].id_categoria
        )
        with self.assertRaises(HTTPException) as ctx_cat:
            AdminDashboardService.get_analytics(self.db, empresa_id=1, payload=req_cross_cat)
        self.assertEqual(ctx_cat.exception.status_code, 404)

        # Robustez ante empresa nueva sin transacciones ni catálogo (empresa_id=99)
        set_tenant_context(self.db, 99)
        res_empty = AdminDashboardService.get_analytics(self.db, empresa_id=99, payload=req)
        self.assertTrue(res_empty.success)
        self.assertEqual(res_empty.kpis.total_ventas, 0)
        self.assertEqual(res_empty.kpis.ingresos_totales, 0.0)
        self.assertEqual(res_empty.kpis.ticket_promedio, 0.0)
        self.assertEqual(res_empty.kpis.stock_disponible, 0)
        self.assertEqual(res_empty.kpis.tasa_devolucion_pct, 0.0)
        self.assertEqual(res_empty.reportes_ia.total_reportes_guardados, 0)
