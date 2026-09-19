"""CU26: recomendador hibrido ligero. Solo lectura, sin IA externa ni modelos.

El puntaje combina afinidad derivada del comportamiento real del cliente
(compras, reservas y carrito) con senales generales del catalogo (popularidad
reciente, promocion vigente y novedad). No entrena nada, no guarda estado y se
resuelve en memoria sobre un pool acotado de candidatos.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping

from sqlalchemy.orm import Session

from app.repositories.client_recommendations import (
    SIGNAL_ABANDONED_CART,
    SIGNAL_CART,
    SIGNAL_PURCHASE,
    SIGNAL_RESERVATION,
    ClientRecommendationsRepository,
)
from app.schemas.client_recommendations import (
    RecommendationItemData,
    RecommendationPromotionData,
    RecommendationVariantData,
)
from app.services.catalog import CatalogService


MONEY = Decimal("0.01")

# Peso por fuente: la compra pesa mas que la reserva, y la reserva mas que el
# carrito. El carrito abandonado es la senal mas debil.
SOURCE_WEIGHTS = {
    SIGNAL_PURCHASE: 5.0,
    SIGNAL_RESERVATION: 3.0,
    SIGNAL_CART: 1.5,
    SIGNAL_ABANDONED_CART: 0.6,
}

# Decaimiento temporal por antiguedad de la senal, en dias.
DECAY_STEPS = ((30, 1.0), (90, 0.7), (180, 0.45))
DECAY_FLOOR = 0.25

# Una compra masiva de la misma prenda no debe dominar el perfil.
MAX_UNITS_PER_SIGNAL = 5

SIGNAL_LOOKBACK_DAYS = 365
POPULARITY_LOOKBACK_DAYS = 90
NOVELTY_WINDOW_DAYS = 180

# Pesos del puntaje personalizado (suman 1.0).
W_CATEGORIA = 0.28
W_TALLA = 0.12
W_COLOR = 0.08
W_SECCION = 0.08
W_TEMPORADA = 0.08
W_RELACIONADO = 0.06
W_POPULARIDAD = 0.20
W_PROMOCION = 0.06
W_NOVEDAD = 0.04

# Pesos del fallback para cliente sin historial (suman 1.0).
F_POPULARIDAD = 0.45
F_PROMOCION = 0.25
F_VIGENCIA = 0.20
F_NOVEDAD = 0.10

CANDIDATE_POOL_MULTIPLIER = 16
CANDIDATE_POOL_MIN = 60
CANDIDATE_POOL_MAX = 200
SHORTLIST_MULTIPLIER = 4
SHORTLIST_MIN = 24

MOTIVO_POR_ORIGEN = {
    SIGNAL_PURCHASE: "Basado en tus compras",
    SIGNAL_RESERVATION: "Porque reservaste prendas similares",
    SIGNAL_CART: "Por lo que tienes en tu carrito",
    SIGNAL_ABANDONED_CART: "Retomando lo que dejaste en el carrito",
}
MOTIVOS = {
    "talla": "Disponible en tu talla habitual",
    "color": "En tu color favorito",
    "seccion": "Acorde a tu estilo habitual",
    "temporada": "De la temporada que prefieres",
    "relacionado": "Similar a prendas que ya elegiste",
    "popularidad": "Popular entre clientes similares",
    "promocion": "En promocion vigente",
    "novedad": "Novedad del catalogo",
    "vigencia": "De la temporada y coleccion actual",
}
MOTIVO_POR_DEFECTO = "Disponible para ti ahora"

SHORT_DESCRIPTION_LENGTH = CatalogService.SHORT_DESCRIPTION_LENGTH


class RecommendationAccessError(Exception):
    """La cuenta autenticada no tiene un perfil CLIENTE asociado."""


@dataclass
class AffinityProfile:
    """Preferencias derivadas del comportamiento, ya normalizadas a 0..1."""

    categorias: dict[int, float] = field(default_factory=dict)
    tallas: dict[int, float] = field(default_factory=dict)
    colores: dict[int, float] = field(default_factory=dict)
    secciones: dict[str, float] = field(default_factory=dict)
    temporadas: dict[int, float] = field(default_factory=dict)
    # "Productos relacionados": afinidad al par (categoria, seccion) con el que
    # el cliente ya interactuo, mas estricta que la categoria por si sola.
    pares: dict[tuple[int, str], float] = field(default_factory=dict)
    origen_por_categoria: dict[int, str] = field(default_factory=dict)
    comprados: set[int] = field(default_factory=set)

    @property
    def vacio(self) -> bool:
        return not (
            self.categorias
            or self.tallas
            or self.colores
            or self.secciones
            or self.temporadas
        )


def _normalize(values: dict) -> dict:
    """Escala a 0..1 contra el maximo del propio cliente."""
    top = max(values.values(), default=0.0)
    if top <= 0:
        return {}
    return {key: value / top for key, value in values.items()}


class ClientRecommendationsService:
    """Genera recomendaciones con pocas consultas por lote y cero escrituras."""

    def __init__(self, db: Session) -> None:
        self.repository = ClientRecommendationsRepository(db)
        # Reutiliza la validacion de sucursal/ciudad publicada por CU12.
        self.catalog_service = CatalogService(db)

    # --------------------------------------------------------------- orquestacion

    def recommend(
        self,
        user_id: int,
        *,
        limit: int = 12,
        branch_id: int | None = None,
        city_id: int | None = None,
        now: datetime | None = None,
    ) -> tuple[list[RecommendationItemData], str]:
        self.catalog_service._validate_location(
            branch_id=branch_id, city_id=city_id
        )
        client = self.repository.get_client_by_user(user_id)
        if client is None:
            raise RecommendationAccessError(
                "La cuenta no tiene un perfil CLIENTE asociado"
            )

        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        profile = self._build_profile(client.id_cliente, now=now)
        popularity = self._popularity(now=now)
        promotions = self._promotions_by_product(now=now)

        candidates = self.repository.list_candidates(
            category_ids=tuple(profile.categorias),
            season_ids=tuple(profile.temporadas),
            promoted_ids=tuple(promotions),
            popular_ids=tuple(popularity),
            branch_id=branch_id,
            city_id=city_id,
            today=now.date(),
            limit=self._pool_size(limit),
        )
        origen = "FALLBACK" if profile.vacio else "PERSONALIZADO"
        if not candidates:
            return [], origen

        # Fase 1: puntaje sin variantes para recortar el pool.
        scored = [
            (row, *self._score_product(row, profile, popularity, promotions, now))
            for row in candidates
        ]
        scored.sort(key=lambda item: (-item[1], item[0]["id_producto"]))
        shortlist = scored[: max(SHORTLIST_MIN, limit * SHORTLIST_MULTIPLIER)]

        # Fase 2: un lote de variantes y otro de imagenes para el recorte.
        product_ids = [row["id_producto"] for row, _, _ in shortlist]
        variants = self._group_variants(
            self.repository.list_available_variants(
                product_ids, branch_id=branch_id, city_id=city_id
            )
        )
        images = self._principal_images(product_ids)

        items = []
        for row, base_score, terms in shortlist:
            product_variants = variants.get(row["id_producto"], [])
            if not product_variants:
                # El EXISTS del pool ya exige stock; esto solo cubre carreras.
                continue
            items.append(
                self._to_item(
                    row,
                    profile=profile,
                    base_score=base_score,
                    base_terms=terms,
                    variants=product_variants,
                    promotions=promotions.get(row["id_producto"]),
                    image=images.get(row["id_producto"]),
                )
            )

        # Lo ya comprado queda al final: se evita "cuando sea posible", pero no
        # se sacrifica el limite solicitado.
        items.sort(
            key=lambda item: (
                item.ya_comprado,
                -item.score,
                item.id_producto,
            )
        )
        return items[:limit], origen

    @staticmethod
    def _pool_size(limit: int) -> int:
        return min(
            CANDIDATE_POOL_MAX,
            max(CANDIDATE_POOL_MIN, limit * CANDIDATE_POOL_MULTIPLIER),
        )

    # --------------------------------------------------------------------- perfil

    @staticmethod
    def _decay(age_days: float) -> float:
        for threshold, factor in DECAY_STEPS:
            if age_days <= threshold:
                return factor
        return DECAY_FLOOR

    def _build_profile(self, client_id: int, *, now: datetime) -> AffinityProfile:
        since = now - timedelta(days=SIGNAL_LOOKBACK_DAYS)
        rows = self.repository.list_affinity_signals(client_id, since=since)

        categorias: dict[int, float] = {}
        tallas: dict[int, float] = {}
        colores: dict[int, float] = {}
        secciones: dict[str, float] = {}
        temporadas: dict[int, float] = {}
        pares: dict[tuple[int, str], float] = {}
        origen_peso: dict[int, dict[str, float]] = {}
        comprados: set[int] = set()

        for row in rows:
            origen = row["origen"]
            base = SOURCE_WEIGHTS.get(origen)
            if base is None:
                continue
            fecha = row["fecha"]
            age_days = (now - fecha).total_seconds() / 86400 if fecha else 0.0
            units = min(int(row["cantidad"] or 1), MAX_UNITS_PER_SIGNAL)
            weight = base * units * self._decay(max(age_days, 0.0))

            categoria = row["id_categoria"]
            categorias[categoria] = categorias.get(categoria, 0.0) + weight
            origen_peso.setdefault(categoria, {})
            origen_peso[categoria][origen] = (
                origen_peso[categoria].get(origen, 0.0) + weight
            )
            tallas[row["id_talla"]] = tallas.get(row["id_talla"], 0.0) + weight
            colores[row["id_color"]] = colores.get(row["id_color"], 0.0) + weight
            secciones[row["seccion"]] = secciones.get(row["seccion"], 0.0) + weight
            if row["id_temporada"] is not None:
                temporadas[row["id_temporada"]] = (
                    temporadas.get(row["id_temporada"], 0.0) + weight
                )
            par = (categoria, row["seccion"])
            pares[par] = pares.get(par, 0.0) + weight
            if origen == SIGNAL_PURCHASE:
                comprados.add(row["id_producto"])

        return AffinityProfile(
            categorias=_normalize(categorias),
            tallas=_normalize(tallas),
            colores=_normalize(colores),
            secciones=_normalize(secciones),
            temporadas=_normalize(temporadas),
            pares=_normalize(pares),
            origen_por_categoria={
                categoria: max(pesos.items(), key=lambda pair: pair[1])[0]
                for categoria, pesos in origen_peso.items()
            },
            comprados=comprados,
        )

    # ------------------------------------------------------- senales generales

    def _popularity(self, *, now: datetime) -> dict[int, float]:
        since = now - timedelta(days=POPULARITY_LOOKBACK_DAYS)
        rows = self.repository.list_recent_popularity(since=since)
        units = {row["id_producto"]: float(row["unidades"] or 0) for row in rows}
        return _normalize(units)

    def _promotions_by_product(
        self, *, now: datetime
    ) -> dict[int, list[Mapping]]:
        """Todas las promociones vigentes agrupadas por producto."""
        grouped: dict[int, list[Mapping]] = {}
        for row in self.repository.list_current_promotions(now=now):
            grouped.setdefault(row["id_producto"], []).append(row)
        return grouped

    def _best_promotion(
        self, price: Decimal, promotions: list[Mapping] | None
    ) -> Mapping | None:
        """La que deja el precio final mas bajo.

        Hay que comparar contra el precio real: un 10% y un monto fijo de Bs 20
        no son comparables por su valor nominal.
        """
        if not promotions:
            return None
        return min(
            promotions,
            key=lambda promotion: (
                self._apply_promotion(price, promotion),
                promotion["id_promocion"],
            ),
        )

    @staticmethod
    def _apply_promotion(price: Decimal, promotion: Mapping | None) -> Decimal:
        if promotion is None:
            return price
        value = Decimal(promotion["valor"])
        if promotion["tipo_descuento"] == "PORCENTAJE":
            final = price - (price * value / Decimal("100"))
        else:
            final = price - value
        return max(final, Decimal("0")).quantize(MONEY, rounding=ROUND_HALF_UP)

    # -------------------------------------------------------------------- puntaje

    def _novelty(self, created_at, now: datetime) -> float:
        if created_at is None:
            return 0.0
        age_days = (now - created_at).total_seconds() / 86400
        return max(0.0, 1.0 - max(age_days, 0.0) / NOVELTY_WINDOW_DAYS)

    def _score_product(
        self,
        row: Mapping,
        profile: AffinityProfile,
        popularity: dict[int, float],
        promotions: dict[int, list[Mapping]],
        now: datetime,
    ) -> tuple[float, dict[str, float]]:
        """Puntaje sin talla/color; la fase 2 agrega el termino de variante."""
        product = row["id_producto"]
        popular = popularity.get(product, 0.0)
        promoted = 1.0 if product in promotions else 0.0
        novelty = self._novelty(row["created_at"], now)
        vigencia = 1.0 if (
            bool(row["temporada_vigente"]) or bool(row["coleccion_activa"])
        ) else 0.0

        if profile.vacio:
            terms = {
                "popularidad": F_POPULARIDAD * popular,
                "promocion": F_PROMOCION * promoted,
                "vigencia": F_VIGENCIA * vigencia,
                "novedad": F_NOVEDAD * novelty,
            }
            return sum(terms.values()), terms

        temporada = row["id_temporada"]
        terms = {
            "categoria": W_CATEGORIA
            * profile.categorias.get(row["id_categoria"], 0.0),
            "seccion": W_SECCION * profile.secciones.get(row["seccion"], 0.0),
            "temporada": W_TEMPORADA
            * (profile.temporadas.get(temporada, 0.0) if temporada else 0.0),
            "relacionado": W_RELACIONADO
            * profile.pares.get((row["id_categoria"], row["seccion"]), 0.0),
            "popularidad": W_POPULARIDAD * popular,
            "promocion": W_PROMOCION * promoted,
            "novedad": W_NOVEDAD * novelty,
        }
        return sum(terms.values()), terms

    def _variant_terms(
        self, profile: AffinityProfile, variants: list[Mapping]
    ) -> tuple[Mapping, dict[str, float]]:
        """Elige la variante sugerida y puntua talla/color habituales."""
        best_variant = variants[0]
        best_key = (-1.0, -1.0, 0)
        for variant in variants:
            size = profile.tallas.get(variant["id_talla"], 0.0)
            color = profile.colores.get(variant["id_color"], 0.0)
            key = (size + color, float(variant["stock_disponible"] or 0),
                   -variant["id_variante_producto"])
            if key > best_key:
                best_key = key
                best_variant = variant
        if profile.vacio:
            return best_variant, {}
        return best_variant, {
            "talla": W_TALLA * profile.tallas.get(best_variant["id_talla"], 0.0),
            "color": W_COLOR * profile.colores.get(best_variant["id_color"], 0.0),
        }

    def _motivo(
        self, terms: dict[str, float], row: Mapping, profile: AffinityProfile
    ) -> str:
        positive = {key: value for key, value in terms.items() if value > 0}
        if not positive:
            return MOTIVO_POR_DEFECTO
        dominant = max(positive.items(), key=lambda pair: pair[1])[0]
        if dominant == "categoria":
            origen = profile.origen_por_categoria.get(row["id_categoria"])
            return MOTIVO_POR_ORIGEN.get(origen, MOTIVO_POR_DEFECTO)
        return MOTIVOS.get(dominant, MOTIVO_POR_DEFECTO)

    # ----------------------------------------------------------------- respuesta

    @staticmethod
    def _group_variants(rows) -> dict[int, list[Mapping]]:
        grouped: dict[int, list[Mapping]] = {}
        for row in rows:
            grouped.setdefault(row["id_producto"], []).append(row)
        return grouped

    def _principal_images(self, product_ids) -> dict[int, str]:
        images: dict[int, str] = {}
        for row in self.repository.list_principal_images(product_ids):
            # La consulta ya ordena es_principal DESC: la primera es la buena.
            images.setdefault(row["id_producto"], row["url_imagen"])
        return images

    @staticmethod
    def _short_description(description: str | None) -> str | None:
        if description is None:
            return None
        text = description.strip()
        if len(text) <= SHORT_DESCRIPTION_LENGTH:
            return text
        return f"{text[:SHORT_DESCRIPTION_LENGTH].rstrip()}..."

    def _to_item(
        self,
        row: Mapping,
        *,
        profile: AffinityProfile,
        base_score: float,
        base_terms: dict[str, float],
        variants: list[Mapping],
        promotions: list[Mapping] | None,
        image: str | None,
    ) -> RecommendationItemData:
        variant, variant_terms = self._variant_terms(profile, variants)
        terms = {**base_terms, **variant_terms}
        score = base_score + sum(variant_terms.values())

        price = Decimal(row["precio_base"]).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        promotion = self._best_promotion(price, promotions)
        final_price = self._apply_promotion(price, promotion)
        discount = price - final_price
        percentage = (
            (discount * Decimal("100") / price).quantize(
                MONEY, rounding=ROUND_HALF_UP
            )
            if promotion is not None and price > 0
            else None
        )

        return RecommendationItemData(
            id_producto=row["id_producto"],
            nombre=row["nombre"],
            descripcion_corta=self._short_description(row["descripcion"]),
            seccion=row["seccion"],
            id_categoria=row["id_categoria"],
            categoria=row["categoria"],
            id_temporada=row["id_temporada"],
            temporada=row["temporada"],
            precio_base=price,
            precio_final=final_price,
            tiene_promocion=promotion is not None,
            promocion=(
                RecommendationPromotionData(
                    id_promocion=promotion["id_promocion"],
                    nombre=promotion["promocion_nombre"],
                    codigo=promotion["codigo"],
                    descripcion=promotion["descripcion"],
                    tipo_descuento=promotion["tipo_descuento"],
                    valor=Decimal(promotion["valor"]),
                    fecha_inicio=promotion["fecha_inicio"],
                    fecha_fin=promotion["fecha_fin"],
                    acumulable=bool(promotion["acumulable"]),
                )
                if promotion is not None
                else None
            ),
            monto_descuento=discount if promotion is not None else None,
            porcentaje_descuento=percentage,
            imagen_principal=image,
            variante_sugerida=RecommendationVariantData(
                id_variante_producto=variant["id_variante_producto"],
                sku=variant["sku"],
                id_talla=variant["id_talla"],
                talla=variant["talla"],
                id_color=variant["id_color"],
                color=variant["color"],
                codigo_hex=variant["codigo_hex"],
                stock_disponible=int(variant["stock_disponible"] or 0),
            ),
            score=round(score, 4),
            motivo=self._motivo(terms, row, profile),
            ya_comprado=row["id_producto"] in profile.comprados,
        )
