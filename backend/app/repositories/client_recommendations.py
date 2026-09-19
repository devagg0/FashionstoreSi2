"""CU26: lecturas agregadas del recomendador. Solo SELECT, sin bloqueos ni DDL.

Todas las consultas son por lote y acotadas: ninguna se ejecuta por producto.
Se evita `greatest()` y la aritmetica de fechas en SQL para que las mismas
sentencias corran en PostgreSQL y en el SQLite de las pruebas; el descuento y el
decaimiento temporal se resuelven en el servicio.
"""

from datetime import date, datetime

from sqlalchemy import and_, case, exists, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.cart import Cart
from app.models.cart_detail import CartDetail
from app.models.category import Category
from app.models.collection import Collection
from app.models.color import Color
from app.models.product import Product
from app.models.product_collection import ProductCollection
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.promotion import Promotion
from app.models.promotion_product import PromotionProduct
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.season import Season
from app.models.size import Size
from app.repositories.catalog import CatalogRepository
from app.repositories.client_reservations import ClientReservationRepository


SIGNAL_PURCHASE = "COMPRA"
SIGNAL_RESERVATION = "RESERVA"
SIGNAL_CART = "CARRITO"
SIGNAL_ABANDONED_CART = "CARRITO_ABANDONADO"

RESERVATION_SIGNAL_STATES = ("ATENDIDA", "CONFIRMADA")

SIGNAL_ROW_LIMIT = 400
POPULARITY_LIMIT = 120
PROMOTION_LIMIT = 500


