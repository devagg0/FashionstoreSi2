"""Pruebas de CU05 sin conexiones ni cambios a la base de datos."""

from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.admin_branch_repository import AdminBranchRepository
from app.routers import admin_branches as routes
from app.routers.admin_users import require_administrator
from app.schemas.admin_branch import (
    BranchCreateRequest, BranchUpdateRequest, BranchStatusUpdateRequest,
)
from app.services.admin_branch_service import (
    AdminBranchService, AdminBranchPersistenceError, BranchNotFoundError,
    BranchCityNotFoundError, BranchCityInactiveError,
)
from app.services.admin_user_service import AdministratorRequiredError


def _branch():
    return SimpleNamespace(
        id_sucursal=7, id_ciudad=1, nombre="Centro", direccion="Calle 1",
        telefono=None, hora_apertura=None, hora_cierre=None, estado=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


def _payload(**changes):
    return BranchCreateRequest(**dict(
        {"id_ciudad": 1, "nombre": "Centro", "direccion": "Calle 1"}, **changes,
    ))


class AdminBranchSchemaTests(TestCase):
    def test_required_fields_and_lengths(self):
        for changes in ({"nombre": " "}, {"direccion": " "}, {"id_ciudad": None},
                        {"nombre": "a" * 151}, {"direccion": "a" * 201},
                        {"telefono": "a" * 31}, {"estado": False}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                _payload(**changes)
        for field in ("id_ciudad", "nombre", "direccion"):
            values = _payload().model_dump()
            del values[field]
            with self.subTest(missing=field), self.assertRaises(ValidationError):
                BranchCreateRequest(**values)

    def test_normalization_and_overnight_hours(self):
        payload = _payload(nombre=" Centro ", direccion=" Calle 1 ",
                           hora_apertura="22:00", hora_cierre="06:00")
        self.assertEqual(payload.nombre, "Centro")
        self.assertEqual(payload.direccion, "Calle 1")
        self.assertEqual(payload.hora_cierre.hour, 6)

    def test_partial_update_and_explicit_null(self):
        self.assertEqual(BranchUpdateRequest(telefono=None).model_dump(exclude_unset=True),
                         {"telefono": None})
        for values in ({}, {"nombre": None}, {"direccion": None}, {"id_ciudad": None},
                       {"estado": False}, {"id_sucursal": 1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                BranchUpdateRequest(**values)


class AdminBranchServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminBranchService(self.db)
        self.service.repository = MagicMock()
        self.service.city_repository = MagicMock()
        self.branch = _branch()
        self.service.repository.get_by_id.return_value = self.branch
        self.service.repository.create.return_value = self.branch
        self.service.city_repository.get_by_id.return_value = SimpleNamespace(estado=True)
        self.service.repository.update.side_effect = self._update
        self.service.repository.update_status.side_effect = (
            lambda branch, *, state: setattr(branch, "estado", state)
        )

    @staticmethod
    def _update(branch, **values):
        for field, value in values.items():
            setattr(branch, field, value)

    def test_valid_creation_allows_repeated_names(self):
        for _ in range(2):
            result = self.service.create_branch(_payload())
            self.assertTrue(result.estado)
        self.service.repository.create.assert_called_with(**_payload().model_dump())
        self.service.city_repository.get_by_id.assert_called_with(1, for_update=True)
        self.assertEqual(self.db.commit.call_count, 2)
        self.service.repository.get_by_name.assert_not_called()

    def test_missing_or_inactive_city_rejects_creation_and_change(self):
        for city, error in ((None, BranchCityNotFoundError),
                            (SimpleNamespace(estado=False), BranchCityInactiveError)):
            self.service.city_repository.get_by_id.return_value = city
            for operation in (
                lambda: self.service.create_branch(_payload()),
                lambda: self.service.update_branch(branch_id=7, payload=BranchUpdateRequest(id_ciudad=2)),
            ):
                with self.subTest(city=city), self.assertRaises(error):
                    operation()
        self.assertEqual(self.db.rollback.call_count, 4)
        self.db.commit.assert_not_called()
        self.service.repository.create.assert_not_called()
        self.service.repository.update.assert_not_called()

    def test_change_city(self):
        result = self.service.update_branch(branch_id=7, payload=BranchUpdateRequest(id_ciudad=2))
        self.assertEqual(result.id_ciudad, 2)
        self.service.city_repository.get_by_id.assert_called_once_with(2, for_update=True)
        self.db.commit.assert_called_once_with()

    def test_inactive_city_does_not_block_detail_or_other_edits(self):
        self.service.city_repository.get_by_id.return_value = SimpleNamespace(estado=False)
        self.assertEqual(self.service.get_branch(7).id_sucursal, 7)
        result = self.service.update_branch(
            branch_id=7, payload=BranchUpdateRequest(nombre="Norte", id_ciudad=1),
        )
        self.assertEqual(result.nombre, "Norte")
        self.service.city_repository.get_by_id.assert_not_called()

    def test_list_and_search_pagination(self):
        self.service.repository.list_branches.return_value = ([self.branch], 21)
        data, pagination = self.service.list_branches(search="Cen", state=False, page=2, page_size=20)
        self.assertEqual(data[0].id_sucursal, 7)
        self.assertEqual(pagination.model_dump(), {"page": 2, "page_size": 20, "total": 21, "total_pages": 2})
        self.service.repository.list_branches.assert_called_once_with(
            search="Cen", state=False, page=2, page_size=20,
        )

    def test_reversible_status_without_cascades(self):
        for state in (False, True):
            result = self.service.update_status(branch_id=7, payload=BranchStatusUpdateRequest(estado=state))
            self.assertEqual(result.estado, state)
        self.db.delete.assert_not_called()
        self.service.city_repository.get_by_id.assert_not_called()
        self.assertEqual(self.db.commit.call_count, 2)

    def test_missing_branch(self):
        self.service.repository.get_by_id.return_value = None
        for operation in (
            lambda: self.service.get_branch(999),
            lambda: self.service.update_branch(branch_id=999, payload=BranchUpdateRequest(nombre="Norte")),
            lambda: self.service.update_status(branch_id=999, payload=BranchStatusUpdateRequest(estado=False)),
        ):
            with self.assertRaises(BranchNotFoundError):
                operation()
        self.db.commit.assert_not_called()
        self.assertEqual(self.db.rollback.call_count, 2)

    def test_persistence_failures_rollback(self):
        self.db.commit.side_effect = SQLAlchemyError("failure")
        for operation in (
            lambda: self.service.create_branch(_payload()),
            lambda: self.service.update_branch(branch_id=7, payload=BranchUpdateRequest(nombre="Norte")),
            lambda: self.service.update_status(branch_id=7, payload=BranchStatusUpdateRequest(estado=False)),
        ):
            with self.assertRaises(AdminBranchPersistenceError):
                operation()
        self.assertEqual(self.db.rollback.call_count, 3)


class AdminBranchRepositoryTests(TestCase):
    def test_search_is_literal_and_count_has_same_filters(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = [_branch()]
        db.scalar.return_value = 3
        data, total = AdminBranchRepository(db).list_branches(
            search="  A%_\\  ", state=False, page=2, page_size=2,
        )
        statement = db.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertIn("ILIKE", str(statement))
        self.assertIn("ORDER BY t_sucursal.nombre, t_sucursal.id_sucursal", str(statement))
        self.assertIn("t_sucursal.estado IS false", str(statement))
        self.assertEqual(statement.params["nombre_1"], "%A\\%\\_\\\\%")
        self.assertEqual(count.params["nombre_1"], statement.params["nombre_1"])
        self.assertIn("t_sucursal.estado IS false", str(count))
        self.assertEqual(statement.params["param_1"], 2)
        self.assertEqual(statement.params["param_2"], 2)
        self.assertEqual((len(data), total), (1, 3))

    def test_create_flushes_active_branch_without_commit(self):
        db = MagicMock()
        branch = AdminBranchRepository(db).create(**_payload().model_dump())
        self.assertTrue(branch.estado)
        db.add.assert_called_once_with(branch)
        db.flush.assert_called_once_with()
        db.commit.assert_not_called()


class AdminBranchRouteTests(TestCase):
    def test_main_registration_and_pagination_limits(self):
        from app.main import app

        operation = app.openapi()["paths"]["/api/admin/branches"]["get"]
        parameters = {item["name"]: item["schema"] for item in operation["parameters"]}
        self.assertEqual(parameters["page"]["minimum"], 1)
        self.assertEqual(parameters["page_size"]["minimum"], 1)
        self.assertEqual(parameters["page_size"]["maximum"], 100)
        self.assertTrue(operation["security"])

    def test_read_failures_return_internal_error(self):
        with patch.object(routes, "AdminBranchService") as service:
            service.return_value.list_branches.side_effect = SQLAlchemyError("failure")
            service.return_value.get_branch.side_effect = SQLAlchemyError("failure")
            self.assertEqual(routes.list_branches(administrator=MagicMock(), db=MagicMock()).status_code, 500)
            self.assertEqual(routes.get_branch(7, administrator=MagicMock(), db=MagicMock()).status_code, 500)

    def test_required_routes(self):
        self.assertEqual({(method, route.path) for route in routes.router.routes for method in route.methods}, {
            ("GET", "/api/admin/branches"), ("POST", "/api/admin/branches"),
            ("GET", "/api/admin/branches/{id_sucursal}"),
            ("PATCH", "/api/admin/branches/{id_sucursal}"),
            ("PATCH", "/api/admin/branches/{id_sucursal}/status"),
        })
        post = next(route for route in routes.router.routes if "POST" in route.methods)
        self.assertEqual(post.status_code, 201)

    def test_non_administrator_and_missing_token_stop_every_endpoint(self):
        with patch("app.routers.admin_users.AdminUserService") as service:
            service.return_value.authenticate_administrator.side_effect = AdministratorRequiredError
            forbidden = require_administrator(HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"), MagicMock())
        unauthorized = require_administrator(None, MagicMock())
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(unauthorized.status_code, 401)
        with patch.object(routes, "AdminBranchService") as branch_service:
            for denial in (forbidden, unauthorized):
                common = {"administrator": denial, "db": MagicMock()}
                responses = [
                    routes.list_branches(**common), routes.get_branch(7, **common),
                    routes.create_branch(_payload(), **common),
                    routes.update_branch(7, BranchUpdateRequest(nombre="Norte"), **common),
                    routes.update_branch_status(7, BranchStatusUpdateRequest(estado=False), **common),
                ]
                for response in responses:
                    self.assertIs(response, denial)
            branch_service.assert_not_called()

    def test_domain_errors_use_expected_status(self):
        with patch.object(routes, "AdminBranchService") as service:
            for error, code in ((BranchCityNotFoundError, 404), (BranchCityInactiveError, 422),
                                (AdminBranchPersistenceError, 500)):
                service.return_value.create_branch.side_effect = error
                response = routes.create_branch(_payload(), administrator=MagicMock(), db=MagicMock())
                self.assertIsInstance(response, JSONResponse)
                self.assertEqual(response.status_code, code)
