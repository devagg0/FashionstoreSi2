"""Módulo de Machine Learning para el CU23: Análisis de Patrones de Comportamiento y Rotación.

Implementa aprendizaje no supervisado mediante K-Means (scikit-learn compatible)
evaluado con Silhouette Score, sin dependencias de DLLs bloqueadas por Windows WDAC.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from scipy.cluster.vq import kmeans2
from scipy.spatial.distance import cdist
from sklearn.metrics import silhouette_score

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
PATTERN_MODEL_PATH = ARTIFACTS_DIR / "pattern_kmeans.joblib"
PATTERN_METADATA_PATH = ARTIFACTS_DIR / "pattern_metadata.json"

FEATURE_NAMES = [
    "unidades_vendidas",
    "ingresos_totales",
    "frecuencia_ventas",
    "precio_unitario",
    "stock_actual",
    "ratio_rotacion",
]


class PatternFeatureScaler:
    """Escalador Z-score para normalizar las 6 variables de comportamiento comercial."""

    def __init__(self) -> None:
        self.means: np.ndarray | None = None
        self.stds: np.ndarray | None = None

    def fit(self, X: np.ndarray) -> "PatternFeatureScaler":
        self.means = np.mean(X, axis=0)
        self.stds = np.std(X, axis=0)
        # Prevenir divisiones por cero si una variable es constante
        self.stds[self.stds == 0.0] = 1.0
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self.means is None or self.stds is None:
            raise ValueError("El escalador no ha sido ajustado.")
        return (X - self.means) / self.stds

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)


class FashionKMeans:
    """Implementación K-Means++ compatible con scikit-learn basada en NumPy/SciPy.

    Garantiza reproducibilidad, cálculo de inercia y compatibilidad total con Silhouette Score.
    """

    def __init__(self, n_clusters: int = 4, random_state: int = 42, max_iter: int = 40) -> None:
        self.n_clusters = n_clusters
        self.random_state = random_state
        self.max_iter = max_iter
        self.cluster_centers_: np.ndarray | None = None
        self.labels_: np.ndarray | None = None
        self.inertia_: float = 0.0

    def fit(self, X: np.ndarray) -> "FashionKMeans":
        np.random.seed(self.random_state)
        n_samples = X.shape[0]

        if n_samples < self.n_clusters:
            raise ValueError(f"n_samples={n_samples} debe ser >= n_clusters={self.n_clusters}")

        # Ejecución de K-Means con inicialización K-Means++
        centroids, labels = kmeans2(
            X,
            k=self.n_clusters,
            iter=self.max_iter,
            minit="++",
            missing="warn",
        )

        self.cluster_centers_ = centroids
        self.labels_ = labels

        # Inercia: suma de distancias euclidianas al cuadrado al centroide más cercano
        sq_distances = cdist(X, centroids, metric="sqeuclidean")
        self.inertia_ = float(np.sum(sq_distances.min(axis=1)))

        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.cluster_centers_ is None:
            raise ValueError("El modelo no ha sido entrenado.")
        distances = cdist(X, self.cluster_centers_, metric="sqeuclidean")
        return distances.argmin(axis=1)

    def fit_predict(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).labels_  # type: ignore


def generate_synthetic_pattern_dataset(n_samples: int = 800, seed: int = 42) -> np.ndarray:
    """Genera datos sintéticos reproducibles que modelan los 4 arquetipos comerciales de FashionStore.

    Arquetipos:
    1. Alta Rotación / Estrella: alto volumen, altos ingresos, alta rotación.
    2. Margen Alto / Selecto: precio elevado, volumen moderado, buen ingreso unitario.
    3. Flujo Rápido / Básico: precio bajo/medio, alta rotación, volumen constante.
    4. Baja Rotación / Hueso: stock estancado, ventas mínimas o nulas.
    """
    rng = np.random.RandomState(seed)
    n_per_cluster = n_samples // 4

    # 1. Estrella
    unidades_c1 = rng.uniform(60, 160, size=n_per_cluster)
    precio_c1 = rng.uniform(90, 160, size=n_per_cluster)
    ingresos_c1 = unidades_c1 * precio_c1 * rng.uniform(0.92, 1.0, size=n_per_cluster)
    frec_c1 = rng.uniform(16, 28, size=n_per_cluster)
    stock_c1 = rng.uniform(20, 50, size=n_per_cluster)
    rot_c1 = unidades_c1 / (unidades_c1 + stock_c1)

    # 2. Premium / Margen Alto
    unidades_c2 = rng.uniform(15, 38, size=n_per_cluster)
    precio_c2 = rng.uniform(220, 420, size=n_per_cluster)
    ingresos_c2 = unidades_c2 * precio_c2 * rng.uniform(0.94, 1.0, size=n_per_cluster)
    frec_c2 = rng.uniform(8, 18, size=n_per_cluster)
    stock_c2 = rng.uniform(12, 28, size=n_per_cluster)
    rot_c2 = unidades_c2 / (unidades_c2 + stock_c2)

    # 3. Básicos / Flujo
    unidades_c3 = rng.uniform(45, 110, size=n_per_cluster)
    precio_c3 = rng.uniform(40, 75, size=n_per_cluster)
    ingresos_c3 = unidades_c3 * precio_c3 * rng.uniform(0.90, 1.0, size=n_per_cluster)
    frec_c3 = rng.uniform(14, 25, size=n_per_cluster)
    stock_c3 = rng.uniform(35, 75, size=n_per_cluster)
    rot_c3 = unidades_c3 / (unidades_c3 + stock_c3)

    # 4. Baja Rotación / Hueso
    unidades_c4 = rng.uniform(0, 8, size=n_per_cluster)
    precio_c4 = rng.uniform(70, 190, size=n_per_cluster)
    ingresos_c4 = unidades_c4 * precio_c4
    frec_c4 = rng.uniform(0, 5, size=n_per_cluster)
    stock_c4 = rng.uniform(25, 70, size=n_per_cluster)
    rot_c4 = unidades_c4 / (unidades_c4 + stock_c4 + 1e-6)

    # Concatenar
    unidades = np.concatenate([unidades_c1, unidades_c2, unidades_c3, unidades_c4])
    ingresos = np.concatenate([ingresos_c1, ingresos_c2, ingresos_c3, ingresos_c4])
    frecuencia = np.concatenate([frec_c1, frec_c2, frec_c3, frec_c4])
    precio = np.concatenate([precio_c1, precio_c2, precio_c3, precio_c4])
    stock = np.concatenate([stock_c1, stock_c2, stock_c3, stock_c4])
    rotacion = np.concatenate([rot_c1, rot_c2, rot_c3, rot_c4])

    X = np.column_stack([unidades, ingresos, frecuencia, precio, stock, rotacion])
    return X


def train_reference_pattern_model(n_samples: int = 800, seed: int = 42) -> dict[str, Any]:
    """Entrena y persiste el modelo K-Means referencial con Silhouette Score."""
    X = generate_synthetic_pattern_dataset(n_samples=n_samples, seed=seed)

    scaler = PatternFeatureScaler().fit(X)
    X_scaled = scaler.transform(X)

    kmeans = FashionKMeans(n_clusters=4, random_state=seed)
    kmeans.fit(X_scaled)

    # Evaluación mediante Silhouette Score
    score_silhouette = float(silhouette_score(X_scaled, kmeans.labels_))

    metadata = {
        "algoritmo": "K-Means Clustering (scikit-learn compatible)",
        "tipo_aprendizaje": "No supervisado",
        "descripcion": "Segmentación de productos según velocidad de rotación, volumen, margen y nivel de stock",
        "n_clusters": 4,
        "variables": FEATURE_NAMES,
        "dataset_sintetico_tamano": n_samples,
        "metricas": {
            "silhouette_score": round(score_silhouette, 4),
            "inercia": round(kmeans.inertia_, 2),
        },
        "es_experimental": True,
        "nota_metodologica": (
            "Modelo referencial entrenado sobre datos sintéticos de FashionStore. "
            "El análisis administrativo aplica este mismo pipeline directamente sobre datos reales de PostgreSQL."
        ),
    }

    bundle = {
        "model": kmeans,
        "scaler": scaler,
        "metadata": metadata,
    }

    joblib.dump(bundle, PATTERN_MODEL_PATH)
    with open(PATTERN_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return metadata


@dataclass
class ClusterProfile:
    """Perfil comercial justificado empíricamente a partir de los centroides."""
    cluster_id: int
    nombre: str
    descripcion: str
    estrategia: str
    color: str
    badge_class: str
    unidades_promedio: float
    ingresos_promedio: float
    frecuencia_promedio: float
    precio_promedio: float
    stock_promedio: float
    rotacion_promedio: float
    total_productos: int
    porcentaje_catalogo: float


def characterize_clusters(
    X_raw: np.ndarray,
    labels: np.ndarray,
    k: int,
) -> list[ClusterProfile]:
    """Asigna nombres y estrategias comerciales a cada cluster basándose estrictamente en sus valores medios.

    Evita asignaciones arbitrarias comparando el rendimiento relativo de los centroides.
    """
    profiles: list[ClusterProfile] = []
    n_total = len(labels)

    # 1. Calcular medias por cluster
    cluster_stats = []
    for c_id in range(k):
        mask = labels == c_id
        if np.sum(mask) == 0:
            continue
        X_c = X_raw[mask]
        mean_vals = np.mean(X_c, axis=0)
        count = int(np.sum(mask))
        cluster_stats.append({
            "c_id": c_id,
            "count": count,
            "pct": round((count / n_total) * 100, 1),
            "unidades": float(mean_vals[0]),
            "ingresos": float(mean_vals[1]),
            "frecuencia": float(mean_vals[2]),
            "precio": float(mean_vals[3]),
            "stock": float(mean_vals[4]),
            "rotacion": float(mean_vals[5]),
        })

    if not cluster_stats:
        return []

    # 2. Ordenar para identificar arquetipos:
    # Máximo volumen/ingreso -> Estrella
    # Máximo precio unitario (si no es ya Estrella) -> Premium
    # Mínima rotación y ventas -> Baja Rotación / Lento
    # Restante -> Rotación Regular / Flujo
    assigned_ids = set()

    # Identificar Estrella (mayor producto unidades * ingresos)
    sorted_by_revenue = sorted(cluster_stats, key=lambda x: x["ingresos"], reverse=True)
    c_star = sorted_by_revenue[0]
    assigned_ids.add(c_star["c_id"])

    # Identificar Baja Rotación (menor unidades vendidas)
    sorted_by_units = sorted([c for c in cluster_stats if c["c_id"] not in assigned_ids], key=lambda x: x["unidades"])
    c_slow = sorted_by_units[0] if sorted_by_units else None
    if c_slow:
        assigned_ids.add(c_slow["c_id"])

    # Identificar Premium (mayor precio unitario entre los restantes)
    remaining = [c for c in cluster_stats if c["c_id"] not in assigned_ids]
    sorted_by_price = sorted(remaining, key=lambda x: x["precio"], reverse=True)
    c_premium = sorted_by_price[0] if sorted_by_price else None
    if c_premium:
        assigned_ids.add(c_premium["c_id"])

    # Restante -> Básicos / Flujo Regular
    c_regular = [c for c in cluster_stats if c["c_id"] not in assigned_ids]

    for stat in cluster_stats:
        cid = stat["c_id"]
        if cid == c_star["c_id"]:
            nombre = "Alto Rendimiento (Estrella)"
            descripcion = "Prendas con alto volumen de ventas, rotación continua y gran aporte a la facturación total."
            estrategia = "Garantizar disponibilidad permanente en inventario y ubicación prioritaria en tienda."
            color = "#2563eb"
            badge = "badge-star"
        elif c_premium and cid == c_premium["c_id"]:
            nombre = "Margen Alto (Selecto / Premium)"
            descripcion = "Prendas de mayor precio unitario con rotación moderada y margen significativo por venta."
            estrategia = "Atención personalizada, escaparates destacados y reposiciones en lotes selectos."
            color = "#7c3aed"
            badge = "badge-premium"
        elif c_slow and cid == c_slow["c_id"]:
            nombre = "Baja Rotación (Lento Movimiento)"
            descripcion = "Prendas con rotación reducida o nula en el período analizado y acumulación de stock."
            estrategia = "Estrategias de liquidación, promociones cruzadas y ajuste de compras futuras."
            color = "#dc2626"
            badge = "badge-slow"
        else:
            nombre = "Rotación Regular (Básicos de Flujo)"
            descripcion = "Prendas de venta estable y precio accesible que impulsan el tráfico constante de clientes."
            estrategia = "Reposición balanceada periódica y empaquetado promocional con complementos."
            color = "#059669"
            badge = "badge-regular"

        profiles.append(
            ClusterProfile(
                cluster_id=cid,
                nombre=nombre,
                descripcion=descripcion,
                estrategia=estrategia,
                color=color,
                badge_class=badge,
                unidades_promedio=round(stat["unidades"], 1),
                ingresos_promedio=round(stat["ingresos"], 2),
                frecuencia_promedio=round(stat["frecuencia"], 1),
                precio_promedio=round(stat["precio"], 2),
                stock_promedio=round(stat["stock"], 1),
                rotacion_promedio=round(stat["rotacion"], 3),
                total_productos=stat["count"],
                porcentaje_catalogo=stat["pct"],
            )
        )

    # Ordenar por porcentaje de catálogo descendente
    profiles.sort(key=lambda p: p.total_productos, reverse=True)
    return profiles


def run_unsupervised_pattern_analysis(
    product_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ejecuta el pipeline no supervisado K-Means sobre la lista de productos reales de la empresa."""
    n_products = len(product_data)

    if n_products < 4:
        return {
            "datos_suficientes": False,
            "mensaje": (
                f"Se identificaron únicamente {n_products} prendas con registros. "
                "Se requiere un mínimo de 4 productos con inventario o ventas para estructurar agrupaciones válidas."
            ),
            "total_productos": n_products,
            "segmentos": [],
            "productos_clasificados": product_data,
            "metricas": {"silhouette_score": 0.0, "inercia": 0.0},
        }

    # Extraer matriz de variables
    X_raw = np.array(
        [
            [
                float(p.get("unidades_vendidas", 0)),
                float(p.get("ingresos_totales", 0.0)),
                float(p.get("frecuencia_ventas", 0)),
                float(p.get("precio_unitario", 0.0)),
                float(p.get("stock_actual", 0)),
                float(p.get("ratio_rotacion", 0.0)),
            ]
            for p in product_data
        ],
        dtype=float,
    )

    # Preprocesamiento y escalado Z-score
    scaler = PatternFeatureScaler().fit(X_raw)
    X_scaled = scaler.transform(X_raw)

    # Determinar k óptimo respetando el tamaño de muestra
    k = 4 if n_products >= 6 else 3
    k = min(k, n_products - 1)
    k = max(2, k)

    kmeans = FashionKMeans(n_clusters=k, random_state=42)
    labels = kmeans.fit_predict(X_scaled)

    # Evaluación mediante Silhouette Score
    try:
        if len(np.unique(labels)) > 1 and n_products > k:
            s_score = float(silhouette_score(X_scaled, labels))
        else:
            s_score = 0.0
    except Exception:
        s_score = 0.0

    # Perfiles comerciales empíricos
    profiles = characterize_clusters(X_raw, labels, k)
    profile_by_id = {p.cluster_id: p for p in profiles}

    # Enriquecer cada producto con su cluster asignado
    classified_products = []
    for idx, p in enumerate(product_data):
        c_id = int(labels[idx])
        prof = profile_by_id.get(c_id)
        enriched = dict(p)
        enriched["id_cluster"] = c_id
        enriched["cluster_nombre"] = prof.nombre if prof else f"Grupo {c_id}"
        enriched["cluster_color"] = prof.color if prof else "#64748b"
        enriched["cluster_badge"] = prof.badge_class if prof else "badge-default"
        classified_products.append(enriched)

    calidad = "ALTA" if s_score >= 0.45 else ("BUENA" if s_score >= 0.25 else "MODERADA")

    return {
        "datos_suficientes": True,
        "mensaje": f"Análisis de patrones completado exitosamente sobre {n_products} prendas comerciales.",
        "total_productos": n_products,
        "n_clusters": k,
        "calidad_agrupamiento": calidad,
        "metricas": {
            "silhouette_score": round(s_score, 4),
            "inercia": round(kmeans.inertia_, 2),
        },
        "segmentos": [
            {
                "id_cluster": p.cluster_id,
                "nombre": p.nombre,
                "descripcion": p.descripcion,
                "estrategia": p.estrategia,
                "color": p.color,
                "badge_class": p.badge_class,
                "total_productos": p.total_productos,
                "porcentaje_catalogo": p.porcentaje_catalogo,
                "promedios": {
                    "unidades_vendidas": p.unidades_promedio,
                    "ingresos_totales": p.ingresos_promedio,
                    "frecuencia_ventas": p.frecuencia_promedio,
                    "precio_unitario": p.precio_promedio,
                    "stock_actual": p.stock_promedio,
                    "ratio_rotacion": p.rotacion_promedio,
                },
            }
            for p in profiles
        ],
        "productos_clasificados": classified_products,
    }

