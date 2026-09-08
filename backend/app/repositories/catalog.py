"""Consultas de solo lectura para el catalogo publico de CU12."""

from decimal import Decimal

from sqlalchemy import Numeric, Select, case, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.branch_inventory import BranchInventory
from app.models.category import Category
from app.models.city import City
from app.models.collection import Collection
from app.models.color import Color
from app.models.product import Product
from app.models.product_collection import ProductCollection
from app.models.product_image import ProductImage
from app.models.product_variant import ProductVariant
from app.models.promotion import Promotion
from app.models.promotion_product import PromotionProduct
from app.models.season import Season
from app.models.size import Size
from app.schemas.catalog import CatalogSort


class CatalogRepository:
    """Centraliza joins y filtros del catalogo sin mutar sus tablas."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _escaped_pattern(search: str) -> str:
        escaped = (
            search.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        return f"%{escaped}%"

    @staticmethod
    def _promotion_candidates():
        percentage_price = Product.precio - (
            Product.precio * Promotion.valor / Decimal("100")
        )
        discounted_price = cast(
            case(
                (
                    Promotion.tipo_descuento == "PORCENTAJE",
                    func.greatest(percentage_price, Decimal("0")),
                ),
                else_=func.greatest(
                    Product.precio - Promotion.valor, Decimal("0")
                ),
            ),
            Numeric(12, 2),
        )
        return (
            select(
                PromotionProduct.id_producto.label("id_producto"),
                Promotion.id_promocion.label("id_promocion"),
                Promotion.nombre.label("promocion_nombre"),
                Promotion.codigo.label("promocion_codigo"),
                Promotion.descripcion.label("promocion_descripcion"),
                Promotion.tipo_descuento.label("tipo_descuento"),
                Promotion.valor.label("valor_descuento"),
                Promotion.fecha_inicio.label("fecha_inicio"),
                Promotion.fecha_fin.label("fecha_fin"),
                Promotion.acumulable.label("acumulable"),
                discounted_price.label("precio_resultante"),
                func.row_number()
                .over(
                    partition_by=PromotionProduct.id_producto,
                    order_by=(discounted_price, Promotion.id_promocion),
                )
                .label("orden_precio"),
            )
            .join(
                Promotion,
                Promotion.id_promocion == PromotionProduct.id_promocion,
            )
            .join(Product, Product.id_producto == PromotionProduct.id_producto)
            .where(
                Promotion.estado.is_(True),
                Promotion.fecha_inicio <= func.now(),
                Promotion.fecha_fin >= func.now(),
            )
            .subquery("promociones_candidatas")
        )

    @classmethod
    def _best_promotion(cls):
        candidates = cls._promotion_candidates()
        return (
            select(*[candidates.c[name] for name in candidates.c.keys()])
            .where(candidates.c.orden_precio == 1)
            .subquery("mejor_promocion")
        )

    @staticmethod
    def _principal_image():
        return (
            select(ProductImage.url_imagen)
            .where(ProductImage.id_producto == Product.id_producto)
            .order_by(
                ProductImage.es_principal.desc(),
                ProductImage.id_imagen_producto,
            )
            .limit(1)
            .correlate(Product)
            .scalar_subquery()
        )

    @staticmethod
    def _matching_variant(
        *,
        size_id: int | None,
        color_id: int | None,
        branch_id: int | None,
        city_id: int | None,
    ):
        variant_match = select(1).select_from(ProductVariant)
        if branch_id is not None or city_id is not None:
            variant_match = variant_match.join(
                BranchInventory,
                BranchInventory.id_variante_producto
                == ProductVariant.id_variante_producto,
            ).join(Branch, Branch.id_sucursal == BranchInventory.id_sucursal)
        conditions = [
            ProductVariant.id_producto == Product.id_producto,
            ProductVariant.estado.is_(True),
        ]
        if size_id is not None:
            conditions.append(ProductVariant.id_talla == size_id)
        if color_id is not None:
            conditions.append(ProductVariant.id_color == color_id)
        if branch_id is not None:
            conditions.extend(
                [
                    BranchInventory.id_sucursal == branch_id,
                    BranchInventory.stock_actual
                    - BranchInventory.stock_reservado
                    > 0,
                ]
            )
        elif city_id is not None:
            conditions.extend(
                [
                    Branch.id_ciudad == city_id,
                    Branch.estado.is_(True),
                    BranchInventory.stock_actual
                    - BranchInventory.stock_reservado
                    > 0,
                ]
            )
        return exists(variant_match.where(*conditions))

    @classmethod
    def _apply_filters(
        cls,
        statement: Select,
        *,
        best_promotion,
        search: str | None,
        section: str | None,
        category_id: int | None,
        size_id: int | None,
        color_id: int | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        on_promotion: bool | None,
        branch_id: int | None,
        city_id: int | None,
    ) -> Select:
        final_price = func.coalesce(
            best_promotion.c.precio_resultante, Product.precio
        )
        statement = statement.where(Product.estado.is_(True))
        if search and search.strip():
            pattern = cls._escaped_pattern(search)
            statement = statement.where(
                or_(
                    Product.nombre.ilike(pattern, escape="\\"),
                    exists(
                        select(1).where(
                            ProductVariant.id_producto == Product.id_producto,
                            ProductVariant.estado.is_(True),
                            ProductVariant.sku.ilike(pattern, escape="\\"),
                        )
                    ),
                )
            )
        if section is not None:
            statement = statement.where(Product.seccion == section)
        if category_id is not None:
            statement = statement.where(Product.id_categoria == category_id)
        if any(
            value is not None
            for value in (size_id, color_id, branch_id, city_id)
        ):
            statement = statement.where(
                cls._matching_variant(
                    size_id=size_id,
                    color_id=color_id,
                    branch_id=branch_id,
                    city_id=city_id,
                )
            )
        if min_price is not None:
            statement = statement.where(final_price >= min_price)
        if max_price is not None:
            statement = statement.where(final_price <= max_price)
        if on_promotion is True:
            statement = statement.where(best_promotion.c.id_promocion.is_not(None))
        elif on_promotion is False:
            statement = statement.where(best_promotion.c.id_promocion.is_(None))
        return statement

    @staticmethod
    def _order_by(statement: Select, *, sort: CatalogSort, final_price):
        if sort == "precio_asc":
            return statement.order_by(final_price.asc(), Product.id_producto.asc())
        if sort == "precio_desc":
            return statement.order_by(final_price.desc(), Product.id_producto.asc())
        if sort == "nombre":
            return statement.order_by(Product.nombre.asc(), Product.id_producto.asc())
        return statement.order_by(Product.created_at.desc(), Product.id_producto.desc())

    def list_products(
        self,
        *,
        search: str | None,
        section: str | None,
        category_id: int | None,
        size_id: int | None,
        color_id: int | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        on_promotion: bool | None,
        branch_id: int | None,
        city_id: int | None,
        sort: CatalogSort,
        page: int,
        page_size: int,
    ):
        best = self._best_promotion()
        final_price = func.coalesce(best.c.precio_resultante, Product.precio)
        base = (
            select(
                Product.id_producto,
                Product.nombre,
                Product.descripcion,
                Product.seccion,
                Product.id_categoria,
                Category.nombre.label("categoria"),
                Product.precio.label("precio_base"),
                final_price.label("precio_final"),
                best.c.precio_resultante.label("precio_resultante"),
                self._principal_image().label("imagen_principal"),
                best.c.id_promocion,
                best.c.promocion_nombre,
                best.c.promocion_codigo,
                best.c.promocion_descripcion,
                best.c.tipo_descuento,
                best.c.valor_descuento,
                best.c.fecha_inicio,
                best.c.fecha_fin,
                best.c.acumulable,
            )
            .join(Category, Category.id_categoria == Product.id_categoria)
            .outerjoin(best, best.c.id_producto == Product.id_producto)
        )
        count = (
            select(func.count(Product.id_producto))
            .outerjoin(best, best.c.id_producto == Product.id_producto)
        )
        filters = dict(
            best_promotion=best,
            search=search,
            section=section,
            category_id=category_id,
            size_id=size_id,
            color_id=color_id,
            min_price=min_price,
            max_price=max_price,
            on_promotion=on_promotion,
            branch_id=branch_id,
            city_id=city_id,
        )
        base = self._apply_filters(base, **filters)
        count = self._apply_filters(count, **filters)
        rows = self.db.execute(
            self._order_by(base, sort=sort, final_price=final_price)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).mappings().all()
        total = self.db.scalar(count) or 0
        return rows, total

    def get_active_product(self, product_id: int):
        best = self._best_promotion()
        final_price = func.coalesce(best.c.precio_resultante, Product.precio)
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
                final_price.label("precio_final"),
                self._principal_image().label("imagen_principal"),
                best.c.id_promocion,
            )
            .join(Category, Category.id_categoria == Product.id_categoria)
            .outerjoin(Season, Season.id_temporada == Product.id_temporada)
            .outerjoin(best, best.c.id_producto == Product.id_producto)
            .where(
                Product.id_producto == product_id,
                Product.estado.is_(True),
            )
        ).mappings().one_or_none()

    def list_active_variants(
        self, product_ids: list[int], *, branch_id: int | None
    ):
        if not product_ids:
            return []
        columns = [
            ProductVariant.id_producto,
            ProductVariant.id_variante_producto,
            ProductVariant.sku,
            Size.id_talla,
            Size.nombre.label("talla"),
            Color.id_color,
            Color.nombre.label("color"),
            Color.codigo_hex,
        ]
        statement = (
            select(*columns)
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
        )
        if branch_id is not None:
            statement = statement.add_columns(
                func.coalesce(BranchInventory.stock_actual, 0).label("stock_actual"),
                func.coalesce(BranchInventory.stock_reservado, 0).label(
                    "stock_reservado"
                ),
            ).outerjoin(
                BranchInventory,
                (
                    (
                        BranchInventory.id_variante_producto
                        == ProductVariant.id_variante_producto
                    )
                    & (BranchInventory.id_sucursal == branch_id)
                ),
            )
        return self.db.execute(
            statement.where(
                ProductVariant.id_producto.in_(product_ids),
                ProductVariant.estado.is_(True),
            ).order_by(
                ProductVariant.id_producto,
                Size.nombre,
                Color.nombre,
                ProductVariant.id_variante_producto,
            )
        ).mappings().all()

    def list_images(self, product_id: int):
        return self.db.execute(
            select(
                ProductImage.id_imagen_producto,
                ProductImage.url_imagen,
                ProductImage.es_principal,
            )
            .where(ProductImage.id_producto == product_id)
            .order_by(
                ProductImage.es_principal.desc(),
                ProductImage.id_imagen_producto,
            )
        ).mappings().all()

    def list_active_collections(self, product_id: int):
        return self.db.execute(
            select(Collection.id_coleccion, Collection.nombre)
            .join(
                ProductCollection,
                ProductCollection.id_coleccion == Collection.id_coleccion,
            )
            .where(
                ProductCollection.id_producto == product_id,
                Collection.estado.is_(True),
            )
            .order_by(Collection.nombre, Collection.id_coleccion)
        ).mappings().all()

    def list_current_promotions(self, product_id: int):
        candidates = self._promotion_candidates()
        return self.db.execute(
            select(*candidates.c)
            .where(candidates.c.id_producto == product_id)
            .order_by(candidates.c.precio_resultante, candidates.c.id_promocion)
        ).mappings().all()

    def get_branch(self, branch_id: int) -> Branch | None:
        return self.db.scalar(
            select(Branch).where(Branch.id_sucursal == branch_id)
        )

    def get_city(self, city_id: int) -> City | None:
        return self.db.scalar(select(City).where(City.id_ciudad == city_id))
