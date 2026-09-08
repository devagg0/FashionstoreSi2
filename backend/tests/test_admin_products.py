"""Pruebas unitarias de CU10 sin conectar ni modificar PostgreSQL."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.repositories.admin_products import AdminProductRepository
from app.routers import admin_products as routes
from app.integrations.supabase_storage import StoredObject
from app.schemas.admin_products import (
    ProductCollectionsRequest,
    ProductCreateRequest,
    ProductImageCreateRequest,
    ProductImageUpdateRequest,
    ProductStatusUpdateRequest,
    ProductSupplierItemRequest,
    ProductSuppliersRequest,
    ProductSupplierUpdateRequest,
    ProductUpdateRequest,
    ProductVariantCreateRequest,
    ProductVariantStatusUpdateRequest,
    ProductVariantUpdateRequest,
)
from app.services.admin_products import (
    AdminProductPersistenceError,
    AdminProductService,
    ProductConflictError,
    ProductImageStorageConfigurationError,
    ProductImageStorageError,
    ProductImageValidationError,
    ProductNotFoundError,
    ProductReferenceInactiveError,
    ProductReferenceNotFoundError,
)


NOW = datetime(2026, 1, 1)


def product_record(**changes):
    values = {
        "id_producto": 7,
        "id_categoria": 2,
        "id_temporada": 3,
        "nombre": "Camisa",
        "seccion": "HOMBRE",
        "descripcion": None,
        "precio": Decimal("49.90"),
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def variant_detail(**changes):
    values = {
        "id_variante_producto": 11,
        "id_talla": 4,
        "talla": "M",
        "id_color": 5,
        "color": "Negro",
        "sku": "CAM-M-NEG",
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return values


class ProductSchemaTests(TestCase):
    def test_product_normalization_and_constraints(self):
        payload = ProductCreateRequest(
            id_categoria=2,
            nombre=" Camisa ",
            seccion="UNISEX",
            descripcion=" suave ",
            precio="10.50",
        )
        self.assertEqual(payload.nombre, "Camisa")
        self.assertEqual(payload.descripcion, "suave")
        self.assertEqual(payload.precio, Decimal("10.50"))
        for values in (
            {},
            {"id_categoria": 0, "nombre": "A", "seccion": "HOMBRE", "precio": 1},
            {"id_categoria": 1, "nombre": " ", "seccion": "HOMBRE", "precio": 1},
            {"id_categoria": 1, "nombre": "A", "seccion": "NINOS", "precio": 1},
            {"id_categoria": 1, "nombre": "A", "seccion": "HOMBRE", "precio": -1},
            {"id_categoria": 1, "nombre": "A", "seccion": "HOMBRE", "precio": 1, "stock": 2},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ProductCreateRequest(**values)

    def test_partial_product_update(self):
        self.assertEqual(
            ProductUpdateRequest(id_temporada=None).model_dump(exclude_unset=True),
            {"id_temporada": None},
        )
        for values in ({}, {"nombre": None}, {"precio": None}, {"estado": False}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ProductUpdateRequest(**values)

    def test_variant_sku_and_duplicate_payload_ids(self):
        variant = ProductVariantCreateRequest(id_talla=1, id_color=2, sku=" ab-01 ")
        self.assertEqual(variant.sku, "AB-01")
        with self.assertRaises(ValidationError):
            ProductVariantUpdateRequest()
        with self.assertRaises(ValidationError):
            ProductCollectionsRequest(id_colecciones=[1, 1])
        with self.assertRaises(ValidationError):
            ProductSuppliersRequest(
                proveedores=[
                    ProductSupplierItemRequest(id_proveedor=1),
                    ProductSupplierItemRequest(id_proveedor=1),
                ]
            )

    def test_image_and_supplier_update_contracts(self):
        self.assertEqual(
            ProductImageCreateRequest(url_imagen=" https://cdn.test/a.jpg ").url_imagen,
            "https://cdn.test/a.jpg",
        )
        for invalid_url in ("file:///tmp/a.jpg", "https://"):
            with self.subTest(url=invalid_url), self.assertRaises(ValidationError):
                ProductImageCreateRequest(url_imagen=invalid_url)
        with self.assertRaises(ValidationError):
            ProductImageUpdateRequest()
        with self.assertRaises(ValidationError):
            ProductSupplierUpdateRequest()
        self.assertIsNone(ProductSupplierUpdateRequest(costo_referencia=None).costo_referencia)


class ProductRepositoryTests(TestCase):
    def test_list_filters_search_name_or_sku_and_category(self):
        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        db.scalar.return_value = 0
        repository = AdminProductRepository(db)
        self.assertEqual(
            repository.list_products(
                search=" %_\\ ", state=False, category_id=9, page=2, page_size=3
            ),
            ([], 0),
        )
        query = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(query)
        self.assertIn("t_producto.nombre ILIKE", sql)
        self.assertIn("t_variante_producto.sku ILIKE", sql)
        self.assertIn("t_producto.estado IS false", sql)
        self.assertIn("t_producto.id_categoria", sql)
        self.assertIn("ORDER BY t_producto.nombre, t_producto.id_producto", sql)
        self.assertIn("%\\%\\_\\\\%", query.params.values())
        self.assertEqual(
            next(value for value in query.params.values() if isinstance(value, str)),
            next(value for value in count.params.values() if isinstance(value, str)),
        )

    def test_repository_mutations_flush_without_commit_or_delete(self):
        db = MagicMock()
        repository = AdminProductRepository(db)
        product = repository.create_product(
            id_categoria=1,
            id_temporada=None,
            nombre="Camisa",
            seccion="HOMBRE",
            descripcion=None,
            precio=Decimal("10.00"),
        )
        variant = repository.create_variant(
            product_id=7, size_id=1, color_id=2, sku="SKU-1"
        )
        image = repository.create_image(
            product_id=7, image_url="https://cdn.test/a.jpg", is_primary=True
        )
        self.assertTrue(product.estado)
        self.assertTrue(variant.estado)
        self.assertTrue(image.es_principal)
        self.assertEqual(db.add.call_count, 3)
        self.assertEqual(db.flush.call_count, 3)
        db.commit.assert_not_called()
        db.delete.assert_not_called()

    def test_sku_lookup_is_case_insensitive_and_locked(self):
        db = MagicMock()
        AdminProductRepository(db).get_variant_by_sku("sku-1", exclude_variant_id=8)
        query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("lower(t_variante_producto.sku)", str(query))
        self.assertIn("!=", str(query))
        self.assertIn("FOR UPDATE", str(query))


class ProductServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminProductService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.product = product_record()
        self.repo.get_by_id.return_value = self.product
        self.repo.get_category.return_value = SimpleNamespace(estado=True)
        self.repo.get_season.return_value = SimpleNamespace(estado=True)
        self.repo.get_size.return_value = SimpleNamespace(estado=True)
        self.repo.get_color.return_value = SimpleNamespace(estado=True)
        self.repo.get_collection.return_value = SimpleNamespace(estado=True)
        self.repo.get_supplier.return_value = SimpleNamespace(estado=True)
        self.repo.get_variant_by_sku.return_value = None
        self.repo.get_variant_by_combination.return_value = None

    def test_create_product_validates_active_references_and_commits(self):
        self.repo.create_product.return_value = self.product
        expected = MagicMock()
        with patch.object(self.service, "_get_product_detail", return_value=expected):
            result = self.service.create_product(
                ProductCreateRequest(
                    id_categoria=2,
                    id_temporada=3,
                    nombre="Camisa",
                    seccion="HOMBRE",
                    precio="49.90",
                )
            )
        self.assertIs(result, expected)
        self.repo.get_category.assert_called_once_with(2, for_update=True)
        self.repo.get_season.assert_called_once_with(3, for_update=True)
        self.db.commit.assert_called_once()

    def test_missing_or_inactive_reference_rolls_back(self):
        for reference, error in (
            (None, ProductReferenceNotFoundError),
            (SimpleNamespace(estado=False), ProductReferenceInactiveError),
        ):
            with self.subTest(error=error):
                self.repo.get_category.return_value = reference
                with self.assertRaises(error):
                    self.service.create_product(
                        ProductCreateRequest(
                            id_categoria=2,
                            nombre="Camisa",
                            seccion="HOMBRE",
                            precio=1,
                        )
                    )
                self.db.rollback.assert_called()

    def test_variant_duplicate_sku_or_combination_is_rejected(self):
        payload = ProductVariantCreateRequest(id_talla=4, id_color=5, sku="sku-1")
        self.repo.get_variant_by_sku.return_value = SimpleNamespace()
        with self.assertRaisesRegex(ProductConflictError, "SKU"):
            self.service.create_variant(product_id=7, payload=payload)
        self.repo.get_variant_by_sku.return_value = None
        self.repo.get_variant_by_combination.return_value = SimpleNamespace()
        with self.assertRaisesRegex(ProductConflictError, "talla"):
            self.service.create_variant(product_id=7, payload=payload)
        self.db.commit.assert_not_called()
        self.repo.create_variant.assert_not_called()

    def test_variant_update_and_reactivation_validate_master_data(self):
        variant = SimpleNamespace(
            id_variante_producto=11,
            id_talla=4,
            id_color=5,
            sku="OLD",
            estado=False,
        )
        self.repo.get_variant.return_value = variant
        self.repo.get_variant_detail.return_value = variant_detail(sku="NEW")
        result = self.service.update_variant(
            product_id=7,
            variant_id=11,
            payload=ProductVariantUpdateRequest(sku="new"),
        )
        self.assertEqual(result.sku, "NEW")
        self.repo.update_variant.assert_called_with(variant, sku="NEW")
        self.service.update_variant_status(
            product_id=7,
            variant_id=11,
            payload=ProductVariantStatusUpdateRequest(estado=True),
        )
        self.repo.get_size.assert_called_with(4, for_update=True)
        self.repo.get_color.assert_called_with(5, for_update=True)

    def test_inactive_supplier_association_is_reactivated(self):
        association = SimpleNamespace(
            id_producto_proveedor=12,
            id_proveedor=6,
            estado=False,
            costo_referencia=None,
        )
        self.repo.get_product_supplier.return_value = association
        self.repo.list_suppliers.return_value = []
        result = self.service.add_suppliers(
            product_id=7,
            payload=ProductSuppliersRequest(
                proveedores=[
                    ProductSupplierItemRequest(
                        id_proveedor=6, costo_referencia="22.50"
                    )
                ]
            ),
        )
        self.assertEqual(result, [])
        self.repo.create_product_supplier.assert_not_called()
        self.repo.update_product_supplier.assert_called_once_with(
            association, costo_referencia=Decimal("22.50"), estado=True
        )
        self.db.commit.assert_called_once()

    def test_first_image_is_primary_and_no_physical_delete_occurs(self):
        image = SimpleNamespace(
            id_imagen_producto=20,
            url_imagen="https://cdn.test/a.jpg",
            es_principal=True,
            created_at=NOW,
        )
        self.repo.has_images.return_value = False
        self.repo.create_image.return_value = image
        result = self.service.create_image(
            product_id=7,
            payload=ProductImageCreateRequest(
                url_imagen="https://cdn.test/a.jpg", es_principal=False
            ),
        )
        self.assertTrue(result.es_principal)
        self.repo.clear_primary_images.assert_called_once_with(7)
        self.repo.create_image.assert_called_once_with(
            product_id=7,
            image_url="https://cdn.test/a.jpg",
            is_primary=True,
        )
        self.db.delete.assert_not_called()

    def test_uploads_valid_image_and_persists_only_public_url(self):
        storage = MagicMock()
        storage.upload_public_image.return_value = StoredObject(
            path="products/7/unique.png",
            public_url=(
                "https://project.supabase.co/storage/v1/object/public/"
                "product-images/products/7/unique.png"
            ),
        )
        self.service.storage_client = storage
        self.repo.has_images.return_value = False
        image = SimpleNamespace(
            id_imagen_producto=20,
            url_imagen=storage.upload_public_image.return_value.public_url,
            es_principal=True,
            created_at=NOW,
        )
        self.repo.create_image.return_value = image

        result = self.service.upload_image(
            product_id=7,
            filename="look.png",
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\nvalid-image",
            is_primary=False,
        )

        self.assertEqual(result.url_imagen, image.url_imagen)
        uploaded = storage.upload_public_image.call_args.kwargs
        self.assertRegex(uploaded["object_path"], r"^products/7/[0-9a-f]{32}\.png$")
        self.assertEqual(uploaded["content_type"], "image/png")
        self.repo.create_image.assert_called_once_with(
            product_id=7,
            image_url=image.url_imagen,
            is_primary=True,
        )
        self.db.commit.assert_called_once()
        storage.remove.assert_not_called()

    def test_upload_rejects_extension_mime_size_and_forged_content(self):
        cases = (
            ("look.gif", "image/gif", b"GIF89a"),
            ("look.png", "image/jpeg", b"\x89PNG\r\n\x1a\n"),
            ("look.webp", "image/webp", b"not-a-webp"),
            ("look.jpg", "image/jpeg", b""),
            (
                "look.png",
                "image/png",
                b"\x89PNG\r\n\x1a\n"
                + b"x" * AdminProductService.MAX_IMAGE_SIZE_BYTES,
            ),
        )
        for filename, mime, content in cases:
            with self.subTest(filename=filename, mime=mime), self.assertRaises(
                ProductImageValidationError
            ):
                self.service.upload_image(
                    product_id=7,
                    filename=filename,
                    content_type=mime,
                    content=content,
                    is_primary=False,
                )
        self.repo.create_image.assert_not_called()
        self.db.commit.assert_not_called()

    def test_database_failure_removes_just_uploaded_storage_object(self):
        storage = MagicMock()
        stored = StoredObject(
            path="products/7/unique.jpg",
            public_url="https://project.supabase.co/public/unique.jpg",
        )
        storage.upload_public_image.return_value = stored
        self.service.storage_client = storage
        self.repo.has_images.return_value = True
        self.repo.create_image.side_effect = SQLAlchemyError("private")

        with self.assertRaises(AdminProductPersistenceError):
            self.service.upload_image(
                product_id=7,
                filename="look.jpg",
                content_type="image/jpeg",
                content=b"\xff\xd8\xffvalid-image",
                is_primary=False,
            )

        self.db.rollback.assert_called_once()
        storage.remove.assert_called_once_with(stored.path)

    def test_write_failure_rolls_back_and_hides_database_error(self):
        self.repo.create_product.side_effect = SQLAlchemyError("private details")
        with self.assertRaises(AdminProductPersistenceError):
            self.service.create_product(
                ProductCreateRequest(
                    id_categoria=2,
                    nombre="Camisa",
                    seccion="HOMBRE",
                    precio=1,
                )
            )
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()


class ProductRouteTests(TestCase):
    def test_all_routes_are_registered_and_protected(self):
        registered = {
            (method, route.path)
            for route in routes.router.routes
            for method in route.methods
        }
        self.assertEqual(
            registered,
            {
                ("GET", "/api/admin/products"),
                ("POST", "/api/admin/products"),
                ("GET", "/api/admin/products/{id_producto}"),
                ("PATCH", "/api/admin/products/{id_producto}"),
                ("PATCH", "/api/admin/products/{id_producto}/status"),
                ("POST", "/api/admin/products/{id_producto}/variants"),
                ("PATCH", "/api/admin/products/{id_producto}/variants/{id_variante_producto}"),
                ("PATCH", "/api/admin/products/{id_producto}/variants/{id_variante_producto}/status"),
                ("POST", "/api/admin/products/{id_producto}/collections"),
                ("POST", "/api/admin/products/{id_producto}/suppliers"),
                ("PATCH", "/api/admin/products/{id_producto}/suppliers/{id_producto_proveedor}"),
                ("PATCH", "/api/admin/products/{id_producto}/suppliers/{id_producto_proveedor}/status"),
                ("POST", "/api/admin/products/{id_producto}/images"),
                ("POST", "/api/admin/products/{id_producto}/images/upload"),
                ("PATCH", "/api/admin/products/{id_producto}/images/{id_imagen_producto}"),
            },
        )
        from app.main import app

        openapi = app.openapi()
        for path, operations in openapi["paths"].items():
            if path.startswith("/api/admin/products"):
                for operation in operations.values():
                    self.assertTrue(operation["security"])
        params = openapi["paths"]["/api/admin/products"]["get"]["parameters"]
        self.assertEqual(
            next(item for item in params if item["name"] == "page_size")["schema"][
                "maximum"
            ],
            100,
        )

    def test_denied_access_stops_base_endpoints(self):
        denied = JSONResponse(status_code=403, content={"success": False})
        with patch.object(routes, "AdminProductService") as service:
            calls = [
                routes.list_products(administrator=denied, db=MagicMock()),
                routes.get_product(7, administrator=denied, db=MagicMock()),
                routes.create_product(
                    ProductCreateRequest(
                        id_categoria=1,
                        nombre="A",
                        seccion="HOMBRE",
                        precio=1,
                    ),
                    administrator=denied,
                    db=MagicMock(),
                ),
                routes.update_product_status(
                    7,
                    ProductStatusUpdateRequest(estado=False),
                    administrator=denied,
                    db=MagicMock(),
                ),
            ]
            self.assertTrue(all(item is denied for item in calls))
            service.assert_not_called()

    def test_domain_errors_have_safe_http_codes(self):
        cases = (
            (ProductNotFoundError("Producto no encontrado"), 404),
            (ProductReferenceInactiveError("Categoria inactiva"), 422),
            (ProductImageValidationError("Archivo invalido"), 422),
            (ProductConflictError("El SKU ya esta registrado"), 409),
            (ProductImageStorageError("Storage no disponible"), 502),
            (ProductImageStorageConfigurationError("Falta configurar"), 503),
            (AdminProductPersistenceError("private"), 500),
            (IntegrityError("query", {}, Exception("private")), 500),
        )
        for error, expected in cases:
            with self.subTest(error=error):
                response = routes._error_response(error)
                self.assertEqual(response.status_code, expected)
                if expected == 500:
                    self.assertNotIn(b"private", response.body)
