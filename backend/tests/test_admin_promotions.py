"""Pruebas unitarias de CU11 sin conectarse a PostgreSQL/Supabase."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.repositories.admin_promotions import AdminPromotionRepository
from app.routers import admin_promotions as routes
from app.schemas.admin_promotions import (
    PromotionCreateRequest,
    PromotionProductsRequest,
    PromotionStatusUpdateRequest,
    PromotionUpdateRequest,
)
from app.services.admin_promotions import (
    AdminPromotionPersistenceError,
    AdminPromotionService,
    PromotionBusinessRuleError,
    PromotionConflictError,
    PromotionNotFoundError,
    PromotionProductInactiveError,
    PromotionProductNotFoundError,
)


NOW = datetime.now(timezone.utc).replace(tzinfo=None)


def promotion_record(**changes):
    values = {
        "id_promocion": 7,
        "nombre": "Semana Denim",
        "codigo": "DENIM20",
        "descripcion": "Descuento global",
        "tipo_descuento": "PORCENTAJE",
        "valor": Decimal("20.00"),
        "fecha_inicio": NOW - timedelta(days=1),
        "fecha_fin": NOW + timedelta(days=1),
        "acumulable": False,
        "estado": True,
        "total_productos": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def promotion_row(**changes):
    return vars(promotion_record(**changes)).copy()


def product_row(product_id=11):
    return {
        "id_promocion_producto": 30,
        "id_producto": product_id,
        "nombre": "Jean recto",
        "seccion": "UNISEX",
        "precio": Decimal("59.90"),
        "estado": True,
    }


class PromotionSchemaTests(TestCase):
    def test_create_normalizes_and_validates_contract(self):
        payload = PromotionCreateRequest(
            nombre=" Semana Denim ",
            codigo=" denim20 ",
            descripcion=" Global ",
            tipo_descuento="PORCENTAJE",
            valor="20.50",
            fecha_inicio="2026-09-01T04:00:00-04:00",
            fecha_fin="2026-09-30T08:00:00Z",
        )
        self.assertEqual(payload.nombre, "Semana Denim")
        self.assertEqual(payload.codigo, "DENIM20")
        self.assertEqual(payload.descripcion, "Global")
        self.assertIsNone(payload.fecha_inicio.tzinfo)
        self.assertEqual(payload.fecha_inicio.hour, 8)
        self.assertFalse(payload.acumulable)

    def test_discount_dates_and_extra_fields_are_rejected(self):
        valid = {
            "nombre": "Promo",
            "tipo_descuento": "MONTO_FIJO",
            "valor": "10.00",
            "fecha_inicio": "2026-09-01T00:00:00",
            "fecha_fin": "2026-09-02T00:00:00",
        }
        invalid = (
            {**valid, "tipo_descuento": "OTRO"},
            {**valid, "valor": 0},
            {**valid, "tipo_descuento": "PORCENTAJE", "valor": 101},
            {
                **valid,
                "fecha_inicio": "2026-09-03T00:00:00",
                "fecha_fin": "2026-09-02T00:00:00",
            },
            {**valid, "id_sucursal": 1},
            {**valid, "estado": False},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                PromotionCreateRequest(**values)

    def test_patch_and_product_ids_are_strict(self):
        self.assertEqual(
            PromotionUpdateRequest(codigo=None).model_dump(exclude_unset=True),
            {"codigo": None},
        )
        for values in ({}, {"nombre": None}, {"valor": None}, {"estado": False}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                PromotionUpdateRequest(**values)
        for ids in ([], [0], [1, 1]):
            with self.subTest(ids=ids), self.assertRaises(ValidationError):
                PromotionProductsRequest(id_productos=ids)


class PromotionRepositoryTests(TestCase):
    def test_list_search_state_validity_and_pagination(self):
        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        db.scalar.return_value = 0
        result = AdminPromotionRepository(db).list_promotions(
            search=" %_\\ ",
            state=False,
            validity="VIGENTE",
            page=2,
            page_size=3,
        )
        self.assertEqual(result, ([], 0))
        statement = db.execute.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        sql = str(statement)
        self.assertIn("t_promocion.nombre ILIKE", sql)
        self.assertIn("t_promocion.codigo ILIKE", sql)
        self.assertIn("t_promocion.descripcion ILIKE", sql)
        self.assertIn("t_promocion.estado IS false", sql)
        self.assertIn("t_promocion.fecha_inicio <= now()", sql)
        self.assertIn("t_promocion.fecha_fin >= now()", sql)
        self.assertIn("ORDER BY t_promocion.nombre, t_promocion.id_promocion", sql)
        self.assertIn("%\\%\\_\\\\%", statement.params.values())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        search_values = [v for v in statement.params.values() if isinstance(v, str)]
        self.assertTrue(any(v in count.params.values() for v in search_values))

    def test_mutations_flush_without_commit_or_delete(self):
        db = MagicMock()
        repository = AdminPromotionRepository(db)
        promotion = repository.create_promotion(
            nombre="Promo",
            codigo=None,
            descripcion=None,
            tipo_descuento="MONTO_FIJO",
            valor=Decimal("10.00"),
            fecha_inicio=NOW,
            fecha_fin=NOW,
            acumulable=False,
        )
        repository.add_product(7, 11)
        repository.update_status(promotion, state=False)
        self.assertTrue(promotion.created_at is None or promotion.estado is False)
        self.assertEqual(db.add.call_count, 2)
        self.assertEqual(db.flush.call_count, 3)
        db.commit.assert_not_called()
        db.delete.assert_not_called()

    def test_write_lookups_use_for_update(self):
        db = MagicMock()
        repository = AdminPromotionRepository(db)
        repository.get_by_id(7, for_update=True)
        promotion_query = db.scalar.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        repository.get_product(11, for_update=True)
        product_query = db.scalar.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        self.assertIn("FOR UPDATE", str(promotion_query))
        self.assertIn("FOR UPDATE", str(product_query))

        repository.get_by_code("denim20", for_update=True)
        code_query = db.scalar.call_args.args[0].compile(
            dialect=postgresql.dialect()
        )
        self.assertIn("lower(t_promocion.codigo)", str(code_query))


class PromotionServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminPromotionService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.promotion = promotion_record()
        self.repo.get_by_id.return_value = self.promotion
        self.repo.get_summary.return_value = promotion_row()
        self.repo.list_products.return_value = [product_row()]
        self.repo.get_by_code.return_value = None
        self.repo.get_association.return_value = None
        self.repo.get_product.return_value = SimpleNamespace(estado=True)

    def test_list_detail_and_temporal_validity(self):
        self.repo.list_promotions.return_value = (
            [
                promotion_row(
                    id_promocion=1,
                    fecha_inicio=NOW + timedelta(days=2),
                    fecha_fin=NOW + timedelta(days=3),
                ),
                promotion_row(
                    id_promocion=2,
                    fecha_inicio=NOW - timedelta(days=3),
                    fecha_fin=NOW - timedelta(days=2),
                ),
            ],
            3,
        )
        data, pagination = self.service.list_promotions(
            search="denim",
            state=True,
            validity="PROGRAMADA",
            page=2,
            page_size=2,
        )
        self.assertEqual([item.vigencia for item in data], ["PROGRAMADA", "EXPIRADA"])
        self.assertEqual(pagination.total_pages, 2)
        self.assertEqual(self.service.get_promotion(7).productos[0].id_producto, 11)

    def test_create_checks_code_and_commits(self):
        self.repo.create_promotion.return_value = self.promotion
        result = self.service.create_promotion(
            PromotionCreateRequest(
                nombre="Promo",
                codigo=" denim20 ",
                tipo_descuento="PORCENTAJE",
                valor=20,
                fecha_inicio=NOW,
                fecha_fin=NOW,
            )
        )
        self.repo.get_by_code.assert_called_once_with(
            "DENIM20", exclude_promotion_id=None, for_update=True
        )
        self.assertEqual(result.id_promocion, 7)
        self.db.commit.assert_called_once()

    def test_partial_update_validates_merged_dates_and_discount(self):
        self.promotion.tipo_descuento = "MONTO_FIJO"
        self.promotion.valor = Decimal("150")
        with self.assertRaises(PromotionBusinessRuleError):
            self.service.update_promotion(
                promotion_id=7,
                payload=PromotionUpdateRequest(tipo_descuento="PORCENTAJE"),
            )
        self.db.rollback.assert_called()
        self.repo.update_promotion.assert_not_called()

        self.promotion.valor = Decimal("20")
        with self.assertRaises(PromotionBusinessRuleError):
            self.service.update_promotion(
                promotion_id=7,
                payload=PromotionUpdateRequest(
                    fecha_inicio=self.promotion.fecha_fin + timedelta(days=1)
                ),
            )
        self.repo.update_promotion.assert_not_called()

    def test_status_is_logical_and_locked(self):
        self.repo.update_status.side_effect = lambda item, state: setattr(
            item, "estado", state
        )
        self.repo.get_summary.side_effect = lambda _promotion_id: promotion_row(
            estado=self.promotion.estado
        )
        result = self.service.update_status(
            promotion_id=7,
            payload=PromotionStatusUpdateRequest(estado=False),
        )
        self.repo.get_by_id.assert_called_with(7, for_update=True)
        self.repo.update_status.assert_called_once_with(self.promotion, state=False)
        self.assertFalse(result.estado)
        self.db.delete.assert_not_called()
        self.db.commit.assert_called_once()

    def test_association_rejects_missing_inactive_and_existing_products(self):
        cases = (
            (None, None, PromotionProductNotFoundError),
            (SimpleNamespace(estado=False), None, PromotionProductInactiveError),
            (SimpleNamespace(estado=True), SimpleNamespace(), PromotionConflictError),
        )
        for product, association, error in cases:
            with self.subTest(error=error):
                self.repo.get_product.return_value = product
                self.repo.get_association.return_value = association
                with self.assertRaises(error):
                    self.service.add_products(
                        promotion_id=7,
                        payload=PromotionProductsRequest(id_productos=[11]),
                    )
                self.db.rollback.assert_called()
        self.repo.add_product.assert_not_called()
        self.db.commit.assert_not_called()

    def test_association_is_atomic_and_commits(self):
        result = self.service.add_products(
            promotion_id=7,
            payload=PromotionProductsRequest(id_productos=[11, 12]),
        )
        self.assertEqual(self.repo.get_product.call_count, 2)
        self.assertEqual(self.repo.add_product.call_count, 2)
        self.assertEqual(result[0].id_producto, 11)
        self.db.commit.assert_called_once()

    def test_conflicts_and_database_errors_rollback(self):
        self.repo.get_by_code.return_value = self.promotion
        with self.assertRaises(PromotionConflictError):
            self.service.create_promotion(
                PromotionCreateRequest(
                    nombre="Promo",
                    codigo="DENIM20",
                    tipo_descuento="MONTO_FIJO",
                    valor=10,
                    fecha_inicio=NOW,
                    fecha_fin=NOW,
                )
            )
        self.db.rollback.assert_called()

        self.repo.get_by_code.return_value = None
        self.repo.create_promotion.side_effect = SQLAlchemyError("private")
        with self.assertRaises(AdminPromotionPersistenceError):
            self.service.create_promotion(
                PromotionCreateRequest(
                    nombre="Promo",
                    tipo_descuento="MONTO_FIJO",
                    valor=10,
                    fecha_inicio=NOW,
                    fecha_fin=NOW,
                )
            )


class PromotionRouteTests(TestCase):
    def test_routes_are_registered_protected_and_paginated(self):
        registered = {
            (method, route.path)
            for route in routes.router.routes
            for method in route.methods
        }
        self.assertEqual(
            registered,
            {
                ("GET", "/api/admin/promotions"),
                ("POST", "/api/admin/promotions"),
                ("GET", "/api/admin/promotions/{id_promocion}"),
                ("PATCH", "/api/admin/promotions/{id_promocion}"),
                ("PATCH", "/api/admin/promotions/{id_promocion}/status"),
                ("GET", "/api/admin/promotions/{id_promocion}/products"),
                ("POST", "/api/admin/promotions/{id_promocion}/products"),
            },
        )
        from app.main import app

        openapi = app.openapi()
        for path, operations in openapi["paths"].items():
            if path.startswith("/api/admin/promotions"):
                for operation in operations.values():
                    self.assertTrue(operation["security"])
        params = openapi["paths"]["/api/admin/promotions"]["get"]["parameters"]
        self.assertEqual(
            next(item for item in params if item["name"] == "page_size")["schema"][
                "maximum"
            ],
            100,
        )
        validity = next(item for item in params if item["name"] == "vigencia")
        schema = validity["schema"]["anyOf"][0]
        self.assertEqual(set(schema["enum"]), {"PROGRAMADA", "VIGENTE", "EXPIRADA"})

    def test_denied_access_stops_every_endpoint(self):
        denied = JSONResponse(status_code=403, content={"success": False})
        create = PromotionCreateRequest(
            nombre="Promo",
            tipo_descuento="MONTO_FIJO",
            valor=10,
            fecha_inicio=NOW,
            fecha_fin=NOW,
        )
        with patch.object(routes, "AdminPromotionService") as service:
            calls = (
                routes.list_promotions(administrator=denied, db=MagicMock()),
                routes.get_promotion(7, administrator=denied, db=MagicMock()),
                routes.create_promotion(create, administrator=denied, db=MagicMock()),
                routes.update_promotion(
                    7,
                    PromotionUpdateRequest(nombre="Otra"),
                    administrator=denied,
                    db=MagicMock(),
                ),
                routes.update_promotion_status(
                    7,
                    PromotionStatusUpdateRequest(estado=False),
                    administrator=denied,
                    db=MagicMock(),
                ),
                routes.list_promotion_products(
                    7, administrator=denied, db=MagicMock()
                ),
                routes.add_promotion_products(
                    7,
                    PromotionProductsRequest(id_productos=[11]),
                    administrator=denied,
                    db=MagicMock(),
                ),
            )
            self.assertTrue(all(item is denied for item in calls))
            service.assert_not_called()

    def test_errors_use_safe_http_statuses(self):
        cases = (
            (PromotionNotFoundError("Promocion no encontrada"), 404),
            (PromotionProductNotFoundError("Producto no encontrado"), 404),
            (PromotionProductInactiveError("Producto inactivo"), 422),
            (PromotionBusinessRuleError("Fechas invalidas"), 422),
            (PromotionConflictError("Duplicado"), 409),
            (AdminPromotionPersistenceError("private"), 500),
            (IntegrityError("query", {}, Exception("private")), 500),
        )
        for error, expected in cases:
            with self.subTest(error=error):
                response = routes._error_response(error)
                self.assertEqual(response.status_code, expected)
                if expected == 500:
                    self.assertNotIn(b"private", response.body)
