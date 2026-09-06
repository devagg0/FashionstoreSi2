"""Pruebas CU08 sin conectar ni modificar la base de datos."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.repositories.admin_season_repository import AdminSeasonRepository
from app.services.admin_season_service import AdminSeasonService, SeasonNotFoundError, AdminSeasonPersistenceError
from app.schemas.admin_season import SeasonCreateRequest, SeasonUpdateRequest, SeasonStatusUpdateRequest
from app.routers import admin_seasons as routes


def record():
    return SimpleNamespace(id_temporada=7, nombre="Base", descripcion=None, fecha_inicio=None, fecha_fin=None, estado=True,
                           created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))


class SchemaTests(TestCase):
    def test_normalization_and_lengths(self):
        self.assertEqual(SeasonCreateRequest(nombre=" Base ", descripcion=" abc ").model_dump(),
                         {"nombre": "Base", "descripcion": "abc", "fecha_inicio": None, "fecha_fin": None})
        for values in ({}, {"nombre": " "}, {"nombre": None}, {"nombre": "x" * (100+1)},
                       {"nombre": "Base", "descripcion": "x" * (200+1)}, {"nombre": "Base", "estado": False},
                       {"nombre": "Base", "id_sucursal": 1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SeasonCreateRequest(**values)
        self.assertEqual(len(SeasonCreateRequest(nombre="x" * 100, descripcion="x" * 200).nombre), 100)

    def test_patch(self):
        self.assertEqual(SeasonUpdateRequest(descripcion=None).model_dump(exclude_unset=True), {"descripcion": None})
        for values in ({}, {"nombre": None}, {"estado": False}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SeasonUpdateRequest(**values)


class ServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminSeasonService(self.db)
        self.repo = self.service.repository = MagicMock()
        self.item = record()
        self.repo.get_by_id.return_value = self.item
        self.repo.get_by_name.return_value = None
        self.repo.create.return_value = self.item
        self.repo.update.side_effect = lambda item, **values: item.__dict__.update(values)
        self.repo.update_status.side_effect = lambda item, state: setattr(item, "estado", state)

    def test_create(self):
        result = self.service.create_season(SeasonCreateRequest(nombre=" Base "))
        self.repo.create.assert_called_once_with(nombre="Base", descripcion=None, fecha_inicio=None, fecha_fin=None)
        self.assertTrue(result.estado)
        self.db.commit.assert_called_once()

    def test_same_name_allowed_on_create_and_update(self):
        self.repo.get_by_name.return_value = self.item
        for _ in range(2):
            self.service.create_season(SeasonCreateRequest(nombre="Base"))
        self.service.update_season(season_id=7, payload=SeasonUpdateRequest(nombre="Base"))
        self.repo.get_by_name.assert_not_called()
        self.assertEqual(self.repo.create.call_count, 2)
        self.assertEqual(self.db.commit.call_count, 3)

    def test_list_search_state_pagination(self):
        self.repo.list_seasons.return_value = ([self.item], 3)
        data, pagination = self.service.list_seasons(search="ba", state=False, page=2, page_size=2)
        self.repo.list_seasons.assert_called_once_with(search="ba", state=False, page=2, page_size=2)
        self.assertEqual(data[0].id_temporada, 7)
        self.assertEqual(pagination.model_dump(), {"page": 2, "page_size": 2, "total": 3, "total_pages": 2})

    def test_detail_and_partial_update(self):
        self.assertEqual(self.service.get_season(7).nombre, "Base")
        result = self.service.update_season(season_id=7, payload=SeasonUpdateRequest(descripcion=" abc "))
        self.assertEqual(result.descripcion, "abc")
        self.assertEqual(result.nombre, "Base")
        self.repo.get_by_name.assert_not_called()
        result = self.service.update_season(season_id=7, payload=SeasonUpdateRequest(descripcion=None))
        self.assertIsNone(result.descripcion)
        self.service.update_season(season_id=7, payload=SeasonUpdateRequest(nombre="BASE"))
        self.repo.get_by_name.assert_not_called()

    def test_deactivate_and_reactivate(self):
        for state in (False, True):
            result = self.service.update_status(season_id=7, payload=SeasonStatusUpdateRequest(estado=state))
            self.assertEqual(result.estado, state)
        self.db.delete.assert_not_called()
        self.assertEqual(result.created_at, datetime(2026, 1, 1))
        self.assertEqual(result.updated_at, datetime(2026, 1, 1))

    def test_missing(self):
        self.repo.get_by_id.return_value = None
        for operation in (lambda: self.service.get_season(999),
                          lambda: self.service.update_season(season_id=999, payload=SeasonUpdateRequest(nombre="Other")),
                          lambda: self.service.update_status(season_id=999, payload=SeasonStatusUpdateRequest(estado=False))):
            with self.assertRaises(SeasonNotFoundError):
                operation()

    def test_persistence_rollback(self):
        self.db.commit.side_effect = SQLAlchemyError("failure")
        with self.assertRaises(AdminSeasonPersistenceError):
            self.service.create_season(SeasonCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()

    def test_integrity_error_is_not_a_name_conflict(self):
        self.repo.create.side_effect = IntegrityError("insert", {}, Exception())
        with self.assertRaises(AdminSeasonPersistenceError):
            self.service.create_season(SeasonCreateRequest(nombre="Base"))
        self.db.rollback.assert_called_once()
        self.repo.get_by_name.assert_not_called()


class RepositoryTests(TestCase):
    def test_filters_escaped_search_and_order(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        db.scalar.return_value = 0
        repository = AdminSeasonRepository(db)
        self.assertEqual(repository.list_seasons(search=" %_\\ ", state=False, page=2, page_size=3), ([], 0))
        statement = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        sql = str(statement)
        self.assertIn("ILIKE", sql)
        self.assertIn("estado IS false", sql)
        self.assertIn("ORDER BY t_temporada.nombre, t_temporada.id_temporada", sql)
        self.assertIn("%\\%\\_\\\\%", statement.params.values())
        self.assertIn(3, statement.params.values())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertEqual(count.params['nombre_1'], statement.params['nombre_1'])

    def test_create_active_without_name_lookup(self):
        db = MagicMock()
        repository = AdminSeasonRepository(db)
        first = repository.create(nombre="Base")
        second = repository.create(nombre="Base")
        self.assertEqual(first.nombre, second.nombre)
        self.assertTrue(first.estado)
        self.assertIsNone(first.descripcion)
        self.assertEqual(db.add.call_count, 2)
        db.scalar.assert_not_called()

    def test_status_only_changes_record(self):
        db = MagicMock()
        item = record()
        original = vars(item).copy()
        AdminSeasonRepository(db).update_status(item, state=False)
        self.assertEqual(vars(item), {**original, "estado": False})
        db.flush.assert_called_once()
        db.delete.assert_not_called()

    def test_update_locks_record(self):
        db = MagicMock()
        AdminSeasonRepository(db).get_by_id(7, for_update=True)
        query = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("FOR UPDATE", str(query))


class RouteTests(TestCase):
    def test_routes_and_pagination_limit(self):
        registered = {(method, route.path) for route in routes.router.routes for method in route.methods}
        self.assertEqual(registered, {("GET", "/api/admin/seasons"), ("POST", "/api/admin/seasons"),
            ("GET", "/api/admin/seasons/{id_temporada}"), ("PATCH", "/api/admin/seasons/{id_temporada}"),
            ("PATCH", "/api/admin/seasons/{id_temporada}/status")})
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(routes.router)
        params = app.openapi()["paths"]["/api/admin/seasons"]["get"]["parameters"]
        self.assertEqual(next(p for p in params if p['name'] == 'page_size')['schema']['maximum'], 100)

    def test_denied_access_never_calls_service(self):
        for code in (401, 403):
            denied = JSONResponse(status_code=code, content={"success": False})
            with patch.object(routes, "AdminSeasonService") as service:
                calls = [routes.list_seasons(administrator=denied, db=MagicMock()),
                    routes.get_season(7, administrator=denied, db=MagicMock()),
                    routes.create_season(SeasonCreateRequest(nombre="Base"), administrator=denied, db=MagicMock()),
                    routes.update_season(7, SeasonUpdateRequest(nombre="Other"), administrator=denied, db=MagicMock()),
                    routes.update_season_status(7, SeasonStatusUpdateRequest(estado=False), administrator=denied, db=MagicMock())]
                self.assertTrue(all(result is denied for result in calls))
                service.assert_not_called()


class SeasonDateTests(TestCase):
    def test_optional_and_reversed_dates_allowed(self):
        self.assertIsNone(SeasonCreateRequest(nombre="Base").fecha_inicio)
        payload = SeasonCreateRequest(nombre="Base", fecha_inicio="2026-12-31", fecha_fin="2026-01-01")
        self.assertEqual(payload.fecha_inicio, date(2026, 12, 31))
        self.assertEqual(payload.fecha_fin, date(2026, 1, 1))
        db = MagicMock()
        item = AdminSeasonRepository(db).create(**payload.model_dump())
        self.assertEqual(item.fecha_fin, payload.fecha_fin)
        self.assertEqual(SeasonUpdateRequest(fecha_inicio=None).model_dump(exclude_unset=True), {"fecha_inicio": None})
        with self.assertRaises(ValidationError):
            SeasonCreateRequest(nombre="Base", fecha_inicio="2026-02-30")

    def test_date_patch_preserves_other_fields(self):
        service = AdminSeasonService(MagicMock())
        item = record()
        item.fecha_fin = date(2026, 1, 1)
        service.repository.get_by_id = MagicMock(return_value=item)
        result = service.update_season(season_id=7, payload=SeasonUpdateRequest(fecha_inicio="2026-12-31"))
        self.assertEqual(result.fecha_inicio, date(2026, 12, 31))
        self.assertEqual(result.fecha_fin, date(2026, 1, 1))
        result = service.update_season(season_id=7, payload=SeasonUpdateRequest(fecha_fin=None))
        self.assertIsNone(result.fecha_fin)


class ResponseTests(TestCase):
    def test_main_registration_and_success_status(self):
        from app.main import app
        operation = app.openapi()["paths"]["/api/admin/seasons"]
        self.assertIn("201", operation["post"]["responses"])
        self.assertIn("200", operation["get"]["responses"])
        self.assertTrue(operation["post"]["security"])
        with patch.object(routes, "AdminSeasonService") as service:
            service.return_value.create_season.return_value = vars(record())
            result = routes.create_season(SeasonCreateRequest(nombre="Base"), administrator=object(), db=MagicMock())
            self.assertTrue(result.success)
            self.assertEqual(result.data.nombre, "Base")

    def test_missing_and_persistence_errors(self):
        with patch.object(routes, "AdminSeasonService") as service:
            instance = service.return_value
            instance.get_season.side_effect = SeasonNotFoundError
            instance.update_season.side_effect = SeasonNotFoundError
            instance.update_status.side_effect = SeasonNotFoundError
            results = [
                routes.get_season(999, administrator=object(), db=MagicMock()),
                routes.update_season(999, SeasonUpdateRequest(nombre="Base"), administrator=object(), db=MagicMock()),
                routes.update_season_status(999, SeasonStatusUpdateRequest(estado=False), administrator=object(), db=MagicMock()),
            ]
            self.assertTrue(all(result.status_code == 404 for result in results))
            instance.create_season.side_effect = AdminSeasonPersistenceError
            result = routes.create_season(SeasonCreateRequest(nombre="Base"), administrator=object(), db=MagicMock())
            self.assertEqual(result.status_code, 500)
            instance.list_seasons.side_effect = SQLAlchemyError("failure")
            db = MagicMock()
            result = routes.list_seasons(administrator=object(), db=db)
            self.assertEqual(result.status_code, 500)
            db.rollback.assert_called_once()
