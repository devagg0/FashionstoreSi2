"""Pruebas SizeU07 sin conectar ni modificar la base de datos."""
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.repositories.admin_size_repository import AdminSizeRepository
from app.services.admin_size_service import AdminSizeService, SizeNameDuplicateError, SizeNotFoundError, AdminSizePersistenceError
from app.schemas.admin_size import SizeCreateRequest, SizeUpdateRequest, SizeStatusUpdateRequest
from app.routers import admin_sizes as routes


def record():
    return SimpleNamespace(id_talla=7, nombre="Base", descripcion=None, estado=True,
                           created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))


class SchemaTests(TestCase):
    def test_normalization_and_lengths(self):
        self.assertEqual(SizeCreateRequest(nombre=" Base ", descripcion=" abc ").model_dump(),
                         {"nombre": "Base", "descripcion": "abc"})
        for values in ({}, {"nombre": " "}, {"nombre": None}, {"nombre": "x" * (20+1)},
                       {"nombre": "Base", "descripcion": "x" * (100+1)}, {"nombre": "Base", "estado": False},
                       {"nombre": "Base", "id_sucursal": 1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SizeCreateRequest(**values)
        self.assertEqual(len(SizeCreateRequest(nombre="x" * 20, descripcion="x" * 100).nombre), 20)

    def test_patch(self):
        self.assertEqual(SizeUpdateRequest(descripcion=None).model_dump(exclude_unset=True), {"descripcion": None})
        for values in ({}, {"nombre": None}, {"estado": False}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SizeUpdateRequest(**values)


class ServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminSizeService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.item = record()
        self.repo.get_by_id.return_value = self.item
        self.repo.get_by_name.return_value = None
        self.repo.create.return_value = self.item
        self.repo.update.side_effect = lambda item, **values: item.__dict__.update(values)
        self.repo.update_status.side_effect = lambda item, state: setattr(item, "estado", state)

    def test_create(self):
        result = self.service.create_size(SizeCreateRequest(nombre=" Base "))
        self.repo.create.assert_called_once_with(nombre="Base", descripcion=None)
        self.assertTrue(result.estado)
        self.db.commit.assert_called_once()

    def test_duplicate_create_and_update(self):
        self.repo.get_by_name.return_value = self.item
        with self.assertRaises(SizeNameDuplicateError):
            self.service.create_size(SizeCreateRequest(nombre="base"))
        with self.assertRaises(SizeNameDuplicateError):
            self.service.update_size(size_id=7, payload=SizeUpdateRequest(nombre="BASE"))
        self.repo.create.assert_not_called()
        self.repo.update.assert_not_called()
        self.assertEqual(self.db.rollback.call_count, 2)

    def test_list_search_state_pagination(self):
        self.repo.list_sizes.return_value = ([self.item], 3)
        data, pagination = self.service.list_sizes(search="ba", state=False, page=2, page_size=2)
        self.repo.list_sizes.assert_called_once_with(search="ba", state=False, page=2, page_size=2)
        self.assertEqual(data[0].id_talla, 7)
        self.assertEqual(pagination.model_dump(), {"page": 2, "page_size": 2, "total": 3, "total_pages": 2})

    def test_detail_and_partial_update(self):
        self.assertEqual(self.service.get_size(7).nombre, "Base")
        result = self.service.update_size(size_id=7, payload=SizeUpdateRequest(descripcion=" abc "))
        self.assertEqual(result.descripcion, "abc")
        self.assertEqual(result.nombre, "Base")
        self.repo.get_by_name.assert_not_called()
        result = self.service.update_size(size_id=7, payload=SizeUpdateRequest(descripcion=None))
        self.assertIsNone(result.descripcion)
        self.service.update_size(size_id=7, payload=SizeUpdateRequest(nombre="BASE"))
        self.repo.get_by_name.assert_called_once_with("BASE", exclude_size_id=7)

    def test_deactivate_and_reactivate(self):
        for state in (False, True):
            result = self.service.update_status(size_id=7, payload=SizeStatusUpdateRequest(estado=state))
            self.assertEqual(result.estado, state)
        self.db.delete.assert_not_called()
        self.assertEqual(result.created_at, datetime(2026, 1, 1))
        self.assertEqual(result.updated_at, datetime(2026, 1, 1))

    def test_missing(self):
        self.repo.get_by_id.return_value = None
        for operation in (lambda: self.service.get_size(999),
                          lambda: self.service.update_size(size_id=999, payload=SizeUpdateRequest(nombre="Other")),
                          lambda: self.service.update_status(size_id=999, payload=SizeStatusUpdateRequest(estado=False))):
            with self.assertRaises(SizeNotFoundError):
                operation()

    def test_persistence_rollback(self):
        self.db.commit.side_effect = SQLAlchemyError("failure")
        with self.assertRaises(AdminSizePersistenceError):
            self.service.create_size(SizeCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()

    def test_integrity_conflict(self):
        self.repo.get_by_name.side_effect = [None, self.item]
        self.repo.create.side_effect = IntegrityError("insert", {}, Exception())
        with self.assertRaises(SizeNameDuplicateError):
            self.service.create_size(SizeCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()


class RepositoryTests(TestCase):
    def test_filters_escaped_search_and_order(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        db.scalar.return_value = 0
        repository = AdminSizeRepository(db)
        self.assertEqual(repository.list_sizes(search=" %_\\ ", state=False, page=2, page_size=3), ([], 0))
        statement = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(statement)
        self.assertIn("ILIKE", sql)
        self.assertIn("estado IS false", sql)
        self.assertIn("ORDER BY t_talla.nombre, t_talla.id_talla", sql)
        self.assertIn("%\\%\\_\\\\%", statement.params.values())
        self.assertIn(3, statement.params.values())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertEqual(count.params['nombre_1'], statement.params['nombre_1'])

    def test_duplicate_comparison(self):
        db = MagicMock()
        AdminSizeRepository(db).get_by_name("BASE", exclude_size_id=7)
        query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("lower(t_talla.nombre)", str(query))
        self.assertIn("base", query.params.values())
        self.assertIn("!=", str(query))


class RouteTests(TestCase):
    def test_routes_and_pagination_limit(self):
        registered = {(method, route.path) for route in routes.router.routes for method in route.methods}
        self.assertEqual(registered, {("GET", "/api/admin/sizes"), ("POST", "/api/admin/sizes"),
            ("GET", "/api/admin/sizes/{id_talla}"), ("PATCH", "/api/admin/sizes/{id_talla}"),
            ("PATCH", "/api/admin/sizes/{id_talla}/status")})
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(routes.router)
        params = app.openapi()["paths"]["/api/admin/sizes"]["get"]["parameters"]
        self.assertEqual(next(p for p in params if p['name'] == 'page_size')['schema']['maximum'], 100)

    def test_denied_access_never_calls_service(self):
        for code in (401, 403):
            denied = JSONResponse(status_code=code, content={"success": False})
            with patch.object(routes, "AdminSizeService") as service:
                calls = [routes.list_sizes(administrator=denied, db=MagicMock()),
                    routes.get_size(7, administrator=denied, db=MagicMock()),
                    routes.create_size(SizeCreateRequest(nombre="Base"), administrator=denied, db=MagicMock()),
                    routes.update_size(7, SizeUpdateRequest(nombre="Other"), administrator=denied, db=MagicMock()),
                    routes.update_size_status(7, SizeStatusUpdateRequest(estado=False), administrator=denied, db=MagicMock())]
                self.assertTrue(all(result is denied for result in calls))
                service.assert_not_called()
