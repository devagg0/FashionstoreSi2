"""Reglas de negocio de CU10: gestion administrativa de productos."""

from math import ceil
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.integrations.supabase_storage import (
    StoredObject,
    SupabaseStorageClient,
    SupabaseStorageConfigurationError,
    SupabaseStorageUploadError,
)
from app.models.product_image import ProductImage
from app.repositories.admin_products import AdminProductRepository
from app.schemas.admin_products import (
    AdminProductData,
    AdminProductDetailData,
    ProductCollectionData,
    ProductCollectionsRequest,
    ProductCreateRequest,
    ProductImageCreateRequest,
    ProductImageData,
    ProductImageUpdateRequest,
    ProductPaginationData,
    ProductStatusUpdateRequest,
    ProductSupplierData,
    ProductSupplierStatusUpdateRequest,
    ProductSuppliersRequest,
    ProductSupplierUpdateRequest,
    ProductUpdateRequest,
    ProductVariantCreateRequest,
    ProductVariantData,
    ProductVariantStatusUpdateRequest,
    ProductVariantUpdateRequest,
)


class ProductNotFoundError(Exception):
    """El producto solicitado no existe."""


class ProductChildNotFoundError(Exception):
    """Una variante, imagen o asociacion del producto no existe."""


class ProductReferenceNotFoundError(Exception):
    """Una referencia maestra seleccionada no existe."""


class ProductReferenceInactiveError(Exception):
    """Una referencia nueva o reactivada debe estar activa."""


class ProductConflictError(Exception):
    """La operacion viola una regla de unicidad del producto."""


class AdminProductPersistenceError(Exception):
    """La operacion no pudo persistirse."""


class ProductImageValidationError(Exception):
    """El archivo recibido no cumple el contrato de imagen de CU10."""


class ProductImageStorageConfigurationError(Exception):
    """El backend no tiene configurado Supabase Storage."""


class ProductImageStorageError(Exception):
    """La imagen no pudo persistirse en Supabase Storage."""


DOMAIN_ERRORS = (
    ProductNotFoundError,
    ProductChildNotFoundError,
    ProductReferenceNotFoundError,
    ProductReferenceInactiveError,
    ProductConflictError,
)


