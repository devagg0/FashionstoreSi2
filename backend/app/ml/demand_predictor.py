"""Pipeline de Machine Learning para predicción de demanda de prendas (CU22).

Modelo supervisado de regresión (GradientBoostingRegressor) entrenado con datos sintéticos
reproducibles de retail de moda. Cumple con la separación estricta Train/Test sin fuga de datos.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "demand_predictor.joblib"
METADATA_PATH = ARTIFACTS_DIR / "demand_metadata.json"

FEATURE_NAMES = [
    "precio_unitario",
    "ventas_ultimos_7d",
    "ventas_ultimos_14d",
    "ventas_ultimos_30d",
    "stock_actual",
    "dias_horizonte",
    "mes",
    "es_temporada_alta",
    "seccion_HOMBRE",
    "seccion_MUJER",
    "seccion_UNISEX",
]


class FashionFeatureScaler:
    """Escalador estandarizado (Z-score) para variables numéricas evitando fuga de datos."""

    def __init__(self) -> None:
        self.means: np.ndarray | None = None
        self.stds: np.ndarray | None = None

    def fit(self, X_num: np.ndarray) -> "FashionFeatureScaler":
        self.means = np.mean(X_num, axis=0)
        self.stds = np.std(X_num, axis=0)
        self.stds[self.stds == 0.0] = 1.0
        return self

    def transform(self, X_num: np.ndarray) -> np.ndarray:
        if self.means is None or self.stds is None:
            raise ValueError("El escalador no ha sido entrenado.")
        return (X_num - self.means) / self.stds


def encode_section(seccion: str) -> list[float]:
    """One-hot encoding determinista para la sección de la prenda."""
    s = str(seccion).strip().upper()
    return [
        1.0 if s == "HOMBRE" else 0.0,
        1.0 if s == "MUJER" else 0.0,
        1.0 if s == "UNISEX" else 0.0,
    ]


def generate_synthetic_fashion_dataset(n_samples: int = 3000, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Genera un dataset sintético reproducible que modela la dinámica comercial de FashionStore.

    Variables modeladas:
    - Precios de prendas (40.0 a 350.0 BOB)
    - Ventas acumuladas 7d, 14d y 30d
    - Stock actual en tienda
    - Horizontes de proyección: 7, 15 y 30 días
    - Estacionalidad comercial (meses 1, 5, 11 y 12 como temporada alta)
    - Sección: HOMBRE, MUJER, UNISEX
    """
    rng = np.random.default_rng(seed)

    precios = rng.uniform(40.0, 320.0, n_samples)
    v7 = rng.poisson(lam=7.0, size=n_samples)
    v14 = v7 + rng.poisson(lam=6.5, size=n_samples)
    v30 = v14 + rng.poisson(lam=13.0, size=n_samples)
    stock = rng.integers(0, 130, size=n_samples)
    horizontes = rng.choice([7, 15, 30], size=n_samples, p=[0.40, 0.35, 0.25])
    meses = rng.integers(1, 13, size=n_samples)
    temporadas_altas = np.isin(meses, [1, 5, 11, 12]).astype(float)
    secciones = rng.choice(["HOMBRE", "MUJER", "UNISEX"], size=n_samples, p=[0.42, 0.46, 0.12])

    seccion_factors = np.array([1.15 if s == "MUJER" else (1.0 if s == "HOMBRE" else 0.90) for s in secciones])
    season_factors = np.where(temporadas_altas == 1.0, 1.25, 0.95)
    price_factors = np.clip(1.0 - 0.0014 * (precios - 110.0), 0.65, 1.35)

    # Velocidad diaria histórica
    daily_velocity = 0.50 * (v7 / 7.0) + 0.30 * (v14 / 14.0) + 0.20 * (v30 / 30.0)

    # Demanda teórica esperada
    expected = daily_velocity * horizontes * price_factors * season_factors * seccion_factors
    noise = rng.normal(0.0, 1.2 + 0.04 * expected, size=n_samples)
    demanda = np.clip(np.round(expected + noise), 0.0, None)

    # Matriz X
    X_rows = []
    for i in range(n_samples):
        num_vals = [
            precios[i],
            float(v7[i]),
            float(v14[i]),
            float(v30[i]),
            float(stock[i]),
            float(horizontes[i]),
            float(meses[i]),
            temporadas_altas[i],
        ]
        cat_vals = encode_section(secciones[i])
        X_rows.append(num_vals + cat_vals)

    return np.array(X_rows, dtype=float), demanda


