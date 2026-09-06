"""Pruebas ColorU07 sin conectar ni modificar la base de datos."""
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.repositories.admin_color_repository import AdminColorRepository
from app.services.admin_color_service import AdminColorService, ColorNameDuplicateError, ColorNotFoundError, AdminColorPersistenceError
from app.schemas.admin_color import ColorCreateRequest, ColorUpdateRequest, ColorStatusUpdateRequest
from app.routers import admin_colors as routes


def record():
    return SimpleNamespace(id_color=7, nombre="Base", codigo_hex=None, estado=True,
                           created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))


class SchemaTests(TestCase):
    def test_normalization_and_lengths(self):
        self.assertEqual(ColorCreateRequest(nombre=" Base ", codigo_hex=" abc ").model_dump(),
                         {"nombre": "Base", "codigo_hex": "abc"})
        for values in ({}, {"nombre": " "}, {"nombre": None}, {"nombre": "x" * (50+1)},
                       {"nombre": "Base", "codigo_hex": "x" * (7+1)}, {"nombre": "Base", "estado": False},
                       {"nombre": "Base", "id_sucursal": 1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ColorCreateRequest(**values)
        self.assertEqual(len(ColorCreateRequest(nombre="x" * 50, codigo_hex="x" * 7).nombre), 50)

    def test_patch(self):
        self.assertEqual(ColorUpdateRequest(codigo_hex=None).model_dump(exclude_unset=True), {"codigo_hex": None})
        for values in ({}, {"nombre": None}, {"estado": False}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ColorUpdateRequest(**values)


class ServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminColorService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.item = record()
        self.repo.get_by_id.return_value = self.item
        self.repo.get_by_name.return_value = None
        self.repo.create.return_value = self.item
        self.repo.update.side_effect = lambda item, **values: item.__dict__.update(values)
        self.repo.update_status.side_effect = lambda item, state: setattr(item, "estado", state)

    def test_create(self):
        result = self.service.create_color(ColorCreateRequest(nombre=" Base "))
        self.repo.create.assert_called_once_with(nombre="Base", codigo_hex=None)
        self.assertTrue(result.estado)
        self.db.commit.assert_called_once()

    def test_duplicate_create_and_update(self):
        self.repo.get_by_name.return_value = self.item
        with self.assertRaises(ColorNameDuplicateError):
            self.service.create_color(ColorCreateRequest(nombre="base"))
        with self.assertRaises(ColorNameDuplicateError):
            self.service.update_color(color_id=7, payload=ColorUpdateRequest(nombre="BASE"))
        self.repo.create.assert_not_called()
        self.repo.update.assert_not_called()
        self.assertEqual(self.db.rollback.call_count, 2)

    def test_list_search_state_pagination(self):
        self.repo.list_colors.return_value = ([self.item], 3)
        data, pagination = self.service.list_colors(search="ba", state=False, page=2, page_size=2)
        self.repo.list_colors.assert_called_once_with(search="ba", state=False, page=2, page_size=2)
        self.assertEqual(data[0].id_color, 7)
        self.assertEqual(pagination.model_dump(), {"page": 2, "page_size": 2, "total": 3, "total_pages": 2})

    def test_detail_and_partial_update(self):
        self.assertEqual(self.service.get_color(7).nombre, "Base")
        result = self.service.update_color(color_id=7, payload=ColorUpdateRequest(codigo_hex=" abc "))
        self.assertEqual(result.codigo_hex, "abc")
        self.assertEqual(result.nombre, "Base")
        self.repo.get_by_name.assert_not_called()
        result = self.service.update_color(color_id=7, payload=ColorUpdateRequest(codigo_hex=None))
        self.assertIsNone(result.codigo_hex)
        self.service.update_color(color_id=7, payload=ColorUpdateRequest(nombre="BASE"))
        self.repo.get_by_name.assert_called_once_with("BASE", exclude_color_id=7)

    def test_deactivate_and_reactivate(self):
        for state in (False, True):
            result = self.service.update_status(color_id=7, payload=ColorStatusUpdateRequest(estado=state))
            self.assertEqual(result.estado, state)
        self.db.delete.assert_not_called()
        self.assertEqual(result.created_at, datetime(2026, 1, 1))
        self.assertEqual(result.updated_at, datetime(2026, 1, 1))

    def test_missing(self):
        self.repo.get_by_id.return_value = None
        for operation in (lambda: self.service.get_color(999),
                          lambda: self.service.update_color(color_id=999, payload=ColorUpdateRequest(nombre="Other")),
                          lambda: self.service.update_status(color_id=999, payload=ColorStatusUpdateRequest(estado=False))):
            with self.assertRaises(ColorNotFoundError):
                operation()

    def test_persistence_rollback(self):
        self.db.commit.side_effect = SQLAlchemyError("failure")
        with self.assertRaises(AdminColorPersistenceError):
            self.service.create_color(ColorCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()

    def test_integrity_conflict(self):
        self.repo.get_by_name.side_effect = [None, self.item]
        self.repo.create.side_effect = IntegrityError("insert", {}, Exception())
        with self.assertRaises(ColorNameDuplicateError):
            self.service.create_color(ColorCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()


class RepositoryTests(TestCase):
    def test_filters_escaped_search_and_order(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        db.scalar.return_value = 0
        repository = AdminColorRepository(db)
        self.assertEqual(repository.list_colors(search=" %_\\ ", state=False, page=2, page_size=3), ([], 0))
        statement = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(statement)
        self.assertIn("ILIKE", sql)
        self.assertIn("estado IS false", sql)
        self.assertIn("ORDER BY t_color.nombre, t_color.id_color", sql)
        self.assertIn("%\\%\\_\\\\%", statement.params.values())
        self.assertIn(3, statement.params.values())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertEqual(count.params['nombre_1'], statement.params['nombre_1'])

    def test_duplicate_comparison(self):
        db = MagicMock()
        AdminColorRepository(db).get_by_name("BASE", exclude_color_id=7)
        query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("lower(t_color.nombre)", str(query))
        self.assertIn("base", query.params.values())
        self.assertIn("!=", str(query))


class RouteTests(TestCase):
    def test_routes_and_pagination_limit(self):
        registered = {(method, route.path) for route in routes.router.routes for method in route.methods}
        self.assertEqual(registered, {("GET", "/api/admin/colors"), ("POST", "/api/admin/colors"),
            ("GET", "/api/admin/colors/{id_color}"), ("PATCH", "/api/admin/colors/{id_color}"),
            ("PATCH", "/api/admin/colors/{id_color}/status")})
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(routes.router)
        params = app.openapi()["paths"]["/api/admin/colors"]["get"]["parameters"]
        self.assertEqual(next(p for p in params if p['name'] == 'page_size')['schema']['maximum'], 100)

    def test_denied_access_never_calls_service(self):
        for code in (401, 403):
            denied = JSONResponse(status_code=code, content={"success": False})
            with patch.object(routes, "AdminColorService") as service:
                calls = [routes.list_colors(administrator=denied, db=MagicMock()),
                    routes.get_color(7, administrator=denied, db=MagicMock()),
                    routes.create_color(ColorCreateRequest(nombre="Base"), administrator=denied, db=MagicMock()),
                    routes.update_color(7, ColorUpdateRequest(nombre="Other"), administrator=denied, db=MagicMock()),
                    routes.update_color_status(7, ColorStatusUpdateRequest(estado=False), administrator=denied, db=MagicMock())]
                self.assertTrue(all(result is denied for result in calls))
                service.assert_not_called()
