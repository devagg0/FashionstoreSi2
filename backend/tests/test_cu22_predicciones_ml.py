"""CU22: Generar predicciones mediante Machine Learning.
Pruebas focalizadas:
1. Generación del dataset sintético, entrenamiento y evaluación del modelo supervisado (sin fuga de datos).
2. Predicción con filtros y datos empresariales reales (7, 15 y 30 días).
3. Seguridad multitenant, validación de permisos y manejo de datos insuficientes.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.tenant_context import set_tenant_context
from app.ml.demand_predictor import (
    DemandPredictor,
    generate_synthetic_fashion_dataset,
    train_demand_model,
)
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.schemas.admin_predictions import PredictionRequest
from app.services.admin_predictions import AdminPredictionsService


class CU22MachineLearningPredictionsTests(TestCase):
    """Batería de validación focalizada para el CU22 según requerimientos."""

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

    def _seed_company_data(self, empresa_id: int):
        set_tenant_context(self.db, empresa_id)
        cat = Category(
            empresa_id=empresa_id,
            nombre=f"Moda Empresa {empresa_id}",
            descripcion="Categoría test",
            estado=True,
        )
        branch = Branch(
            empresa_id=empresa_id,
            id_ciudad=1,
            nombre=f"Sucursal Central E{empresa_id}",
            direccion=f"Av. Principal {empresa_id}",
            estado=True,
        )
        self.db.add_all([cat, branch])
        self.db.commit()

        prod = Product(
            empresa_id=empresa_id,
            id_categoria=cat.id_categoria,
            nombre=f"Vestido Floral E{empresa_id}",
            seccion="MUJER",
            descripcion="Vestido de verano",
            precio=Decimal("120.00"),
            estado=True,
        )
        self.db.add(prod)
        self.db.commit()

        var = ProductVariant(
            empresa_id=empresa_id,
            id_producto=prod.id_producto,
            id_talla=1,
            id_color=1,
            sku=f"VF-E{empresa_id}-M",
            estado=True,
        )
        self.db.add(var)
        self.db.commit()

        inv = BranchInventory(
            empresa_id=empresa_id,
            id_sucursal=branch.id_sucursal,
            id_variante_producto=var.id_variante_producto,
            stock_actual=25,
            stock_reservado=0,
            stock_minimo=5,
        )
        self.db.add(inv)

        # Sembrar ventas en últimos 7, 14 y 30 días
        now = datetime.utcnow()
        fechas_ventas = [
            (now - timedelta(days=2), 3),
            (now - timedelta(days=5), 4),
            (now - timedelta(days=10), 5),
            (now - timedelta(days=20), 8),
        ]
        for i, (f_venta, qty) in enumerate(fechas_ventas, start=1):
            sale = Sale(
                empresa_id=empresa_id,
                id_sucursal=branch.id_sucursal,
                numero_venta=f"V-{empresa_id}-{i}",
                canal="DIGITAL",
                id_cliente=1,
                moneda="BOB",
                subtotal=Decimal(str(qty * 120)),
                descuento_total=Decimal("0.00"),
                total=Decimal(str(qty * 120)),
                estado="COMPLETADA",
                fecha_venta=f_venta,
                fecha_completada=f_venta,
            )
            self.db.add(sale)
            self.db.commit()

            detail = SaleDetail(
                empresa_id=empresa_id,
                id_venta=sale.id_venta,
                id_variante_producto=var.id_variante_producto,
                cantidad=qty,
                precio_unitario=Decimal("120.00"),
                descuento_unitario=Decimal("0.00"),
                subtotal_linea=Decimal(str(qty * 120)),
            )
            self.db.add(detail)

        self.db.commit()
        return branch, prod

    # =========================================================================
    # PRUEBA 1: Dataset sintético, entrenamiento y evaluación del modelo ML
    # =========================================================================
    def test_01_dataset_training_and_evaluation(self):
        """Prueba 1: Pipeline ML reproducible, sin fuga de datos, con métricas MAE/RMSE/R2."""
        from app.ml.demand_predictor import FEATURE_NAMES

        # 1. Generación reproducible
        X, y = generate_synthetic_fashion_dataset(n_samples=1500, seed=42)
        self.assertEqual(len(X), 1500)
        self.assertEqual(len(y), 1500)
        self.assertEqual(X.shape[1], 11)
        self.assertEqual(len(FEATURE_NAMES), 11)
        self.assertIn("ventas_ultimos_7d", FEATURE_NAMES)
        self.assertIn("dias_horizonte", FEATURE_NAMES)
        self.assertIn("seccion_MUJER", FEATURE_NAMES)

        # 2. Entrenamiento y evaluación formal
        meta = train_demand_model(n_samples=2000, seed=42)
        self.assertIn("metricas", meta)
        metricas = meta["metricas"]
        mae = metricas["mae"]
        rmse = metricas["rmse"]
        r2 = metricas["r2"]

        # Validar umbrales estadísticos de calidad supervisada
        self.assertLess(mae, 2.5, f"MAE demasiado alto: {mae}")
        self.assertLess(rmse, 3.5, f"RMSE demasiado alto: {rmse}")
        self.assertGreater(r2, 0.85, f"R² insuficiente: {r2}")
        self.assertTrue(meta["es_experimental"])
        self.assertEqual(meta["algoritmo"], "GradientBoostingRegressor (scikit-learn)")

        # 3. Inferencia directa a través de DemandPredictor Singleton
        predictor = DemandPredictor.get_instance()
        pred = predictor.predict(
            precio_unitario=120.0,
            ventas_ultimos_7d=7,
            ventas_ultimos_14d=12,
            ventas_ultimos_30d=20,
            stock_actual=25,
            dias_horizonte=15,
            mes=11,
            es_temporada_alta=1,
            seccion="MUJER",
        )
        self.assertGreater(pred, 0.0)
        self.assertIsInstance(pred, float)

    # =========================================================================
    # PRUEBA 2: Predicción con filtros y datos empresariales reales
    # =========================================================================
    def test_02_prediction_with_real_business_data_and_filters(self):
        """Prueba 2: Consulta de filtros y predicción para horizontes 7, 15 y 30 días."""
        branch, prod = self._seed_company_data(empresa_id=1)

        # 1. Filtros disponibles
        filters = AdminPredictionsService.get_filters(self.db, empresa_id=1)
        self.assertTrue(any(p.id == prod.id_producto for p in filters.productos))
        self.assertTrue(any(s.id == branch.id_sucursal for s in filters.sucursales))
        self.assertEqual(filters.horizontes_disponibles, [7, 15, 30])

        # 2. Predicción para 7, 15 y 30 días
        for horizonte in [7, 15, 30]:
            req = PredictionRequest(
                id_producto=prod.id_producto,
                id_sucursal=branch.id_sucursal,
                horizonte_dias=horizonte,
            )
            response = AdminPredictionsService.generate_prediction(
                self.db,
                empresa_id=1,
                payload=req,
            )

            self.assertTrue(response.success)
            self.assertEqual(response.horizonte_dias, horizonte)
            self.assertEqual(response.producto_nombre, prod.nombre)
            self.assertEqual(response.sucursal_nombre, branch.nombre)

            # Verificar datos históricos reales capturados
            self.assertEqual(response.historico.ventas_ultimos_7d, 7)  # 3 + 4
            self.assertEqual(response.historico.ventas_ultimos_14d, 12)  # 7 + 5
            self.assertEqual(response.historico.ventas_ultimos_30d, 20)  # 12 + 8
            self.assertEqual(response.historico.stock_actual, 25)
            self.assertTrue(response.historico.datos_suficientes)

            # Verificar estructura de predicción
            pred = response.prediccion
            self.assertGreaterEqual(pred.demanda_estimada, 0)
            self.assertLessEqual(pred.rango_minimo, pred.demanda_estimada)
            self.assertGreaterEqual(pred.rango_maximo, pred.demanda_estimada)
            self.assertIn(pred.nivel_riesgo, ["BAJO", "MEDIO", "ALTO", "CRITICO"])
            self.assertIn(pred.confianza_estimacion, ["ALTA", "MEDIA", "EXPERIMENTAL"])

            # Serie temporal: 14 días históricos + N días proyectados
            self.assertEqual(len(response.serie_temporal), 14 + horizonte)
            reales = [p for p in response.serie_temporal if p.tipo == "REAL"]
            proy = [p for p in response.serie_temporal if p.tipo == "PROYECTADO"]
            self.assertEqual(len(reales), 14)
            self.assertEqual(len(proy), horizonte)

            # Disclaimer presente
            self.assertTrue(len(response.disclaimer) > 10)

    # =========================================================================
    # PRUEBA 3: Seguridad multitenant, permisos y manejo de datos insuficientes
    # =========================================================================
    def test_03_multitenant_security_and_insufficient_data(self):
        """Prueba 3: Aislamiento tenant (empresa A vs B), validaciones y datos insuficientes."""
        branch_e1, prod_e1 = self._seed_company_data(empresa_id=1)
        branch_e2, prod_e2 = self._seed_company_data(empresa_id=2)

        # 1. Aislamiento tenant: Empresa 1 intentando consultar producto de Empresa 2
        req_cross_prod = PredictionRequest(
            id_producto=prod_e2.id_producto,
            id_sucursal=branch_e1.id_sucursal,
            horizonte_dias=15,
        )
        with self.assertRaises(HTTPException) as ctx_prod:
            AdminPredictionsService.generate_prediction(self.db, empresa_id=1, payload=req_cross_prod)
        self.assertEqual(ctx_prod.exception.status_code, 404)

        # 2. Aislamiento tenant: Empresa 1 intentando consultar sucursal de Empresa 2
        req_cross_branch = PredictionRequest(
            id_producto=prod_e1.id_producto,
            id_sucursal=branch_e2.id_sucursal,
            horizonte_dias=15,
        )
        with self.assertRaises(HTTPException) as ctx_branch:
            AdminPredictionsService.generate_prediction(self.db, empresa_id=1, payload=req_cross_branch)
        self.assertEqual(ctx_branch.exception.status_code, 404)

        # 3. Validación de horizonte inválido (solo 7, 15, 30 permitidos)
        req_invalid_horizon = PredictionRequest(
            id_producto=prod_e1.id_producto,
            id_sucursal=branch_e1.id_sucursal,
            horizonte_dias=45,
        )
        with self.assertRaises(HTTPException) as ctx_horizon:
            AdminPredictionsService.generate_prediction(self.db, empresa_id=1, payload=req_invalid_horizon)
        self.assertEqual(ctx_horizon.exception.status_code, 400)

        # 4. Manejo honesto de datos insuficientes (nuevo producto sin ventas ni stock)
        set_tenant_context(self.db, 1)
        new_prod = Product(
            empresa_id=1,
            id_categoria=1,
            nombre="Producto Nuevo Sin Historial",
            seccion="HOMBRE",
            precio=Decimal("80.00"),
            estado=True,
        )
        self.db.add(new_prod)
        self.db.commit()

        req_new = PredictionRequest(
            id_producto=new_prod.id_producto,
            id_sucursal=branch_e1.id_sucursal,
            horizonte_dias=15,
        )
        res_new = AdminPredictionsService.generate_prediction(self.db, empresa_id=1, payload=req_new)
        self.assertFalse(res_new.historico.datos_suficientes)
        self.assertEqual(res_new.historico.ventas_ultimos_30d, 0)
        self.assertEqual(res_new.historico.stock_actual, 0)
        self.assertEqual(res_new.prediccion.confianza_estimacion, "EXPERIMENTAL")
        self.assertIn("insuficientes", res_new.historico.mensaje_suficiencia.lower())
        self.assertIn("orientativa", res_new.prediccion.explicacion.lower())
        self.assertIn("no una necesidad confirmada", res_new.prediccion.explicacion.lower())

        # 5. Endpoint de metadatos del modelo
        info = AdminPredictionsService.get_model_info()
        self.assertEqual(info.algoritmo, "GradientBoostingRegressor (scikit-learn)")
        self.assertTrue(info.es_experimental)
        self.assertGreater(len(info.variables), 5)
        self.assertGreater(info.dataset_size, 0)