class ClientRecommendationsRepository:
    """Agrupa las consultas de CU26 reutilizando el catalogo publico de CU12."""

    def __init__(self, db: Session) -> None:
        self.db = db
        # Reutiliza la resolucion canonica id_usuario -> t_cliente de CU17 sin
        # heredar sus metodos de escritura ni de bloqueo.
        self._clients = ClientReservationRepository(db)

    def get_client_by_user(self, user_id: int):
        return self._clients.get_client_by_user(user_id)

    # ------------------------------------------------------------------ señales

    @staticmethod
    def _signal_sources(client_id: int, since: datetime):
        """Una rama por fuente de comportamiento, con su etiqueta de origen."""
        purchases = (
            select(
                SaleDetail.id_variante_producto.label("id_variante_producto"),
                SaleDetail.cantidad.label("cantidad"),
                Sale.fecha_venta.label("fecha"),
                literal(SIGNAL_PURCHASE).label("origen"),
            )
            .join(Sale, Sale.id_venta == SaleDetail.id_venta)
            .where(
                Sale.id_cliente == client_id,
                Sale.estado == "COMPLETADA",
                Sale.fecha_venta >= since,
            )
        )
        reservations = (
            select(
                ReservationDetail.id_variante_producto,
                ReservationDetail.cantidad,
                Reservation.created_at,
                literal(SIGNAL_RESERVATION),
            )
            .join(
                Reservation,
                Reservation.id_reserva == ReservationDetail.id_reserva,
            )
            .where(
                Reservation.id_cliente == client_id,
                Reservation.estado.in_(RESERVATION_SIGNAL_STATES),
                Reservation.created_at >= since,
            )
        )
        active_cart = (
            select(
                CartDetail.id_variante_producto,
                CartDetail.cantidad,
                Cart.updated_at,
                literal(SIGNAL_CART),
            )
            .join(Cart, Cart.id_carrito == CartDetail.id_carrito)
            .where(Cart.id_cliente == client_id, Cart.estado == "ACTIVO")
        )
        abandoned_cart = (
            select(
                CartDetail.id_variante_producto,
                CartDetail.cantidad,
                Cart.updated_at,
                literal(SIGNAL_ABANDONED_CART),
            )
            .join(Cart, Cart.id_carrito == CartDetail.id_carrito)
            .where(
                Cart.id_cliente == client_id,
                Cart.estado == "ABANDONADO",
                Cart.updated_at >= since,
            )
        )
        return purchases, reservations, active_cart, abandoned_cart

    def list_affinity_signals(
        self, client_id: int, *, since: datetime, limit: int = SIGNAL_ROW_LIMIT
    ):
        """Comportamiento del cliente ya proyectado sobre atributos de prenda.

        No filtra producto/variante activos: una prenda descatalogada sigue
        revelando la preferencia de categoria, talla y color del cliente.
        """
        signals = union_all(
            *self._signal_sources(client_id, since)
        ).subquery("senales")
        statement = (
            select(
                signals.c.origen,
                signals.c.fecha,
                func.sum(signals.c.cantidad).label("cantidad"),
                Product.id_producto,
                Product.id_categoria,
                Product.seccion,
                Product.id_temporada,
                ProductVariant.id_talla,
                ProductVariant.id_color,
            )
            .select_from(signals)
            .join(
                ProductVariant,
                ProductVariant.id_variante_producto
                == signals.c.id_variante_producto,
            )
            .join(Product, Product.id_producto == ProductVariant.id_producto)
            .group_by(
                signals.c.origen,
                signals.c.fecha,
                Product.id_producto,
                Product.id_categoria,
                Product.seccion,
                Product.id_temporada,
                ProductVariant.id_talla,
                ProductVariant.id_color,
            )
            .order_by(signals.c.fecha.desc(), Product.id_producto)
            .limit(limit)
        )
        return self.db.execute(statement).mappings().all()

    # ------------------------------------------------- señales generales / pool

    def list_recent_popularity(
        self, *, since: datetime, limit: int = POPULARITY_LIMIT
    ):
        """Unidades vendidas por producto en ventas COMPLETADAS recientes."""
        units = func.sum(SaleDetail.cantidad).label("unidades")
        return self.db.execute(
            select(ProductVariant.id_producto.label("id_producto"), units)
            .select_from(SaleDetail)
            .join(Sale, Sale.id_venta == SaleDetail.id_venta)
            .join(
                ProductVariant,
                ProductVariant.id_variante_producto
                == SaleDetail.id_variante_producto,
            )
            .where(
                Sale.estado == "COMPLETADA",
                Sale.fecha_venta >= since,
            )
            .group_by(ProductVariant.id_producto)
            .order_by(units.desc(), ProductVariant.id_producto)
            .limit(limit)
        ).mappings().all()

    def list_current_promotions(
        self, *, now: datetime, limit: int = PROMOTION_LIMIT
    ):
        """Promociones vigentes por producto; el servicio elige la mejor."""
        return self.db.execute(
            select(
                PromotionProduct.id_producto,
                Promotion.id_promocion,
                Promotion.nombre.label("promocion_nombre"),
                Promotion.codigo,
                Promotion.descripcion,
                Promotion.tipo_descuento,
                Promotion.valor,
                Promotion.fecha_inicio,
                Promotion.fecha_fin,
                Promotion.acumulable,
            )
            .join(
                Promotion,
                Promotion.id_promocion == PromotionProduct.id_promocion,
            )
            .where(
                Promotion.estado.is_(True),
                Promotion.fecha_inicio <= now,
                Promotion.fecha_fin >= now,
            )
            .order_by(PromotionProduct.id_producto, Promotion.id_promocion)
            .limit(limit)
        ).mappings().all()

    @staticmethod
    def _available_variant(*, branch_id: int | None, city_id: int | None):
        """EXISTS de variante activa con stock disponible."""
        if branch_id is not None or city_id is not None:
            # CU12 ya resuelve variante activa + stock por sucursal/ciudad.
            return CatalogRepository._matching_variant(
                size_id=None,
                color_id=None,
                branch_id=branch_id,
                city_id=city_id,
            )
        return exists(
            select(1)
            .select_from(ProductVariant)
            .join(
                BranchInventory,
                BranchInventory.id_variante_producto
                == ProductVariant.id_variante_producto,
            )
            .join(Branch, Branch.id_sucursal == BranchInventory.id_sucursal)
            .where(
                ProductVariant.id_producto == Product.id_producto,
                ProductVariant.estado.is_(True),
                Branch.estado.is_(True),
                BranchInventory.stock_actual
                - BranchInventory.stock_reservado
                > 0,
            )
        )

    @staticmethod
    def _active_collection():
        return exists(
            select(1)
            .select_from(ProductCollection)
            .join(
                Collection,
                Collection.id_coleccion == ProductCollection.id_coleccion,
            )
            .where(
                ProductCollection.id_producto == Product.id_producto,
                Collection.estado.is_(True),
            )
        )

    @staticmethod
    def _current_season(today: date):
        return and_(
            Season.estado.is_(True),
            or_(Season.fecha_inicio.is_(None), Season.fecha_inicio <= today),
            or_(Season.fecha_fin.is_(None), Season.fecha_fin >= today),
        )

    @staticmethod
    def _priority_flag(column, values):
        """1 cuando la fila pertenece al conjunto afin, 0 en caso contrario."""
        if not values:
            return literal(0)
        return case((column.in_(list(values)), 1), else_=0)

    def list_candidates(
        self,
        *,
        category_ids=(),
        season_ids=(),
        promoted_ids=(),
        popular_ids=(),
        branch_id: int | None,
        city_id: int | None,
        today: date,
        limit: int,
    ):
        """Pool acotado de productos publicables y con stock real.

        El ORDER BY prioriza afinidad, promocion y popularidad para que el LIMIT
        no descarte candidatos relevantes; el puntaje fino se calcula despues.
        """
        priority = (
            self._priority_flag(Product.id_categoria, category_ids)
            + self._priority_flag(Product.id_temporada, season_ids)
            + self._priority_flag(Product.id_producto, promoted_ids)
            + self._priority_flag(Product.id_producto, popular_ids)
        )
        return self.db.execute(
            select(
                Product.id_producto,
                Product.nombre,
                Product.descripcion,
                Product.seccion,
                Product.id_categoria,
                Category.nombre.label("categoria"),
                Product.id_temporada,
                Season.nombre.label("temporada"),
                Product.precio.label("precio_base"),
                Product.created_at,
                self._active_collection().label("coleccion_activa"),
                self._current_season(today).label("temporada_vigente"),
            )
            .join(Category, Category.id_categoria == Product.id_categoria)
            .outerjoin(Season, Season.id_temporada == Product.id_temporada)
            .where(
                # Misma visibilidad que el catalogo de CU12: manda Product.estado.
                Product.estado.is_(True),
                self._available_variant(branch_id=branch_id, city_id=city_id),
            )
            .order_by(
                priority.desc(),
                Product.created_at.desc(),
                Product.id_producto.desc(),
            )
            .limit(limit)
        ).mappings().all()

    # ------------------------------------------------ enriquecido del top final

    def list_available_variants(
        self,
        product_ids,
        *,
        branch_id: int | None,
        city_id: int | None,
    ):
        """Variantes activas con stock agregado, en una sola consulta por lote."""
        if not product_ids:
            return []
        available = func.sum(
            BranchInventory.stock_actual - BranchInventory.stock_reservado
        ).label("stock_disponible")
        conditions = [
            ProductVariant.id_producto.in_(list(product_ids)),
            ProductVariant.estado.is_(True),
            Branch.estado.is_(True),
        ]
        if branch_id is not None:
            conditions.append(Branch.id_sucursal == branch_id)
        elif city_id is not None:
            conditions.append(Branch.id_ciudad == city_id)
        return self.db.execute(
            select(
                ProductVariant.id_producto,
                ProductVariant.id_variante_producto,
                ProductVariant.sku,
                Size.id_talla,
                Size.nombre.label("talla"),
                Color.id_color,
                Color.nombre.label("color"),
                Color.codigo_hex,
                available,
            )
            .select_from(ProductVariant)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .join(
                BranchInventory,
                BranchInventory.id_variante_producto
                == ProductVariant.id_variante_producto,
            )
            .join(Branch, Branch.id_sucursal == BranchInventory.id_sucursal)
            .where(*conditions)
            .group_by(
                ProductVariant.id_producto,
                ProductVariant.id_variante_producto,
                ProductVariant.sku,
                Size.id_talla,
                Size.nombre,
                Color.id_color,
                Color.nombre,
                Color.codigo_hex,
            )
            .having(
                func.sum(
                    BranchInventory.stock_actual
                    - BranchInventory.stock_reservado
                )
                > 0
            )
            .order_by(
                ProductVariant.id_producto,
                ProductVariant.id_variante_producto,
            )
        ).mappings().all()

    def list_principal_images(self, product_ids):
        """Imagenes del top final en lote; el servicio toma la principal."""
        if not product_ids:
            return []
        return self.db.execute(
            select(
                ProductImage.id_producto,
                ProductImage.url_imagen,
                ProductImage.es_principal,
            )
            .where(ProductImage.id_producto.in_(list(product_ids)))
            .order_by(
                ProductImage.id_producto,
                ProductImage.es_principal.desc(),
                ProductImage.id_imagen_producto,
            )
        ).mappings().all()
