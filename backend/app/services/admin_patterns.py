"""Servicio de análisis de patrones no supervisado con K-Means (CU23)."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.pattern_analyzer import (
    PATTERN_METADATA_PATH,
    run_unsupervised_pattern_analysis,
    train_reference_pattern_model,
)
from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.schemas.admin_patterns import (
    ClusterAverages,
    PatternAnalysisRequest,
    PatternAnalysisResponse,
    PatternFilterOption,
    PatternFiltersResponse,
    PatternModelInfoResponse,
    PatternModelMetrics,
    PatternSegment,
    ProductPatternItem,
)

logger = logging.getLogger(__name__)


class AdminPatternsService:
    """Orquestación del análisis no supervisado de patrones comerciales y rotación."""

    @staticmethod
    def get_model_info() -> PatternModelInfoResponse:
        """Devuelve los metadatos y métricas del modelo referencial K-Means."""
        if not PATTERN_METADATA_PATH.exists():
            meta = train_reference_pattern_model()
        else:
            with open(PATTERN_METADATA_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)

        metricas = meta.get("metricas", {})
        return PatternModelInfoResponse(
            algoritmo=meta.get("algoritmo", "K-Means Clustering (scikit-learn compatible)"),
            tipo_aprendizaje="No supervisado",
            descripcion=meta.get(
                "descripcion",
                "Segmentación de productos según velocidad de rotación, volumen, margen y nivel de stock",
            ),
            variables=meta.get("variables", []),
            n_clusters=meta.get("n_clusters", 4),
            metricas=PatternModelMetrics(
                silhouette_score=float(metricas.get("silhouette_score", 0.55)),
                inercia=float(metricas.get("inercia", 800.0)),
            ),
            es_experimental=meta.get("es_experimental", True),
            nota_metodologica=meta.get(
                "nota_metodologica",
                "Modelo referencial entrenado sobre datos sintéticos de FashionStore.",
            ),
        )

    @staticmethod
    def get_filters(db: Session, empresa_id: int) -> PatternFiltersResponse:
        """Devuelve las sucursales y categorías activas de la empresa para filtrar el análisis."""
        sucursales = [
            PatternFilterOption(id=b.id_sucursal, nombre=b.nombre, extra=b.direccion)
            for b in db.execute(
                select(Branch)
                .where(Branch.empresa_id == empresa_id, Branch.estado == True)  # noqa: E712
                .order_by(Branch.nombre.asc())
            ).scalars().all()
        ]

        categorias = [
            PatternFilterOption(id=c.id_categoria, nombre=c.nombre)
            for c in db.execute(
                select(Category)
                .where(Category.empresa_id == empresa_id, Category.estado == True)  # noqa: E712
                .order_by(Category.nombre.asc())
            ).scalars().all()
        ]

        return PatternFiltersResponse(
            sucursales=sucursales,
            categorias=categorias,
            periodos_sugeridos_dias=[30, 60, 90, 180],
        )

    @classmethod
    def analyze_patterns(
        cls,
        db: Session,
        empresa_id: int,
        payload: PatternAnalysisRequest,
    ) -> PatternAnalysisResponse:
        """Extrae métricas comerciales reales de PostgreSQL y aplica clustering K-Means."""
        now = datetime.now()

        # 1. Determinar ventana de tiempo
        if payload.fecha_desde and payload.fecha_hasta:
            try:
                dt_desde = datetime.strptime(payload.fecha_desde[:10], "%Y-%m-%d")
                dt_hasta = datetime.strptime(payload.fecha_hasta[:10], "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Formato de fecha inválido. Utilice AAAA-MM-DD.",
                )
        else:
            dias = payload.dias_periodo or 30
            dt_hasta = now
            dt_desde = now - timedelta(days=dias)

        filtros_dict: Dict[str, Any] = {
            "periodo": f"{dt_desde.strftime('%Y-%m-%d')} a {dt_hasta.strftime('%Y-%m-%d')}",
            "dias_periodo": (dt_hasta - dt_desde).days,
            "sucursal": "Todas",
            "categoria": "Todas",
        }

        # 2. Validar sucursal si se especifica
        if payload.id_sucursal is not None:
            branch = db.execute(
                select(Branch).where(
                    Branch.id_sucursal == payload.id_sucursal,
                    Branch.empresa_id == empresa_id,
                )
            ).scalar_one_or_none()
            if not branch:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="La sucursal seleccionada no existe o no pertenece a la empresa.",
                )
            filtros_dict["sucursal"] = branch.nombre

        # 3. Validar categoría si se especifica
        if payload.id_categoria is not None:
            cat = db.execute(
                select(Category).where(
                    Category.id_categoria == payload.id_categoria,
                    Category.empresa_id == empresa_id,
                )
            ).scalar_one_or_none()
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="La categoría seleccionada no existe o no pertenece a la empresa.",
                )
            filtros_dict["categoria"] = cat.nombre

        # 4. Obtener productos activos de la empresa
        prod_stmt = select(Product, Category.nombre.label("cat_nombre")).outerjoin(
            Category, Product.id_categoria == Category.id_categoria
        ).where(
            Product.empresa_id == empresa_id,
            Product.estado == True,  # noqa: E712
        )
        if payload.id_categoria is not None:
            prod_stmt = prod_stmt.where(Product.id_categoria == payload.id_categoria)

        products_rows = db.execute(prod_stmt.order_by(Product.nombre.asc())).all()

        # 5. Para cada producto, extraer stock real y ventas en el período
        products_payload: List[Dict[str, Any]] = []

        total_unidades = 0
        total_ingresos = 0.0

        for prod, cat_nombre in products_rows:
            # Obtener variantes del producto
            variant_ids = db.execute(
                select(ProductVariant.id_variante_producto).where(
                    ProductVariant.id_producto == prod.id_producto,
                    ProductVariant.empresa_id == empresa_id,
                )
            ).scalars().all()

            stock_total = 0
            if variant_ids:
                inv_stmt = select(
                    func.coalesce(func.sum(BranchInventory.stock_actual), 0)
                ).where(
                    BranchInventory.id_variante_producto.in_(variant_ids),
                    BranchInventory.empresa_id == empresa_id,
                )
                if payload.id_sucursal is not None:
                    inv_stmt = inv_stmt.where(BranchInventory.id_sucursal == payload.id_sucursal)

                stock_total = int(db.execute(inv_stmt).scalar() or 0)

            unidades_prod = 0
            ingresos_prod = 0.0
            dias_con_ventas = 0

            if variant_ids:
                sales_stmt = select(
                    func.coalesce(func.sum(SaleDetail.cantidad), 0),
                    func.coalesce(func.sum(SaleDetail.subtotal_linea), 0),
                    func.count(func.distinct(func.date(Sale.fecha_venta))),
                ).join(
                    Sale, SaleDetail.id_venta == Sale.id_venta
                ).where(
                    Sale.empresa_id == empresa_id,
                    Sale.estado == "COMPLETADA",
                    Sale.fecha_venta >= dt_desde,
                    Sale.fecha_venta <= dt_hasta,
                    SaleDetail.id_variante_producto.in_(variant_ids),
                    SaleDetail.empresa_id == empresa_id,
                )
                if payload.id_sucursal is not None:
                    sales_stmt = sales_stmt.where(Sale.id_sucursal == payload.id_sucursal)

                s_row = db.execute(sales_stmt).one()
                unidades_prod = int(s_row[0] or 0)
                ingresos_prod = float(s_row[1] or 0.0)
                dias_con_ventas = int(s_row[2] or 0)

            total_unidades += unidades_prod
            total_ingresos += ingresos_prod

            # Ratio de rotación = unidades / (unidades + stock)
            denom = unidades_prod + stock_total
            rotacion = round(unidades_prod / denom, 3) if denom > 0 else 0.0

            products_payload.append({
                "id_producto": prod.id_producto,
                "nombre": prod.nombre,
                "categoria_nombre": cat_nombre or "Sin categoría",
                "seccion": prod.seccion,
                "precio_unitario": float(prod.precio),
                "unidades_vendidas": unidades_prod,
                "ingresos_totales": round(ingresos_prod, 2),
                "frecuencia_ventas": dias_con_ventas,
                "stock_actual": stock_total,
                "ratio_rotacion": rotacion,
            })

        # 6. Ejecutar análisis no supervisado K-Means
        ml_result = run_unsupervised_pattern_analysis(products_payload)

        # 7. Construir respuesta estructurada
        segmentos_response: List[PatternSegment] = []
        for s in ml_result.get("segmentos", []):
            p = s["promedios"]
            segmentos_response.append(
                PatternSegment(
                    id_cluster=s["id_cluster"],
                    nombre=s["nombre"],
                    descripcion=s["descripcion"],
                    estrategia=s["estrategia"],
                    color=s["color"],
                    badge_class=s["badge_class"],
                    total_productos=s["total_productos"],
                    porcentaje_catalogo=s["porcentaje_catalogo"],
                    promedios=ClusterAverages(
                        unidades_vendidas=p["unidades_vendidas"],
                        ingresos_totales=p["ingresos_totales"],
                        frecuencia_ventas=p["frecuencia_ventas"],
                        precio_unitario=p["precio_unitario"],
                        stock_actual=p["stock_actual"],
                        ratio_rotacion=p["ratio_rotacion"],
                    ),
                )
            )

        productos_response: List[ProductPatternItem] = [
            ProductPatternItem(
                id_producto=p["id_producto"],
                nombre=p["nombre"],
                categoria_nombre=p["categoria_nombre"],
                seccion=p["seccion"],
                precio_unitario=p["precio_unitario"],
                unidades_vendidas=p["unidades_vendidas"],
                ingresos_totales=p["ingresos_totales"],
                frecuencia_ventas=p["frecuencia_ventas"],
                stock_actual=p["stock_actual"],
                ratio_rotacion=p["ratio_rotacion"],
                id_cluster=p.get("id_cluster", 0),
                cluster_nombre=p.get("cluster_nombre", "Sin Clasificar"),
                cluster_color=p.get("cluster_color", "#64748b"),
                cluster_badge=p.get("cluster_badge", "badge-default"),
            )
            for p in ml_result.get("productos_clasificados", [])
        ]

        metricas_res = ml_result.get("metricas", {})

        return PatternAnalysisResponse(
            success=True,
            datos_suficientes=ml_result["datos_suficientes"],
            mensaje=ml_result["mensaje"],
            filtros_aplicados=filtros_dict,
            total_productos_analizados=len(products_payload),
            total_unidades_vendidas=total_unidades,
            total_ingresos_facturados=round(total_ingresos, 2),
            n_clusters=ml_result.get("n_clusters", 0),
            calidad_agrupamiento=ml_result.get("calidad_agrupamiento", "MODERADA"),
            metricas=PatternModelMetrics(
                silhouette_score=metricas_res.get("silhouette_score", 0.0),
                inercia=metricas_res.get("inercia", 0.0),
            ),
            segmentos=segmentos_response,
            productos=productos_response,
            modelo_referencial=cls.get_model_info(),
            disclaimer=(
                "Patrones descubiertos mediante K-Means no supervisado a partir de ventas reales e inventario de FashionStore. "
                "Las etiquetas y estrategias de cada grupo se asignan automáticamente según las características relativas de los centroides."
            ),
        )