class AdminProductService:
    """Orquesta productos, variantes, asociaciones e imagenes para CU10."""

    MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
    IMAGE_MIME_BY_EXTENSION = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }

    def __init__(
        self, db: Session, storage_client: SupabaseStorageClient | None = None
    ) -> None:
        self.db = db
        self.repository = AdminProductRepository(db)
        self.storage_client = storage_client

    def list_products(
        self,
        *,
        search: str | None,
        state: bool | None,
        category_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminProductData], ProductPaginationData]:
        rows, total = self.repository.list_products(
            search=search,
            state=state,
            category_id=category_id,
            page=page,
            page_size=page_size,
        )
        pagination = ProductPaginationData(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
        return [AdminProductData.model_validate(row) for row in rows], pagination

    def get_product(self, product_id: int) -> AdminProductDetailData:
        if self.repository.get_by_id(product_id) is None:
            raise ProductNotFoundError("Producto no encontrado")
        return self._get_product_detail(product_id)

    def create_product(self, payload: ProductCreateRequest) -> AdminProductDetailData:
        try:
            self._validate_category(payload.id_categoria)
            if payload.id_temporada is not None:
                self._validate_season(payload.id_temporada)
            product = self.repository.create_product(**payload.model_dump())
            result = self._get_product_detail(product.id_producto)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def update_product(
        self, *, product_id: int, payload: ProductUpdateRequest
    ) -> AdminProductDetailData:
        try:
            product = self._get_product_for_update(product_id)
            values = payload.model_dump(exclude_unset=True)
            if (
                "id_categoria" in values
                and values["id_categoria"] != product.id_categoria
            ):
                self._validate_category(values["id_categoria"])
            if (
                "id_temporada" in values
                and values["id_temporada"] is not None
                and values["id_temporada"] != product.id_temporada
            ):
                self._validate_season(values["id_temporada"])
            self.repository.update_product(product, **values)
            result = self._get_product_detail(product_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def update_product_status(
        self, *, product_id: int, payload: ProductStatusUpdateRequest
    ) -> AdminProductDetailData:
        try:
            product = self._get_product_for_update(product_id)
            if payload.estado:
                self._validate_category(product.id_categoria)
                if product.id_temporada is not None:
                    self._validate_season(product.id_temporada)
            self.repository.update_product_status(product, state=payload.estado)
            result = self._get_product_detail(product_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def create_variant(
        self, *, product_id: int, payload: ProductVariantCreateRequest
    ) -> ProductVariantData:
        try:
            self._get_product_for_update(product_id)
            self._validate_size(payload.id_talla)
            self._validate_color(payload.id_color)
            self._ensure_unique_variant(
                product_id=product_id,
                size_id=payload.id_talla,
                color_id=payload.id_color,
                sku=payload.sku,
            )
            variant = self.repository.create_variant(
                product_id=product_id,
                size_id=payload.id_talla,
                color_id=payload.id_color,
                sku=payload.sku,
            )
            result = self._get_variant_data(product_id, variant.id_variante_producto)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise ProductConflictError(
                "El SKU o la combinacion de talla y color ya existe"
            ) from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def update_variant(
        self,
        *,
        product_id: int,
        variant_id: int,
        payload: ProductVariantUpdateRequest,
    ) -> ProductVariantData:
        try:
            self._get_product_for_update(product_id)
            variant = self.repository.get_variant(
                product_id, variant_id, for_update=True
            )
            if variant is None:
                raise ProductChildNotFoundError("Variante no encontrada")
            values = payload.model_dump(exclude_unset=True)
            size_id = values.get("id_talla", variant.id_talla)
            color_id = values.get("id_color", variant.id_color)
            sku = values.get("sku", variant.sku)
            if "id_talla" in values and size_id != variant.id_talla:
                self._validate_size(size_id)
            if "id_color" in values and color_id != variant.id_color:
                self._validate_color(color_id)
            self._ensure_unique_variant(
                product_id=product_id,
                size_id=size_id,
                color_id=color_id,
                sku=sku,
                exclude_variant_id=variant_id,
            )
            self.repository.update_variant(variant, **values)
            result = self._get_variant_data(product_id, variant_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise ProductConflictError(
                "El SKU o la combinacion de talla y color ya existe"
            ) from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def update_variant_status(
        self,
        *,
        product_id: int,
        variant_id: int,
        payload: ProductVariantStatusUpdateRequest,
    ) -> ProductVariantData:
        try:
            self._get_product_for_update(product_id)
            variant = self.repository.get_variant(
                product_id, variant_id, for_update=True
            )
            if variant is None:
                raise ProductChildNotFoundError("Variante no encontrada")
            if payload.estado:
                self._validate_size(variant.id_talla)
                self._validate_color(variant.id_color)
            self.repository.update_variant(variant, estado=payload.estado)
            result = self._get_variant_data(product_id, variant_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def add_collections(
        self, *, product_id: int, payload: ProductCollectionsRequest
    ) -> list[ProductCollectionData]:
        try:
            self._get_product_for_update(product_id)
            for collection_id in payload.id_colecciones:
                self._validate_collection(collection_id)
                if self.repository.get_product_collection(product_id, collection_id):
                    raise ProductConflictError(
                        f"La coleccion {collection_id} ya esta asociada al producto"
                    )
            for collection_id in payload.id_colecciones:
                self.repository.add_collection(product_id, collection_id)
            result = self._get_collections(product_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise ProductConflictError(
                "Una coleccion ya esta asociada al producto"
            ) from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def add_suppliers(
        self, *, product_id: int, payload: ProductSuppliersRequest
    ) -> list[ProductSupplierData]:
        try:
            self._get_product_for_update(product_id)
            for item in payload.proveedores:
                self._validate_supplier(item.id_proveedor)
                association = self.repository.get_product_supplier(
                    product_id,
                    supplier_id=item.id_proveedor,
                    for_update=True,
                )
                if association is not None and association.estado:
                    raise ProductConflictError(
                        f"El proveedor {item.id_proveedor} ya esta asociado al producto"
                    )
                if association is None:
                    self.repository.create_product_supplier(
                        product_id=product_id,
                        supplier_id=item.id_proveedor,
                        reference_cost=item.costo_referencia,
                    )
                else:
                    self.repository.update_product_supplier(
                        association,
                        costo_referencia=item.costo_referencia,
                        estado=True,
                    )
            result = self._get_suppliers(product_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            raise ProductConflictError(
                "Un proveedor ya esta asociado al producto"
            ) from error
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def update_supplier(
        self,
        *,
        product_id: int,
        association_id: int,
        payload: ProductSupplierUpdateRequest,
    ) -> ProductSupplierData:
        return self._change_supplier(
            product_id=product_id,
            association_id=association_id,
            values=payload.model_dump(exclude_unset=True),
            validate_activation=False,
        )

    def update_supplier_status(
        self,
        *,
        product_id: int,
        association_id: int,
        payload: ProductSupplierStatusUpdateRequest,
    ) -> ProductSupplierData:
        return self._change_supplier(
            product_id=product_id,
            association_id=association_id,
            values={"estado": payload.estado},
            validate_activation=payload.estado,
        )

    def _change_supplier(
        self,
        *,
        product_id: int,
        association_id: int,
        values: dict,
        validate_activation: bool,
    ) -> ProductSupplierData:
        try:
            self._get_product_for_update(product_id)
            association = self.repository.get_product_supplier(
                product_id,
                association_id=association_id,
                for_update=True,
            )
            if association is None:
                raise ProductChildNotFoundError("Asociacion de proveedor no encontrada")
            if validate_activation:
                self._validate_supplier(association.id_proveedor)
            self.repository.update_product_supplier(association, **values)
            result = self._get_supplier_data(product_id, association_id)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def create_image(
        self, *, product_id: int, payload: ProductImageCreateRequest
    ) -> ProductImageData:
        try:
            self._get_product_for_update(product_id)
            is_primary = payload.es_principal or not self.repository.has_images(product_id)
            if is_primary:
                self.repository.clear_primary_images(product_id)
            image = self.repository.create_image(
                product_id=product_id,
                image_url=payload.url_imagen,
                is_primary=is_primary,
            )
            result = self._to_image_data(image)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def upload_image(
        self,
        *,
        product_id: int,
        filename: str,
        content_type: str,
        content: bytes,
        is_primary: bool,
    ) -> ProductImageData:
        """Valida, carga en Storage y persiste solamente la URL resultante."""
        stored_object: StoredObject | None = None
        storage_client: SupabaseStorageClient | None = None
        try:
            self._get_product_for_update(product_id)
            extension, normalized_mime = self._validate_image_file(
                filename=filename,
                content_type=content_type,
                content=content,
            )
            try:
                storage_client = (
                    self.storage_client or SupabaseStorageClient.from_settings()
                )
                stored_object = storage_client.upload_public_image(
                    object_path=f"products/{product_id}/{uuid4().hex}{extension}",
                    content=content,
                    content_type=normalized_mime,
                )
            except SupabaseStorageConfigurationError as error:
                raise ProductImageStorageConfigurationError(
                    "Supabase Storage no esta configurado"
                ) from error
            except SupabaseStorageUploadError as error:
                raise ProductImageStorageError(
                    "No fue posible subir la imagen"
                ) from error

            primary = is_primary or not self.repository.has_images(product_id)
            if primary:
                self.repository.clear_primary_images(product_id)
            image = self.repository.create_image(
                product_id=product_id,
                image_url=stored_object.public_url,
                is_primary=primary,
            )
            result = self._to_image_data(image)
            self.db.commit()
            return result
        except (
            *DOMAIN_ERRORS,
            ProductImageValidationError,
            ProductImageStorageConfigurationError,
            ProductImageStorageError,
        ):
            self.db.rollback()
            self._remove_uncommitted_object(storage_client, stored_object)
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            self._remove_uncommitted_object(storage_client, stored_object)
            raise AdminProductPersistenceError from error

    def update_image(
        self,
        *,
        product_id: int,
        image_id: int,
        payload: ProductImageUpdateRequest,
    ) -> ProductImageData:
        try:
            self._get_product_for_update(product_id)
            image = self.repository.get_image(product_id, image_id, for_update=True)
            if image is None:
                raise ProductChildNotFoundError("Imagen no encontrada")
            values = payload.model_dump(exclude_unset=True)
            if values.get("es_principal") is True:
                self.repository.clear_primary_images(
                    product_id, exclude_image_id=image_id
                )
            self.repository.update_image(image, **values)
            result = self._to_image_data(image)
            self.db.commit()
            return result
        except DOMAIN_ERRORS:
            self.db.rollback()
            raise
        except SQLAlchemyError as error:
            self.db.rollback()
            raise AdminProductPersistenceError from error

    def _get_product_for_update(self, product_id: int):
        product = self.repository.get_by_id(product_id, for_update=True)
        if product is None:
            raise ProductNotFoundError("Producto no encontrado")
        return product

    @classmethod
    def _validate_image_file(
        cls, *, filename: str, content_type: str, content: bytes
    ) -> tuple[str, str]:
        extension = Path(filename).suffix.lower()
        expected_mime = cls.IMAGE_MIME_BY_EXTENSION.get(extension)
        normalized_mime = content_type.split(";", maxsplit=1)[0].strip().lower()
        if expected_mime is None:
            raise ProductImageValidationError(
                "Solo se permiten imagenes JPG, JPEG, PNG o WEBP"
            )
        if normalized_mime != expected_mime:
            raise ProductImageValidationError(
                "El tipo MIME no coincide con la extension"
            )
        if not content:
            raise ProductImageValidationError("El archivo de imagen esta vacio")
        if len(content) > cls.MAX_IMAGE_SIZE_BYTES:
            raise ProductImageValidationError("La imagen no puede superar 5 MB")
        if not cls._matches_image_signature(content, normalized_mime):
            raise ProductImageValidationError(
                "El contenido no corresponde a una imagen valida"
            )
        return extension, normalized_mime

    @staticmethod
    def _matches_image_signature(content: bytes, content_type: str) -> bool:
        if content_type == "image/jpeg":
            return content.startswith(b"\xff\xd8\xff")
        if content_type == "image/png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        if content_type == "image/webp":
            return (
                len(content) >= 12
                and content.startswith(b"RIFF")
                and content[8:12] == b"WEBP"
            )
        return False

    @staticmethod
    def _remove_uncommitted_object(
        storage_client: SupabaseStorageClient | None,
        stored_object: StoredObject | None,
    ) -> None:
        if storage_client is not None and stored_object is not None:
            storage_client.remove(stored_object.path)

    def _validate_category(self, category_id: int) -> None:
        category = self.repository.get_category(category_id, for_update=True)
        self._validate_reference(category, "Categoria")

    def _validate_season(self, season_id: int) -> None:
        season = self.repository.get_season(season_id, for_update=True)
        self._validate_reference(season, "Temporada")

    def _validate_size(self, size_id: int) -> None:
        size = self.repository.get_size(size_id, for_update=True)
        self._validate_reference(size, "Talla")

    def _validate_color(self, color_id: int) -> None:
        color = self.repository.get_color(color_id, for_update=True)
        self._validate_reference(color, "Color")

    def _validate_collection(self, collection_id: int) -> None:
        collection = self.repository.get_collection(collection_id, for_update=True)
        self._validate_reference(collection, "Coleccion")

    def _validate_supplier(self, supplier_id: int) -> None:
        supplier = self.repository.get_supplier(supplier_id, for_update=True)
        self._validate_reference(supplier, "Proveedor")

    @staticmethod
    def _validate_reference(reference, name: str) -> None:
        if reference is None:
            raise ProductReferenceNotFoundError(f"{name} no encontrada")
        if not reference.estado:
            raise ProductReferenceInactiveError(f"{name} inactiva")

    def _ensure_unique_variant(
        self,
        *,
        product_id: int,
        size_id: int,
        color_id: int,
        sku: str,
        exclude_variant_id: int | None = None,
    ) -> None:
        if self.repository.get_variant_by_sku(
            sku, exclude_variant_id=exclude_variant_id
        ):
            raise ProductConflictError("El SKU ya esta registrado")
        if self.repository.get_variant_by_combination(
            product_id,
            size_id,
            color_id,
            exclude_variant_id=exclude_variant_id,
        ):
            raise ProductConflictError(
                "La combinacion de talla y color ya existe para el producto"
            )

    def _get_product_detail(self, product_id: int) -> AdminProductDetailData:
        row = self.repository.get_product_summary(product_id)
        if row is None:
            raise ProductNotFoundError("Producto no encontrado")
        summary = AdminProductData.model_validate(row)
        return AdminProductDetailData(
            **summary.model_dump(),
            variantes=self._get_variants(product_id),
            colecciones=self._get_collections(product_id),
            proveedores=self._get_suppliers(product_id),
            imagenes=[
                self._to_image_data(image)
                for image in self.repository.list_images(product_id)
            ],
        )

    def _get_variants(self, product_id: int) -> list[ProductVariantData]:
        return [
            ProductVariantData.model_validate(row)
            for row in self.repository.list_variants(product_id)
        ]

    def _get_variant_data(
        self, product_id: int, variant_id: int
    ) -> ProductVariantData:
        row = self.repository.get_variant_detail(product_id, variant_id)
        if row is None:
            raise ProductChildNotFoundError("Variante no encontrada")
        return ProductVariantData.model_validate(row)

    def _get_collections(self, product_id: int) -> list[ProductCollectionData]:
        return [
            ProductCollectionData.model_validate(row)
            for row in self.repository.list_collections(product_id)
        ]

    def _get_suppliers(self, product_id: int) -> list[ProductSupplierData]:
        return [
            ProductSupplierData.model_validate(row)
            for row in self.repository.list_suppliers(product_id)
        ]

    def _get_supplier_data(
        self, product_id: int, association_id: int
    ) -> ProductSupplierData:
        row = self.repository.get_product_supplier_detail(product_id, association_id)
        if row is None:
            raise ProductChildNotFoundError("Asociacion de proveedor no encontrada")
        return ProductSupplierData.model_validate(row)

    @staticmethod
    def _to_image_data(image: ProductImage) -> ProductImageData:
        return ProductImageData(
            id_imagen_producto=image.id_imagen_producto,
            url_imagen=image.url_imagen,
            es_principal=image.es_principal,
            created_at=image.created_at,
        )
