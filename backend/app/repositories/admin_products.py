"""Persistencia de CU10 sobre las tablas de productos existentes."""

from decimal import Decimal

from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.collection import Collection
from app.models.color import Color
from app.models.product import Product
from app.models.product_collection import ProductCollection
from app.models.product_image import ProductImage
from app.models.product_supplier import ProductSupplier
from app.models.product_variant import ProductVariant
from app.models.season import Season
from app.models.size import Size
from app.models.supplier import Supplier


class AdminProductRepository:
    """Centraliza consultas y mutaciones de productos y sus asociaciones."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _apply_filters(
        statement: Select,
        *,
        search: str | None,
        state: bool | None,
        category_id: int | None,
    ) -> Select:
        if search and search.strip():
            escaped = (
                search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            pattern = f"%{escaped}%"
            statement = statement.where(
                or_(
                    Product.nombre.ilike(pattern, escape="\\"),
                    exists(
                        select(1).where(
                            ProductVariant.id_producto == Product.id_producto,
                            ProductVariant.sku.ilike(pattern, escape="\\"),
                        )
                    ),
                )
            )
        if state is not None:
            statement = statement.where(Product.estado.is_(state))
        if category_id is not None:
            statement = statement.where(Product.id_categoria == category_id)
        return statement

    @staticmethod
    def _list_columns():
        principal_image = (
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
        variant_count = (
            select(func.count(ProductVariant.id_variante_producto))
            .where(ProductVariant.id_producto == Product.id_producto)
            .correlate(Product)
            .scalar_subquery()
        )
        return (
            Product.id_producto,
            Product.id_categoria,
            Category.nombre.label("categoria"),
            Product.id_temporada,
            Season.nombre.label("temporada"),
            Product.nombre,
            Product.seccion,
            Product.descripcion,
            Product.precio,
            Product.estado,
            principal_image.label("imagen_principal"),
            variant_count.label("total_variantes"),
            Product.created_at,
            Product.updated_at,
        )

    def list_products(
        self,
        *,
        search: str | None,
        state: bool | None,
        category_id: int | None,
        page: int,
        page_size: int,
    ):
        filters = {
            "search": search,
            "state": state,
            "category_id": category_id,
        }
        statement = self._apply_filters(
            select(*self._list_columns())
            .join(Category, Category.id_categoria == Product.id_categoria)
            .outerjoin(Season, Season.id_temporada == Product.id_temporada),
            **filters,
        )
        count_statement = self._apply_filters(
            select(func.count(Product.id_producto)), **filters
        )
        rows = self.db.execute(
            statement.order_by(Product.nombre, Product.id_producto)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).mappings().all()
        total = self.db.scalar(count_statement) or 0
        return rows, total

    def get_by_id(self, product_id: int, *, for_update: bool = False) -> Product | None:
        statement = select(Product).where(Product.id_producto == product_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_product_summary(self, product_id: int):
        return self.db.execute(
            select(*self._list_columns())
            .join(Category, Category.id_categoria == Product.id_categoria)
            .outerjoin(Season, Season.id_temporada == Product.id_temporada)
            .where(Product.id_producto == product_id)
        ).mappings().one_or_none()

    def get_category(self, category_id: int, *, for_update: bool = False):
        statement = select(Category).where(Category.id_categoria == category_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_season(self, season_id: int, *, for_update: bool = False):
        statement = select(Season).where(Season.id_temporada == season_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_size(self, size_id: int, *, for_update: bool = False):
        statement = select(Size).where(Size.id_talla == size_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_color(self, color_id: int, *, for_update: bool = False):
        statement = select(Color).where(Color.id_color == color_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_collection(self, collection_id: int, *, for_update: bool = False):
        statement = select(Collection).where(Collection.id_coleccion == collection_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_supplier(self, supplier_id: int, *, for_update: bool = False):
        statement = select(Supplier).where(Supplier.id_proveedor == supplier_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def create_product(self, **values) -> Product:
        product = Product(**values, estado=True)
        self.db.add(product)
        self.db.flush()
        return product

    def update_product(self, product: Product, **values) -> None:
        for field, value in values.items():
            setattr(product, field, value)
        self.db.flush()

    def update_product_status(self, product: Product, *, state: bool) -> None:
        product.estado = state
        self.db.flush()

    def list_variants(self, product_id: int):
        return self.db.execute(
            select(
                ProductVariant.id_variante_producto,
                ProductVariant.id_talla,
                Size.nombre.label("talla"),
                ProductVariant.id_color,
                Color.nombre.label("color"),
                ProductVariant.sku,
                ProductVariant.estado,
                ProductVariant.created_at,
                ProductVariant.updated_at,
            )
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(ProductVariant.id_producto == product_id)
            .order_by(Size.nombre, Color.nombre, ProductVariant.id_variante_producto)
        ).mappings().all()

    def get_variant(
        self, product_id: int, variant_id: int, *, for_update: bool = False
    ) -> ProductVariant | None:
        statement = select(ProductVariant).where(
            ProductVariant.id_producto == product_id,
            ProductVariant.id_variante_producto == variant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_variant_detail(self, product_id: int, variant_id: int):
        return self.db.execute(
            select(
                ProductVariant.id_variante_producto,
                ProductVariant.id_talla,
                Size.nombre.label("talla"),
                ProductVariant.id_color,
                Color.nombre.label("color"),
                ProductVariant.sku,
                ProductVariant.estado,
                ProductVariant.created_at,
                ProductVariant.updated_at,
            )
            .join(Size, Size.id_talla == ProductVariant.id_talla)
            .join(Color, Color.id_color == ProductVariant.id_color)
            .where(
                ProductVariant.id_producto == product_id,
                ProductVariant.id_variante_producto == variant_id,
            )
        ).mappings().one_or_none()

    def get_variant_by_sku(
        self, sku: str, *, exclude_variant_id: int | None = None
    ) -> ProductVariant | None:
        statement = select(ProductVariant).where(
            func.lower(ProductVariant.sku) == sku.lower()
        )
        if exclude_variant_id is not None:
            statement = statement.where(
                ProductVariant.id_variante_producto != exclude_variant_id
            )
        return self.db.scalar(statement.with_for_update())

    def get_variant_by_combination(
        self,
        product_id: int,
        size_id: int,
        color_id: int,
        *,
        exclude_variant_id: int | None = None,
    ) -> ProductVariant | None:
        statement = select(ProductVariant).where(
            ProductVariant.id_producto == product_id,
            ProductVariant.id_talla == size_id,
            ProductVariant.id_color == color_id,
        )
        if exclude_variant_id is not None:
            statement = statement.where(
                ProductVariant.id_variante_producto != exclude_variant_id
            )
        return self.db.scalar(statement.with_for_update())

    def create_variant(
        self, *, product_id: int, size_id: int, color_id: int, sku: str
    ) -> ProductVariant:
        variant = ProductVariant(
            id_producto=product_id,
            id_talla=size_id,
            id_color=color_id,
            sku=sku,
            estado=True,
        )
        self.db.add(variant)
        self.db.flush()
        return variant

    def update_variant(self, variant: ProductVariant, **values) -> None:
        for field, value in values.items():
            setattr(variant, field, value)
        self.db.flush()

    def list_collections(self, product_id: int):
        return self.db.execute(
            select(
                ProductCollection.id_producto_coleccion,
                ProductCollection.id_coleccion,
                Collection.nombre.label("coleccion"),
                Collection.estado.label("estado_coleccion"),
            )
            .join(Collection, Collection.id_coleccion == ProductCollection.id_coleccion)
            .where(ProductCollection.id_producto == product_id)
            .order_by(Collection.nombre, ProductCollection.id_producto_coleccion)
        ).mappings().all()

    def get_product_collection(self, product_id: int, collection_id: int):
        return self.db.scalar(
            select(ProductCollection)
            .where(
                ProductCollection.id_producto == product_id,
                ProductCollection.id_coleccion == collection_id,
            )
            .with_for_update()
        )

    def add_collection(self, product_id: int, collection_id: int) -> ProductCollection:
        association = ProductCollection(
            id_producto=product_id, id_coleccion=collection_id
        )
        self.db.add(association)
        self.db.flush()
        return association

    def list_suppliers(self, product_id: int):
        return self.db.execute(
            select(
                ProductSupplier.id_producto_proveedor,
                ProductSupplier.id_proveedor,
                Supplier.nombre.label("proveedor"),
                ProductSupplier.costo_referencia,
                ProductSupplier.estado,
                Supplier.estado.label("estado_proveedor"),
            )
            .join(Supplier, Supplier.id_proveedor == ProductSupplier.id_proveedor)
            .where(ProductSupplier.id_producto == product_id)
            .order_by(Supplier.nombre, ProductSupplier.id_producto_proveedor)
        ).mappings().all()

    def get_product_supplier(
        self,
        product_id: int,
        *,
        association_id: int | None = None,
        supplier_id: int | None = None,
        for_update: bool = False,
    ) -> ProductSupplier | None:
        statement = select(ProductSupplier).where(
            ProductSupplier.id_producto == product_id
        )
        if association_id is not None:
            statement = statement.where(
                ProductSupplier.id_producto_proveedor == association_id
            )
        if supplier_id is not None:
            statement = statement.where(ProductSupplier.id_proveedor == supplier_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_product_supplier_detail(self, product_id: int, association_id: int):
        return self.db.execute(
            select(
                ProductSupplier.id_producto_proveedor,
                ProductSupplier.id_proveedor,
                Supplier.nombre.label("proveedor"),
                ProductSupplier.costo_referencia,
                ProductSupplier.estado,
                Supplier.estado.label("estado_proveedor"),
            )
            .join(Supplier, Supplier.id_proveedor == ProductSupplier.id_proveedor)
            .where(
                ProductSupplier.id_producto == product_id,
                ProductSupplier.id_producto_proveedor == association_id,
            )
        ).mappings().one_or_none()

    def create_product_supplier(
        self,
        *,
        product_id: int,
        supplier_id: int,
        reference_cost: Decimal | None,
    ) -> ProductSupplier:
        association = ProductSupplier(
            id_producto=product_id,
            id_proveedor=supplier_id,
            costo_referencia=reference_cost,
            estado=True,
        )
        self.db.add(association)
        self.db.flush()
        return association

    def update_product_supplier(
        self, association: ProductSupplier, **values
    ) -> None:
        for field, value in values.items():
            setattr(association, field, value)
        self.db.flush()

    def list_images(self, product_id: int):
        return list(
            self.db.scalars(
                select(ProductImage)
                .where(ProductImage.id_producto == product_id)
                .order_by(
                    ProductImage.es_principal.desc(),
                    ProductImage.id_imagen_producto,
                )
            ).all()
        )

    def get_image(
        self, product_id: int, image_id: int, *, for_update: bool = False
    ) -> ProductImage | None:
        statement = select(ProductImage).where(
            ProductImage.id_producto == product_id,
            ProductImage.id_imagen_producto == image_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def has_images(self, product_id: int) -> bool:
        return bool(
            self.db.scalar(
                select(exists().where(ProductImage.id_producto == product_id))
            )
        )

    def clear_primary_images(
        self, product_id: int, *, exclude_image_id: int | None = None
    ) -> None:
        statement = update(ProductImage).where(
            ProductImage.id_producto == product_id,
            ProductImage.es_principal.is_(True),
        )
        if exclude_image_id is not None:
            statement = statement.where(
                ProductImage.id_imagen_producto != exclude_image_id
            )
        self.db.execute(statement.values(es_principal=False))
        self.db.flush()

    def create_image(
        self, *, product_id: int, image_url: str, is_primary: bool
    ) -> ProductImage:
        image = ProductImage(
            id_producto=product_id,
            url_imagen=image_url,
            es_principal=is_primary,
        )
        self.db.add(image)
        self.db.flush()
        return image

    def update_image(self, image: ProductImage, **values) -> None:
        for field, value in values.items():
            setattr(image, field, value)
        self.db.flush()
