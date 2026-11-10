"""CU23: Analizar patrones de comportamiento mediante Machine Learning.
Pruebas focalizadas:
1. Entrenamiento y evaluación reproducibles del modelo no supervisado (K-Means + Silhouette score).
2. Análisis de patrones con datos reales y filtros empresariales (sucursales, categorías, fechas).
3. Manejo de datos insuficientes y aislamiento multitenant.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.ml.pattern_analyzer import (
    FEATURE_NAMES,
    generate_synthetic_pattern_dataset,
    train_reference_pattern_model,
)
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.schemas.admin_patterns import PatternAnalysisRequest
from app.services.admin_patterns import AdminPatternsService


class CU23UnsupervisedPatternAnalysisTests(TestCase):
    """Batería de validación focalizada para el CU23."""

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
        ):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def _seed_company_catalog(self, empresa_id: int):
        set_tenant_context(self.db, empresa_id)
        cat_moda = Category(empresa_id=empresa_id, nombre=f"Moda E{empresa_id}", estado=True)
        cat_formal = Category(empresa_id=empresa_id, nombre=f"Formal E{empresa_id}", estado=True)
        branch = Branch(empresa_id=empresa_id, id_ciudad=1, nombre=f"Central E{empresa_id}", direccion="Dir", estado=True)
        self.db.add_all([cat_moda, cat_formal, branch])
        self.db.commit()

        # Sembrar 6 productos con perfiles comerciales diferenciados para Empresa 1
        products_def = [
            ("Vestido Fiesta", cat_formal.id_categoria, "MUJER", Decimal("180.00"), 40, 25),   # Estrella
            ("Blusa Seda", cat_moda.id_categoria, "MUJER", Decimal("140.00"), 35, 20),         # Estrella
            ("Abrigo Premium", cat_formal.id_categoria, "UNISEX", Decimal("350.00"), 12, 10),   # Premium
            ("Camiseta Básica", cat_moda.id_categoria, "UNISEX", Decimal("50.00"), 50, 40),     # Flujo
            ("Pantalón Denim", cat_moda.id_categoria, "HOMBRE", Decimal("70.00"), 30, 35),      # Flujo
            ("Bufanda Invierno", cat_moda.id_categoria, "UNISEX", Decimal("90.00"), 0, 30),     # Hueso (sin ventas)
        ]

        now = datetime.now()
        seeded_products = []

        for idx, (p_nom, cat_id, sec, precio, ventas_qty, stock_qty) in enumerate(products_def, start=1):
            prod = Product(
                empresa_id=empresa_id,
                id_categoria=cat_id,
                nombre=p_nom,
                seccion=sec,
                precio=precio,
                estado=True,
            )
            self.db.add(prod)
            self.db.commit()

            var = ProductVariant(
                empresa_id=empresa_id,
                id_producto=prod.id_producto,
                id_talla=1,
                id_color=1,
                sku=f"SKU-E{empresa_id}-{idx}",
                estado=True,
            )
            self.db.add(var)
            self.db.commit()

            inv = BranchInventory(
                empresa_id=empresa_id,
                id_sucursal=branch.id_sucursal,
                id_variante_producto=var.id_variante_producto,
                stock_actual=stock_qty,
                stock_reservado=0,
                stock_minimo=5,
            )
            self.db.add(inv)
            self.db.commit()

            # Registrar ventas si ventas_qty > 0
            if ventas_qty > 0:
                sale = Sale(
                    empresa_id=empresa_id,
                    id_sucursal=branch.id_sucursal,
                    numero_venta=f"V-{empresa_id}-{idx}",
                    canal="DIGITAL",
                    id_cliente=1,
                    moneda="BOB",
                    subtotal=Decimal(str(ventas_qty * float(precio))),
                    descuento_total=Decimal("0.00"),
                    total=Decimal(str(ventas_qty * float(precio))),
                    estado="COMPLETADA",
                    fecha_venta=now - timedelta(days=5),
                    fecha_completada=now - timedelta(days=5),
                )
                self.db.add(sale)
                self.db.commit()

                detail = SaleDetail(
                    empresa_id=empresa_id,
                    id_venta=sale.id_venta,
                    id_variante_producto=var.id_variante_producto,
                    cantidad=ventas_qty,
                    precio_unitario=precio,
                    descuento_unitario=Decimal("0.00"),
                    subtotal_linea=Decimal(str(ventas_qty * float(precio))),
                )
                self.db.add(detail)
                self.db.commit()

            seeded_products.append(prod)

        return branch, cat_moda, seeded_products

    # =========================================================================
    # PRUEBA 1: Entrenamiento y evaluación reproducibles del modelo K-Means
    # =========================================================================
    def test_01_unsupervised_training_and_evaluation(self):
        """Prueba 1: Pipeline no supervisado, selección de variables y evaluación Silhouette."""
        # 1. Dataset sintético reproducible
        X = generate_synthetic_pattern_dataset(n_samples=400, seed=42)
        self.assertEqual(X.shape, (400, 6))
        self.assertEqual(len(FEATURE_NAMES), 6)
        self.assertIn("ratio_rotacion", FEATURE_NAMES)
        self.assertIn("ingresos_totales", FEATURE_NAMES)

        # 2. Entrenamiento y evaluación formal
        meta = train_reference_pattern_model(n_samples=400, seed=42)
        self.assertEqual(meta["tipo_aprendizaje"], "No supervisado")
        self.assertEqual(meta["n_clusters"], 4)

        metricas = meta["metricas"]
        self.assertIn("silhouette_score", metricas)
        self.assertIn("inercia", metricas)
        # El Silhouette Score debe superar 0.35 para indicar agrupamiento estructurado
        self.assertGreater(metricas["silhouette_score"], 0.35)
        self.assertGreater(metricas["inercia"], 0.0)

    # =========================================================================
    # PRUEBA 2: Análisis de patrones con datos reales y filtros empresariales
    # =========================================================================
    def test_02_pattern_analysis_with_real_business_data_and_filters(self):
        """Prueba 2: Agrupación K-Means de 6 productos reales con centroides justificados."""
        branch, cat, products = self._seed_company_catalog(empresa_id=1)

        # 1. Filtros disponibles
        filters = AdminPatternsService.get_filters(self.db, empresa_id=1)
        self.assertTrue(any(s.id == branch.id_sucursal for s in filters.sucursales))
        self.assertTrue(any(c.id == cat.id_categoria for c in filters.categorias))

        # 2. Análisis global de la empresa a 30 días
        req = PatternAnalysisRequest(dias_periodo=30)
        res = AdminPatternsService.analyze_patterns(self.db, empresa_id=1, payload=req)

        self.assertTrue(res.success)
        self.assertTrue(res.datos_suficientes)
        self.assertEqual(res.total_productos_analizados, 6)
        self.assertGreater(res.total_unidades_vendidas, 100)
        self.assertGreater(res.total_ingresos_facturados, 5000.0)

        # Verificar segmentos descubiertos
        self.assertGreater(len(res.segmentos), 1)
        nombres_segmentos = [s.nombre for s in res.segmentos]
        self.assertTrue(any("Alto Rendimiento" in n or "Estrella" in n for n in nombres_segmentos))
        self.assertTrue(any("Baja Rotación" in n for n in nombres_segmentos))

        # Cada producto clasificado tiene cluster asignado
        self.assertEqual(len(res.productos), 6)
        for p in res.productos:
            self.assertIsNotNone(p.id_cluster)
            self.assertNotEqual(p.cluster_nombre, "Sin Clasificar")
            self.assertTrue(p.cluster_color.startswith("#"))

        # Métricas de evaluación presentes
        self.assertIsInstance(res.metricas.silhouette_score, float)
        self.assertGreaterEqual(res.metricas.silhouette_score, -1.0)
        self.assertLessEqual(res.metricas.silhouette_score, 1.0)

        # 3. Análisis con filtro por sucursal específica
        req_branch = PatternAnalysisRequest(dias_periodo=30, id_sucursal=branch.id_sucursal)
        res_branch = AdminPatternsService.analyze_patterns(self.db, empresa_id=1, payload=req_branch)
        self.assertEqual(res_branch.total_productos_analizados, 6)

    # =========================================================================
    # PRUEBA 3: Manejo de datos insuficientes y aislamiento multitenant
    # =========================================================================
    def test_03_multitenant_isolation_and_insufficient_data(self):
        """Prueba 3: Aislamiento tenant y resultado controlado cuando hay < 4 productos."""
        branch_e1, cat_e1, _ = self._seed_company_catalog(empresa_id=1)
        branch_e2, cat_e2, _ = self._seed_company_catalog(empresa_id=2)

        # 1. Aislamiento tenant: Empresa 1 intentando filtrar por sucursal de Empresa 2
        req_cross_branch = PatternAnalysisRequest(id_sucursal=branch_e2.id_sucursal)
        with self.assertRaises(HTTPException) as ctx_branch:
            AdminPatternsService.analyze_patterns(self.db, empresa_id=1, payload=req_cross_branch)
        self.assertEqual(ctx_branch.exception.status_code, 404)

        # 2. Aislamiento tenant: Empresa 1 intentando filtrar por categoría de Empresa 2
        req_cross_cat = PatternAnalysisRequest(id_categoria=cat_e2.id_categoria)
        with self.assertRaises(HTTPException) as ctx_cat:
            AdminPatternsService.analyze_patterns(self.db, empresa_id=1, payload=req_cross_cat)
        self.assertEqual(ctx_cat.exception.status_code, 404)

        # 3. Manejo controlado de datos insuficientes (Empresa 3 con solo 2 productos)
        set_tenant_context(self.db, 3)
        c3 = Category(empresa_id=3, nombre="Cat E3", estado=True)
        b3 = Branch(empresa_id=3, id_ciudad=1, nombre="Suc E3", direccion="D3", estado=True)
        p1 = Product(empresa_id=3, id_categoria=1, nombre="P1 E3", seccion="UNISEX", precio=Decimal("100"), estado=True)
        p2 = Product(empresa_id=3, id_categoria=1, nombre="P2 E3", seccion="UNISEX", precio=Decimal("120"), estado=True)
        self.db.add_all([c3, b3, p1, p2])
        self.db.commit()

        req_e3 = PatternAnalysisRequest(dias_periodo=30)
        res_e3 = AdminPatternsService.analyze_patterns(self.db, empresa_id=3, payload=req_e3)

        self.assertTrue(res_e3.success)
        self.assertFalse(res_e3.datos_suficientes)
        self.assertEqual(res_e3.total_productos_analizados, 2)
        self.assertEqual(len(res_e3.segmentos), 0)
        self.assertIn("mínimo de 4 productos", res_e3.mensaje)
        self.assertEqual(res_e3.metricas.silhouette_score, 0.0)

        # 4. Metadatos del modelo referencial
        info = AdminPatternsService.get_model_info()
        self.assertEqual(info.tipo_aprendizaje, "No supervisado")
        self.assertTrue(info.es_experimental)
        self.assertGreater(len(info.variables), 4)

