"""Pruebas CategoryU07 sin conectar ni modificar la base de datos."""
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.repositories.admin_category_repository import AdminCategoryRepository
from app.services.admin_category_service import AdminCategoryService, CategoryNameDuplicateError, CategoryNotFoundError, AdminCategoryPersistenceError
from app.schemas.admin_category import CategoryCreateRequest, CategoryUpdateRequest, CategoryStatusUpdateRequest
from app.routers import admin_categories as routes


def record():
    return SimpleNamespace(id_categoria=7, nombre="Base", descripcion=None, estado=True,
                           created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))


class SchemaTests(TestCase):
    def test_normalization_and_lengths(self):
        self.assertEqual(CategoryCreateRequest(nombre=" Base ", descripcion=" abc ").model_dump(),
                         {"nombre": "Base", "descripcion": "abc"})
        for values in ({}, {"nombre": " "}, {"nombre": None}, {"nombre": "x" * (100+1)},
                       {"nombre": "Base", "descripcion": "x" * (200+1)}, {"nombre": "Base", "estado": False},
                       {"nombre": "Base", "id_sucursal": 1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                CategoryCreateRequest(**values)
        self.assertEqual(len(CategoryCreateRequest(nombre="x" * 100, descripcion="x" * 200).nombre), 100)

    def test_patch(self):
        self.assertEqual(CategoryUpdateRequest(descripcion=None).model_dump(exclude_unset=True), {"descripcion": None})
        for values in ({}, {"nombre": None}, {"estado": False}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                CategoryUpdateRequest(**values)


class ServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminCategoryService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.item = record()
        self.repo.get_by_id.return_value = self.item
        self.repo.get_by_name.return_value = None
        self.repo.create.return_value = self.item
        self.repo.update.side_effect = lambda item, **values: item.__dict__.update(values)
        self.repo.update_status.side_effect = lambda item, state: setattr(item, "estado", state)

    def test_create(self):
        result = self.service.create_category(CategoryCreateRequest(nombre=" Base "))
        self.repo.create.assert_called_once_with(nombre="Base", descripcion=None)
        self.assertTrue(result.estado)
        self.db.commit.assert_called_once()

    def test_duplicate_create_and_update(self):
        self.repo.get_by_name.return_value = self.item
        with self.assertRaises(CategoryNameDuplicateError):
            self.service.create_category(CategoryCreateRequest(nombre="base"))
        with self.assertRaises(CategoryNameDuplicateError):
            self.service.update_category(category_id=7, payload=CategoryUpdateRequest(nombre="BASE"))
        self.repo.create.assert_not_called()
        self.repo.update.assert_not_called()
        self.assertEqual(self.db.rollback.call_count, 2)

    def test_list_search_state_pagination(self):
        self.repo.list_categories.return_value = ([self.item], 3)
        data, pagination = self.service.list_categories(search="ba", state=False, page=2, page_size=2)
        self.repo.list_categories.assert_called_once_with(search="ba", state=False, page=2, page_size=2)
        self.assertEqual(data[0].id_categoria, 7)
        self.assertEqual(pagination.model_dump(), {"page": 2, "page_size": 2, "total": 3, "total_pages": 2})

    def test_detail_and_partial_update(self):
        self.assertEqual(self.service.get_category(7).nombre, "Base")
        result = self.service.update_category(category_id=7, payload=CategoryUpdateRequest(descripcion=" abc "))
        self.assertEqual(result.descripcion, "abc")
        self.assertEqual(result.nombre, "Base")
        self.repo.get_by_name.assert_not_called()
        result = self.service.update_category(category_id=7, payload=CategoryUpdateRequest(descripcion=None))
        self.assertIsNone(result.descripcion)
        self.service.update_category(category_id=7, payload=CategoryUpdateRequest(nombre="BASE"))
        self.repo.get_by_name.assert_called_once_with("BASE", exclude_category_id=7)

    def test_deactivate_and_reactivate(self):
        for state in (False, True):
            result = self.service.update_status(category_id=7, payload=CategoryStatusUpdateRequest(estado=state))
            self.assertEqual(result.estado, state)
        self.db.delete.assert_not_called()
        self.assertEqual(result.created_at, datetime(2026, 1, 1))
        self.assertEqual(result.updated_at, datetime(2026, 1, 1))

    def test_missing(self):
        self.repo.get_by_id.return_value = None
        for operation in (lambda: self.service.get_category(999),
                          lambda: self.service.update_category(category_id=999, payload=CategoryUpdateRequest(nombre="Other")),
                          lambda: self.service.update_status(category_id=999, payload=CategoryStatusUpdateRequest(estado=False))):
            with self.assertRaises(CategoryNotFoundError):
                operation()

    def test_persistence_rollback(self):
        self.db.commit.side_effect = SQLAlchemyError("failure")
        with self.assertRaises(AdminCategoryPersistenceError):
            self.service.create_category(CategoryCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()

    def test_integrity_conflict(self):
        self.repo.get_by_name.side_effect = [None, self.item]
        self.repo.create.side_effect = IntegrityError("insert", {}, Exception())
        with self.assertRaises(CategoryNameDuplicateError):
            self.service.create_category(CategoryCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()


class RepositoryTests(TestCase):
    def test_filters_escaped_search_and_order(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        db.scalar.return_value = 0
        repository = AdminCategoryRepository(db)
        self.assertEqual(repository.list_categories(search=" %_\\ ", state=False, page=2, page_size=3), ([], 0))
        statement = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(statement)
        self.assertIn("ILIKE", sql)
        self.assertIn("estado IS false", sql)
        self.assertIn("ORDER BY t_categoria.nombre, t_categoria.id_categoria", sql)
        self.assertIn("%\\%\\_\\\\%", statement.params.values())
        self.assertIn(3, statement.params.values())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertEqual(count.params['nombre_1'], statement.params['nombre_1'])

    def test_duplicate_comparison(self):
        db = MagicMock()
        AdminCategoryRepository(db).get_by_name("BASE", exclude_category_id=7)
        query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("lower(t_categoria.nombre)", str(query))
        self.assertIn("base", query.params.values())
        self.assertIn("!=", str(query))


class RouteTests(TestCase):
    def test_routes_and_pagination_limit(self):
        registered = {(method, route.path) for route in routes.router.routes for method in route.methods}
        self.assertEqual(registered, {("GET", "/api/admin/categories"), ("POST", "/api/admin/categories"),
            ("GET", "/api/admin/categories/{id_categoria}"), ("PATCH", "/api/admin/categories/{id_categoria}"),
            ("PATCH", "/api/admin/categories/{id_categoria}/status")})
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(routes.router)
        params = app.openapi()["paths"]["/api/admin/categories"]["get"]["parameters"]
        self.assertEqual(next(p for p in params if p['name'] == 'page_size')['schema']['maximum'], 100)

    def test_denied_access_never_calls_service(self):
        for code in (401, 403):
            denied = JSONResponse(status_code=code, content={"success": False})
            with patch.object(routes, "AdminCategoryService") as service:
                calls = [routes.list_categories(administrator=denied, db=MagicMock()),
                    routes.get_category(7, administrator=denied, db=MagicMock()),
                    routes.create_category(CategoryCreateRequest(nombre="Base"), administrator=denied, db=MagicMock()),
                    routes.update_category(7, CategoryUpdateRequest(nombre="Other"), administrator=denied, db=MagicMock()),
                    routes.update_category_status(7, CategoryStatusUpdateRequest(estado=False), administrator=denied, db=MagicMock())]
                self.assertTrue(all(result is denied for result in calls))
                service.assert_not_called()
