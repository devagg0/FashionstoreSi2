"""Pruebas unitarias de CU12 sin conectar ni modificar PostgreSQL."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.catalog import CatalogRepository
from app.routers import catalog as routes
from app.services.catalog import (
    CatalogFilterError,
    CatalogProductNotFoundError,
    CatalogReferenceInactiveError,
    CatalogReferenceNotFoundError,
    CatalogService,
)


NOW = datetime(2026, 9, 8, 12, 0, 0)


def product_row(**changes):
    values = {
        "id_producto": 7,
        "nombre": "Chaqueta",
        "descripcion": "Chaqueta ligera",
        "seccion": "UNISEX",
        "id_categoria": 2,
        "categoria": "Chaquetas",
        "precio_base": Decimal("100.00"),
        "precio_final": Decimal("75.00"),
        "precio_resultante": Decimal("75.00"),
        "imagen_principal": "https://cdn.test/principal.jpg",
        "id_promocion": 4,
        "promocion_nombre": "Oferta",
        "promocion_codigo": None,
        "promocion_descripcion": None,
        "tipo_descuento": "PORCENTAJE",
        "valor_descuento": Decimal("25.00"),
        "fecha_inicio": NOW,
        "fecha_fin": NOW,
        "acumulable": False,
    }
    values.update(changes)
    return values


def variant_row(**changes):
    values = {
        "id_producto": 7,
        "id_variante_producto": 11,
        "sku": "CHA-M-NEG",
        "id_talla": 3,
        "talla": "M",
        "id_color": 5,
        "color": "Negro",
        "codigo_hex": "#000000",
        "stock_actual": 8,
        "stock_reservado": 3,
    }
    values.update(changes)
    return values


class CatalogRepositoryTests(TestCase):
    def test_query_uses_active_products_variants_promotions_and_branch_stock(self):
        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        db.scalar.return_value = 0
        repository = CatalogRepository(db)
        self.assertEqual(
            repository.list_products(
                search=" %_\\ ",
                section="HOMBRE",
                category_id=2,
                size_id=3,
                color_id=4,
                min_price=Decimal("10"),
                max_price=Decimal("100"),
                on_promotion=True,
                branch_id=5,
                city_id=None,
                sort="precio_asc",
                page=2,
                page_size=10,
            ),
            ([], 0),
        )
        query = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(query)
        self.assertIn("t_producto.estado IS true", sql)
        self.assertIn("t_variante_producto.estado IS true", sql)
        self.assertIn("t_promocion.estado IS true", sql)
        self.assertIn("t_promocion.fecha_inicio <= now()", sql)
        self.assertIn("stock_actual - t_inventario_sucursal.stock_reservado", sql)
        self.assertIn("row_number() OVER", sql)
        self.assertIn("greatest", sql)
        self.assertIn("ORDER BY coalesce", sql)
        self.assertIn("%\\%\\_\\\\%", query.params.values())

    def test_detail_queries_are_stable_and_only_use_active_variants(self):
        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        repository = CatalogRepository(db)
        repository.list_active_variants([7], branch_id=2)
        variant_query = db.execute.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        self.assertIn("t_variante_producto.estado IS true", str(variant_query))
        self.assertIn("LEFT OUTER JOIN t_inventario_sucursal", str(variant_query))

        repository.list_images(7)
        image_query = db.execute.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        self.assertIn(
            "ORDER BY t_imagen_producto.es_principal DESC, "
            "t_imagen_producto.id_imagen_producto",
            str(image_query),
        )


class CatalogServiceTests(TestCase):
    def setUp(self):
        self.service = CatalogService(MagicMock())
        self.repo = self.service.repository = MagicMock()
        self.repo.get_branch.return_value = SimpleNamespace(
            id_sucursal=2, id_ciudad=1, nombre="Centro", estado=True
        )
        self.repo.get_city.return_value = SimpleNamespace(id_ciudad=1, estado=True)

    def test_list_calculates_best_promotion_facets_and_availability(self):
        self.repo.list_products.return_value = ([product_row()], 1)
        self.repo.list_active_variants.return_value = [variant_row()]
        data, pagination = self.service.list_products(
            search=None,
            section=None,
            category_id=None,
            size_id=None,
            color_id=None,
            min_price=None,
            max_price=None,
            on_promotion=None,
            branch_id=2,
            city_id=None,
            sort="recientes",
            page=1,
            page_size=20,
        )
        item = data[0]
        self.assertEqual(item.precio_final, Decimal("75.00"))
        self.assertEqual(item.monto_descuento, Decimal("25.00"))
        self.assertEqual(item.porcentaje_descuento, Decimal("25.00"))
        self.assertEqual(item.disponibilidad_sucursal.cantidad_disponible, 5)
        self.assertEqual(item.tallas_disponibles[0].nombre, "M")
        self.assertEqual(item.colores_disponibles[0].nombre, "Negro")
        self.assertEqual(pagination.total_pages, 1)

    def test_detail_returns_all_promotions_and_chooses_lowest_price(self):
        detail = product_row(id_temporada=8, temporada="Invierno")
        self.repo.get_active_product.return_value = detail
        self.repo.list_active_variants.return_value = [variant_row()]
        self.repo.list_current_promotions.return_value = [
            product_row(precio_resultante=Decimal("60.00")),
            product_row(
                id_promocion=5,
                promocion_nombre="Monto fijo",
                tipo_descuento="MONTO_FIJO",
                valor_descuento=Decimal("20.00"),
                precio_resultante=Decimal("80.00"),
            ),
        ]
        self.repo.list_images.return_value = [
            {
                "id_imagen_producto": 1,
                "url_imagen": "https://cdn.test/principal.jpg",
                "es_principal": True,
            }
        ]
        self.repo.list_active_collections.return_value = [
            {"id_coleccion": 9, "nombre": "Urban"}
        ]
        result = self.service.get_product(7, branch_id=2)
        self.assertEqual(len(result.promociones_vigentes), 2)
        self.assertEqual(result.promocion_destacada.id_promocion, 4)
        self.assertEqual(result.precio_final, Decimal("60.00"))
        self.assertEqual(result.variantes[0].disponibilidad_sucursal.cantidad_disponible, 5)
        self.assertEqual(result.imagen_principal, result.galeria[0].url_imagen)

    def test_location_validation_distinguishes_missing_inactive_and_mismatch(self):
        self.repo.get_branch.return_value = None
        with self.assertRaises(CatalogReferenceNotFoundError):
            self.service._validate_location(branch_id=2, city_id=None)
        self.repo.get_branch.return_value = SimpleNamespace(
            id_ciudad=1, nombre="Centro", estado=False
        )
        with self.assertRaises(CatalogReferenceInactiveError):
            self.service._validate_location(branch_id=2, city_id=None)
        self.repo.get_branch.return_value = SimpleNamespace(
            id_ciudad=2, nombre="Norte", estado=True
        )
        with self.assertRaises(CatalogFilterError):
            self.service._validate_location(branch_id=2, city_id=1)

    def test_inactive_or_missing_product_is_not_exposed(self):
        self.repo.get_active_product.return_value = None
        with self.assertRaises(CatalogProductNotFoundError):
            self.service.get_product(999, branch_id=None)


class CatalogRouteTests(TestCase):
    def test_routes_are_public_typed_and_paginated(self):
        registered = {
            (method, route.path)
            for route in routes.router.routes
            for method in route.methods
        }
        self.assertEqual(
            registered,
            {
                ("GET", "/api/catalog/products"),
                ("GET", "/api/catalog/products/{id_producto}"),
            },
        )
        from app.main import app

        openapi = app.openapi()
        operations = openapi["paths"]["/api/catalog/products"]
        self.assertIsNone(operations["get"].get("security"))
        self.assertIsNone(
            openapi["paths"]["/api/catalog/products/{id_producto}"]["get"].get(
                "security"
            )
        )
        params = operations["get"]["parameters"]
        page_size = next(item for item in params if item["name"] == "page_size")
        self.assertEqual(page_size["schema"]["maximum"], 100)
        sort = next(item for item in params if item["name"] == "sort")
        self.assertEqual(
            set(sort["schema"]["enum"]),
            {"recientes", "precio_asc", "precio_desc", "nombre"},
        )

    def test_route_validates_price_range_before_query(self):
        with patch.object(routes, "CatalogService") as service:
            response = routes.list_catalog_products(
                search=None,
                seccion=None,
                id_categoria=None,
                id_talla=None,
                id_color=None,
                precio_min=Decimal("20"),
                precio_max=Decimal("10"),
                en_promocion=None,
                id_sucursal=None,
                id_ciudad=None,
                sort="recientes",
                page=1,
                page_size=20,
                db=MagicMock(),
            )
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 422)
        service.assert_not_called()

    def test_database_errors_do_not_leak_details(self):
        response = routes._error_response(SQLAlchemyError("private database data"))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b"private", response.body)