def train_demand_model(n_samples: int = 3000, seed: int = 42) -> dict[str, Any]:
    """Entrena y evalúa el modelo supervisado de regresión evitando fuga de datos."""
    X, y = generate_synthetic_fashion_dataset(n_samples=n_samples, seed=seed)

    # División estricta Train / Test (80% / 20%) sin fuga de datos
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=seed
    )

    # Escalador entrenado EXCLUSIVAMENTE sobre X_train (primeras 8 columnas numéricas)
    scaler = FashionFeatureScaler()
    scaler.fit(X_train[:, :8])

    X_train_num_scaled = scaler.transform(X_train[:, :8])
    X_train_processed = np.hstack([X_train_num_scaled, X_train[:, 8:]])

    X_test_num_scaled = scaler.transform(X_test[:, :8])
    X_test_processed = np.hstack([X_test_num_scaled, X_test[:, 8:]])

    # Regresor no lineal supervisado
    model = GradientBoostingRegressor(
        n_estimators=110,
        learning_rate=0.08,
        max_depth=4,
        random_state=seed,
    )
    model.fit(X_train_processed, y_train)

    # Evaluación objetiva en test set
    y_pred = model.predict(X_test_processed)
    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(root_mean_squared_error(y_test, y_pred))
    r2 = float(r2_score(y_test, y_pred))

    # Persistencia segura de artefactos
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": model,
        "scaler": scaler,
        "feature_names": FEATURE_NAMES,
    }
    joblib.dump(bundle, MODEL_PATH)

    metadata = {
        "algoritmo": "GradientBoostingRegressor (scikit-learn)",
        "descripcion": "Modelo supervisado de regresión para estimar demanda de prendas en sucursales",
        "variables": FEATURE_NAMES,
        "total_variables": len(FEATURE_NAMES),
        "dataset_size": n_samples,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "metricas": {
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "r2": round(r2, 4),
        },
        "es_experimental": True,
        "nota_metodologica": "Entrenado sobre datos sintéticos generados para FashionStore. Las predicciones son estimaciones orientativas.",
        "entrenado_en": datetime.now(timezone.utc).isoformat(),
    }

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return metadata


class DemandPredictor:
    """Singleton para inferencia segura y de bajo overhead."""

    _instance: "DemandPredictor | None" = None
    _bundle: dict[str, Any] | None = None
    _metadata: dict[str, Any] | None = None

    @classmethod
    def get_instance(cls) -> "DemandPredictor":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_or_train()
        return cls._instance

    def _load_or_train(self) -> None:
        if not MODEL_PATH.exists() or not METADATA_PATH.exists():
            train_demand_model()

        self._bundle = joblib.load(MODEL_PATH)
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            self._metadata = json.load(f)

    @property
    def metadata(self) -> dict[str, Any]:
        if self._metadata is None:
            self._load_or_train()
        return self._metadata or {}

    def get_metadata(self) -> dict[str, Any]:
        return self.metadata

    def predict(
        self,
        precio_unitario: float,
        ventas_ultimos_7d: int,
        ventas_ultimos_14d: int,
        ventas_ultimos_30d: int,
        stock_actual: int,
        dias_horizonte: int,
        mes: int,
        es_temporada_alta: int,
        seccion: str,
    ) -> float:
        if self._bundle is None:
            self._load_or_train()

        model = self._bundle["model"]
        scaler: FashionFeatureScaler = self._bundle["scaler"]

        num_features = np.array(
            [[
                float(precio_unitario),
                float(ventas_ultimos_7d),
                float(ventas_ultimos_14d),
                float(ventas_ultimos_30d),
                float(stock_actual),
                float(dias_horizonte),
                float(mes),
                float(es_temporada_alta),
            ]],
            dtype=float,
        )

        num_scaled = scaler.transform(num_features)
        cat_features = np.array([encode_section(seccion)], dtype=float)
        X_input = np.hstack([num_scaled, cat_features])

        pred = model.predict(X_input)[0]
        return float(max(0.0, pred))
