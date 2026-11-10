"""Servicio de predicciones de demanda supervisada con Machine Learning (CU22)."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.demand_predictor import DemandPredictor
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.schemas.admin_predictions import (
    DailyTrendPoint,
    HistoricalContext,
    ModelEvaluationMetrics,
    ModelInfoResponse,
    PredictionFilterItem,
    PredictionFiltersResponse,
    PredictionRequest,
    PredictionResponse,
    PredictionResult,
)

logger = logging.getLogger(__name__)

HORIZONTES_PERMITIDOS = [7, 15, 30]


class AdminPredictionsService:
    """Lógica de negocio y orquestación ML para predicción de demanda."""

    @staticmethod
    def get_model_info() -> ModelInfoResponse:
        """Devuelve los metadatos y métricas reales del modelo supervisado."""
        predictor = DemandPredictor.get_instance()
        meta = predictor.get_metadata()
        metricas = meta.get("metricas", {})

        return ModelInfoResponse(
            algoritmo=meta.get("algoritmo", "GradientBoostingRegressor (scikit-learn)"),
            descripcion=meta.get(
                "descripcion",
                "Modelo supervisado de regresión para estimar demanda de prendas",
            ),
            variables=meta.get("variables", []),
            total_variables=meta.get("total_variables", len(meta.get("variables", []))),
            dataset_size=meta.get("dataset_size", 3000),
            train_size=meta.get("train_size", 2400),
            test_size=meta.get("test_size", 600),
            metricas=ModelEvaluationMetrics(
                mae=float(metricas.get("mae", 1.6)),
                rmse=float(metricas.get("rmse", 2.14)),
                r2=float(metricas.get("r2", 0.96)),
            ),
            es_experimental=meta.get("es_experimental", True),
            nota_metodologica=meta.get(
                "nota_metodologica",
                "Entrenado sobre datos sintéticos generados para FashionStore. Las predicciones son estimaciones orientativas.",
            ),
            entrenado_en=meta.get("entrenado_en"),
        )

    @staticmethod
    def get_filters(db: Session, empresa_id: int) -> PredictionFiltersResponse:
        """Obtiene las listas de productos y sucursales activas pertenecientes a la empresa."""
        productos_stmt = (
            select(Product)
            .where(
                Product.empresa_id == empresa_id,
                Product.estado == True,  # noqa: E712
            )
            .order_by(Product.nombre.asc())
        )
        productos = [
            PredictionFilterItem(
                id=p.id_producto,
                nombre=p.nombre,
                codigo=f"SECC-{p.seccion}",
                extra=f"Bs. {float(p.precio):.2f}",
            )
            for p in db.execute(productos_stmt).scalars().all()
        ]

        sucursales_stmt = (
            select(Branch)
            .where(
                Branch.empresa_id == empresa_id,
                Branch.estado == True,  # noqa: E712
            )
            .order_by(Branch.nombre.asc())
        )
        sucursales = [
            PredictionFilterItem(
                id=s.id_sucursal,
                nombre=s.nombre,
                codigo=s.direccion,
            )
            for s in db.execute(sucursales_stmt).scalars().all()
        ]

        return PredictionFiltersResponse(
            productos=productos,
            sucursales=sucursales,
            horizontes_disponibles=HORIZONTES_PERMITIDOS,
        )

    @classmethod
    def generate_prediction(
        cls,
        db: Session,
        empresa_id: int,
        payload: PredictionRequest,
    ) -> PredictionResponse:
        """Genera una predicción supervisada para un producto y sucursal específicos."""
        if payload.horizonte_dias not in HORIZONTES_PERMITIDOS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Horizonte no válido. Debe ser uno de {HORIZONTES_PERMITIDOS} días.",
            )

        # 1. Validar producto y aislamiento tenant
        product = db.execute(
            select(Product).where(
                Product.id_producto == payload.id_producto,
                Product.empresa_id == empresa_id,
            )
        ).scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El producto no existe o no pertenece a la empresa.",
            )

        # 2. Validar sucursal y aislamiento tenant
        branch = db.execute(
            select(Branch).where(
                Branch.id_sucursal == payload.id_sucursal,
                Branch.empresa_id == empresa_id,
            )
        ).scalar_one_or_none()
        if not branch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La sucursal no existe o no pertenece a la empresa.",
            )

        # 3. Obtener variantes del producto
        variant_ids = db.execute(
            select(ProductVariant.id_variante_producto).where(
                ProductVariant.id_producto == product.id_producto,
                ProductVariant.empresa_id == empresa_id,
            )
        ).scalars().all()

        # 4. Obtener stock actual de inventario en la sucursal
        stock_actual = 0
        stock_minimo = 0
        if variant_ids:
            inv_row = db.execute(
                select(
                    func.coalesce(func.sum(BranchInventory.stock_actual), 0),
                    func.coalesce(func.sum(BranchInventory.stock_minimo), 0),
                ).where(
                    BranchInventory.id_sucursal == branch.id_sucursal,
                    BranchInventory.id_variante_producto.in_(variant_ids),
                    BranchInventory.empresa_id == empresa_id,
                )
            ).one()
            stock_actual = int(inv_row[0] or 0)
            stock_minimo = int(inv_row[1] or 0)

        # 5. Obtener ventas históricas reales en los últimos 30, 14 y 7 días
        now = datetime.utcnow()
        since_30d = now - timedelta(days=30)

        ventas_7d = 0
        ventas_14d = 0
        ventas_30d = 0

        # Mapeo de ventas diarias para los últimos 14 días (para el gráfico comparativo)
        dias_historia = 14
        hist_fechas = [
            (now - timedelta(days=d)).strftime("%Y-%m-%d")
            for d in range(dias_historia, 0, -1)
        ]
        daily_sales_map: Dict[str, float] = {f: 0.0 for f in hist_fechas}

        if variant_ids:
            sales_stmt = (
                select(
                    func.date(Sale.fecha_venta).label("fecha_dia"),
                    func.sum(SaleDetail.cantidad).label("unidades"),
                )
                .join(SaleDetail, Sale.id_venta == SaleDetail.id_venta)
                .where(
                    Sale.id_sucursal == branch.id_sucursal,
                    Sale.empresa_id == empresa_id,
                    Sale.estado == "COMPLETADA",
                    Sale.fecha_venta >= since_30d,
                    SaleDetail.id_variante_producto.in_(variant_ids),
                    SaleDetail.empresa_id == empresa_id,
                )
                .group_by(func.date(Sale.fecha_venta))
            )

            for row in db.execute(sales_stmt).all():
                fecha_raw = row[0]
                total_qty = int(row[1] or 0)

                fecha_str = (
                    fecha_raw.strftime("%Y-%m-%d")
                    if hasattr(fecha_raw, "strftime")
                    else str(fecha_raw)[:10]
                )

                try:
                    f_date = datetime.strptime(fecha_str, "%Y-%m-%d")
                    delta_dias = (now.date() - f_date.date()).days
                except Exception:
                    delta_dias = 0

                if delta_dias <= 30:
                    ventas_30d += total_qty
                if delta_dias <= 14:
                    ventas_14d += total_qty
                    if fecha_str in daily_sales_map:
                        daily_sales_map[fecha_str] = float(total_qty)
                if delta_dias <= 7:
                    ventas_7d += total_qty

        # 6. Validación de datos insuficientes
        datos_suficientes = bool(ventas_30d > 0 or stock_actual > 0)
        if datos_suficientes:
            mensaje_suficiencia = (
                f"Se registraron {ventas_30d} unidades vendidas en los últimos 30 días "
                f"y un stock actual de {stock_actual} unidades."
            )
            confianza = "ALTA" if ventas_30d >= 10 else "MEDIA"
        else:
            mensaje_suficiencia = (
                "Datos históricos insuficientes o sin ventas registradas para este producto en la sucursal. "
                "La predicción se calcula como estimación teórica experimental basada en precio y sección."
            )
            confianza = "EXPERIMENTAL"

        # 7. Inferencia con el modelo supervisado
        predictor = DemandPredictor.get_instance()
        precio_unitario = float(product.precio)
        mes_actual = now.month
        es_temporada_alta = 1 if mes_actual in [5, 11, 12] else 0

        pred_raw = predictor.predict(
            precio_unitario=precio_unitario,
            ventas_ultimos_7d=ventas_7d,
            ventas_ultimos_14d=ventas_14d,
            ventas_ultimos_30d=ventas_30d,
            stock_actual=stock_actual,
            dias_horizonte=payload.horizonte_dias,
            mes=mes_actual,
            es_temporada_alta=es_temporada_alta,
            seccion=product.seccion,
        )

        demanda_estimada = max(0, int(round(pred_raw)))
        unidades_diarias_prom = round(demanda_estimada / float(payload.horizonte_dias), 2)

        # Rango de estimación considerando el MAE del modelo
        meta = predictor.get_metadata()
        mae = float(meta.get("metricas", {}).get("mae", 1.6))
        factor_horizonte = max(1.0, payload.horizonte_dias / 15.0)
        margen = max(1, int(round(mae * factor_horizonte)))
        rango_min = max(0, demanda_estimada - margen)
        rango_max = demanda_estimada + margen

        # Cobertura y autonomía de stock coherente con la tasa diaria y el horizonte
        tasa_diaria_exacta = (
            float(demanda_estimada) / float(payload.horizonte_dias)
            if payload.horizonte_dias > 0
            else 0.0
        )
        if stock_actual == 0:
            cobertura_dias = 0.0
        elif tasa_diaria_exacta > 0:
            cobertura_dias = round(float(stock_actual) / tasa_diaria_exacta, 1)
        else:
            cobertura_dias = None

        riesgo_desabastecimiento = stock_actual < demanda_estimada

        if stock_actual == 0 and demanda_estimada > 0:
            nivel_riesgo = "CRITICO"
        elif stock_actual < demanda_estimada * 0.5:
            nivel_riesgo = "ALTO"
        elif stock_actual < demanda_estimada:
            nivel_riesgo = "MEDIO"
        else:
            nivel_riesgo = "BAJO"

        if not datos_suficientes:
            # Caso sin historial previo o datos limitados:
            # Conservar advertencia experimental y presentar recomendaciones como estimaciones orientativas
            if riesgo_desabastecimiento:
                deficit = demanda_estimada - stock_actual
                explicacion = (
                    f"Al no registrarse ventas previas ni rotación histórica en esta sucursal, "
                    f"la demanda de {demanda_estimada} unidades (rango [{rango_min} - {rango_max}]) a {payload.horizonte_dias} días "
                    f"constituye una estimación teórica orientativa basada en precio y sección. "
                    f"La sugerencia de reposición de ~{deficit} unidades es una estimación orientativa, no una necesidad confirmada."
                )
            else:
                explicacion = (
                    f"Sin historial de ventas reciente en la sucursal. La demanda proyectada de {demanda_estimada} unidades "
                    f"es una estimación orientativa experimental. El stock disponible de {stock_actual} unidades cubre el escenario teórico a {payload.horizonte_dias} días."
                )
        else:
            if riesgo_desabastecimiento:
                deficit = demanda_estimada - stock_actual
                explicacion = (
                    f"Demanda proyectada de {demanda_estimada} unidades (rango [{rango_min} - {rango_max}]) "
                    f"para los próximos {payload.horizonte_dias} días supera el stock disponible ({stock_actual} un.). "
                    f"Nivel de riesgo de desabastecimiento: {nivel_riesgo}. Se sugiere reposición de al menos {deficit} unidades."
                )
            else:
                explicacion = (
                    f"Demanda proyectada de {demanda_estimada} unidades (rango [{rango_min} - {rango_max}]) "
                    f"para los próximos {payload.horizonte_dias} días está cubierta por el stock actual ({stock_actual} un.). "
                    f"Autonomía estimada de inventario: {cobertura_dias if cobertura_dias is not None else '>30'} días."
                )

        # 8. Construcción de serie temporal para gráficos comparativos
        serie_temporal: List[DailyTrendPoint] = []
        # Históricos reales (últimos 14 días)
        for fecha_k in sorted(daily_sales_map.keys()):
            try:
                dt_obj = datetime.strptime(fecha_k, "%Y-%m-%d")
                dia_etiqueta = dt_obj.strftime("%d/%m")
            except Exception:
                dia_etiqueta = fecha_k[-5:]
            serie_temporal.append(
                DailyTrendPoint(
                    fecha=fecha_k,
                    dia_etiqueta=dia_etiqueta,
                    tipo="REAL",
                    unidades=daily_sales_map[fecha_k],
                )
            )

        # Proyección futura (próximos horizonte_dias)
        # Distribuir demanda_estimada a lo largo del horizonte
        base_diaria = unidades_diarias_prom
        for d in range(1, payload.horizonte_dias + 1):
            future_dt = now + timedelta(days=d)
            f_str = future_dt.strftime("%Y-%m-%d")
            dia_etiqueta = future_dt.strftime("%d/%m")
            # Pequeña modulación de fin de semana para realismo
            is_weekend = future_dt.weekday() in (5, 6)
            modulador = 1.15 if is_weekend else 0.94
            unidades_dia = round(base_diaria * modulador, 2)
            serie_temporal.append(
                DailyTrendPoint(
                    fecha=f_str,
                    dia_etiqueta=dia_etiqueta,
                    tipo="PROYECTADO",
                    unidades=unidades_dia,
                )
            )

        # Contexto histórico
        historico = HistoricalContext(
            ventas_ultimos_7d=ventas_7d,
            ventas_ultimos_14d=ventas_14d,
            ventas_ultimos_30d=ventas_30d,
            stock_actual=stock_actual,
            stock_minimo=stock_minimo,
            precio_unitario=precio_unitario,
            seccion=product.seccion,
            datos_suficientes=datos_suficientes,
            mensaje_suficiencia=mensaje_suficiencia,
        )

        resultado = PredictionResult(
            demanda_estimada=demanda_estimada,
            demanda_estimada_raw=round(pred_raw, 2),
            rango_minimo=rango_min,
            rango_maximo=rango_max,
            unidades_diarias_promedio=unidades_diarias_prom,
            cobertura_stock_dias=cobertura_dias,
            riesgo_desabastecimiento=riesgo_desabastecimiento,
            nivel_riesgo=nivel_riesgo,
            confianza_estimacion=confianza,
            explicacion=explicacion,
        )

        return PredictionResponse(
            success=True,
            id_producto=product.id_producto,
            producto_nombre=product.nombre,
            id_sucursal=branch.id_sucursal,
            sucursal_nombre=branch.nombre,
            horizonte_dias=payload.horizonte_dias,
            prediccion=resultado,
            historico=historico,
            serie_temporal=serie_temporal,
            modelo=cls.get_model_info(),
            disclaimer=(
                "Estimación experimental generada mediante GradientBoostingRegressor (scikit-learn) "
                "a partir de variables de ventas históricas, stock y precio. Destinada a soporte de decisiones operativas."
            ),
        )
