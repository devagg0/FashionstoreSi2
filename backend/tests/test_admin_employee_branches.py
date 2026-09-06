"""Pruebas de CU06 con mocks: sin conexiones, DDL ni migraciones."""

from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.repositories.admin_employee_branch_repository import AdminEmployeeBranchRepository
from app.routers import admin_employee_branches as routes
from app.routers.admin_users import require_administrator
from app.schemas.admin_employee_branch import (
    AdminEmployeeBranchData, EmployeeBranchCreateRequest, EmployeeBranchStatusUpdateRequest,
)
from app.services.admin_employee_branch_service import (
    AdminEmployeeBranchPersistenceError, AdminEmployeeBranchService,
    EmployeeBranchConflictError, EmployeeBranchNotFoundError, EmployeeBranchValidationError,
)
from app.services.admin_user_service import AdministratorRequiredError


def _payload(branch_id=7):
    return EmployeeBranchCreateRequest(id_empleado=3, id_sucursal=branch_id)


def _detail():
    return dict(
        id_empleado_sucursal=9, id_empleado=3, nombre_empleado="Ana Pérez",
        correo="ana@example.com", rol="CAJERO", id_sucursal=7,
        nombre_sucursal="Centro", fecha_asignacion=date(2026, 1, 1), estado=True,
    )


class EmployeeBranchServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = AdminEmployeeBranchService(self.db)
        self.service.repository = MagicMock()
        self.service.user_repository = MagicMock()
        self.service.branch_repository = MagicMock()
        self.assignment = SimpleNamespace(**_detail())
        self.service.repository.get_employee.return_value = SimpleNamespace(id_usuario=5)
        self.service.user_repository.get_user_with_role.return_value = (SimpleNamespace(estado=True), "CAJERO")
        self.service.branch_repository.get_by_id.return_value = SimpleNamespace(estado=True)
        self.service.repository.get_by_pair.return_value = None
        self.service.repository.create.return_value = self.assignment
        self.service.repository.get_by_id.return_value = self.assignment
        self.service.repository.get_detail.side_effect = lambda _: vars(self.assignment)
        self.service.repository.update_status.side_effect = lambda item, *, state: setattr(item, "estado", state)

    def test_create_for_both_operational_roles_and_multiple_branches(self):
        for branch_id, role in ((7, "CAJERO"), (8, "ENCARGADO_SUCURSAL")):
            self.service.user_repository.get_user_with_role.return_value = (SimpleNamespace(estado=True), role)
            data, created = self.service.create_assignment(_payload(branch_id))
            self.assertTrue(created)
            self.assertTrue(data.estado)
            self.service.repository.get_by_pair.assert_called_with(3, branch_id)
            self.service.repository.create.assert_called_with(employee_id=3, branch_id=branch_id)
        self.assertEqual(self.db.commit.call_count, 2)

    def test_missing_employee(self):
        self.service.repository.get_employee.return_value = None
        with self.assertRaisesRegex(EmployeeBranchNotFoundError, "Empleado"):
            self.service.create_assignment(_payload())
        self.service.repository.create.assert_not_called()
        self.db.rollback.assert_called_once()

    def test_invalid_missing_or_inactive_user_and_non_employee_roles(self):
        for user in (None, (SimpleNamespace(estado=False), "CAJERO"),
                     (SimpleNamespace(estado=True), "CLIENTE"),
                     (SimpleNamespace(estado=True), "PROVEEDOR"),
                     (SimpleNamespace(estado=True), "ADMINISTRADOR")):
            self.service.user_repository.get_user_with_role.return_value = user
            for operation in (
                lambda: self.service.create_assignment(_payload()),
                lambda: self.service.update_status(assignment_id=9, payload=EmployeeBranchStatusUpdateRequest(estado=True)),
            ):
                with self.subTest(user=user), self.assertRaises(EmployeeBranchValidationError):
                    operation()
        self.service.repository.create.assert_not_called()
        self.service.repository.update_status.assert_not_called()
        self.db.commit.assert_not_called()

    def test_missing_or_inactive_branch_on_create_and_reactivation(self):
        for branch, error in ((None, EmployeeBranchNotFoundError),
                              (SimpleNamespace(estado=False), EmployeeBranchValidationError)):
            self.service.branch_repository.get_by_id.return_value = branch
            for operation in (
                lambda: self.service.create_assignment(_payload()),
                lambda: self.service.update_status(assignment_id=9, payload=EmployeeBranchStatusUpdateRequest(estado=True)),
            ):
                with self.subTest(branch=branch), self.assertRaises(error):
                    operation()
        self.db.commit.assert_not_called()

    def test_active_duplicate_conflict(self):
        self.service.repository.get_by_pair.return_value = self.assignment
        with self.assertRaises(EmployeeBranchConflictError):
            self.service.create_assignment(_payload())
        self.service.repository.create.assert_not_called()
        self.db.rollback.assert_called_once()

    def test_post_reuses_inactive_record_and_preserves_date(self):
        self.assignment.estado = False
        self.service.repository.get_by_pair.return_value = self.assignment
        result, created = self.service.create_assignment(_payload())
        self.assertFalse(created)
        self.assertTrue(result.estado)
        self.assertEqual(result.id_empleado_sucursal, 9)
        self.assertEqual(result.fecha_asignacion, date(2026, 1, 1))
        self.service.repository.create.assert_not_called()

    def test_deactivation_only_changes_assignment_even_if_targets_inactive(self):
        self.service.user_repository.get_user_with_role.return_value = None
        result = self.service.update_status(assignment_id=9, payload=EmployeeBranchStatusUpdateRequest(estado=False))
        self.assertFalse(result.estado)
        self.service.user_repository.get_user_with_role.assert_not_called()
        self.service.branch_repository.get_by_id.assert_not_called()
        self.db.delete.assert_not_called()
        self.db.commit.assert_called_once()

    def test_reactivation_keeps_identity_and_date(self):
        self.assignment.estado = False
        result = self.service.update_status(assignment_id=9, payload=EmployeeBranchStatusUpdateRequest(estado=True))
        self.assertTrue(result.estado)
        self.assertEqual((result.id_empleado_sucursal, result.fecha_asignacion), (9, date(2026, 1, 1)))
        self.service.user_repository.get_user_with_role.assert_called_once_with(5, for_update=True)
        self.service.repository.create.assert_not_called()

    def test_detail_and_missing_assignment(self):
        self.assertEqual(self.service.get_assignment(9).nombre_empleado, "Ana Pérez")
        self.service.repository.get_detail.side_effect = None
        self.service.repository.get_detail.return_value = None
        self.service.repository.get_by_id.return_value = None
        with self.assertRaises(EmployeeBranchNotFoundError):
            self.service.get_assignment(999)
        with self.assertRaises(EmployeeBranchNotFoundError):
            self.service.update_status(assignment_id=999, payload=EmployeeBranchStatusUpdateRequest(estado=False))

    def test_list_filters_pagination_and_empty_result(self):
        for employee_id, branch_id, state in ((None, None, None), (3, None, None), (None, 7, None), (3, 7, False)):
            filters = dict(employee_id=employee_id, branch_id=branch_id, state=state, page=2, page_size=2)
            self.service.repository.list_assignments.return_value = ([_detail()], 3)
            data, pagination = self.service.list_assignments(**filters)
            self.assertEqual(len(data), 1)
            self.assertEqual(pagination.model_dump(), dict(page=2, page_size=2, total=3, total_pages=2))
            self.service.repository.list_assignments.assert_called_with(**filters)
        self.service.repository.list_assignments.return_value = ([], 0)
        data, pagination = self.service.list_assignments(**filters)
        self.assertEqual((data, pagination.total_pages), ([], 0))

    def test_integrity_conflict_and_persistence_rollback(self):
        self.service.repository.create.side_effect = IntegrityError("insert", {}, Exception("constraint"))
        with self.assertRaises(EmployeeBranchConflictError):
            self.service.create_assignment(_payload())
        self.service.repository.create.side_effect = None
        self.db.commit.side_effect = SQLAlchemyError("private database details")
        for operation in (
            lambda: self.service.create_assignment(_payload()),
            lambda: self.service.update_status(assignment_id=9, payload=EmployeeBranchStatusUpdateRequest(estado=False)),
        ):
            with self.assertRaises(AdminEmployeeBranchPersistenceError):
                operation()
        self.assertEqual(self.db.rollback.call_count, 3)


class EmployeeBranchRepositoryTests(TestCase):
    def test_filters_in_list_and_count_and_pagination(self):
        for employee_id, branch_id, state in ((3, None, None), (None, 7, None), (3, 7, False), (None, None, None)):
            db = MagicMock()
            db.scalar.return_value = 4
            db.execute.return_value.mappings.return_value.all.return_value = [_detail()]
            rows, total = AdminEmployeeBranchRepository(db).list_assignments(
                employee_id=employee_id, branch_id=branch_id, state=state, page=2, page_size=3,
            )
            listing = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
            count = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
            for statement in (listing, count):
                sql = str(statement)
                self.assertIn("JOIN t_empleado", sql)
                self.assertIn("JOIN t_usuario", sql)
                if employee_id is not None:
                    self.assertEqual(statement.params["id_empleado_1"], employee_id)
                if branch_id is not None:
                    self.assertEqual(statement.params["id_sucursal_1"], branch_id)
                if state is False:
                    self.assertIn("t_empleado_sucursal.estado IS false", sql)
            self.assertIn("ORDER BY t_empleado_sucursal.id_empleado_sucursal", str(listing))
            self.assertEqual(listing.params["param_1"], 3)
            self.assertEqual(listing.params["param_2"], 3)
            self.assertEqual((len(rows), total), (1, 4))

    def test_pair_lookup_uses_both_keys_and_lock(self):
        db = MagicMock()
        AdminEmployeeBranchRepository(db).get_by_pair(3, 7)
        statement = db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())
        self.assertEqual(statement.params, {"id_empleado_1": 3, "id_sucursal_1": 7})
        self.assertIn("FOR UPDATE", str(statement))

    def test_create_and_status_never_delete_or_commit_or_reset_date(self):
        db = MagicMock()
        repository = AdminEmployeeBranchRepository(db)
        assignment = repository.create(employee_id=3, branch_id=7)
        self.assertEqual((assignment.id_empleado, assignment.id_sucursal, assignment.estado), (3, 7, True))
        assignment.fecha_asignacion = date(2026, 1, 1)
        for state in (False, True):
            repository.update_status(assignment, state=state)
            self.assertEqual(assignment.estado, state)
            self.assertEqual(assignment.fecha_asignacion, date(2026, 1, 1))
        db.delete.assert_not_called()
        db.commit.assert_not_called()
        self.assertEqual(db.flush.call_count, 3)


class EmployeeBranchRouteTests(TestCase):
    def test_openapi_registration_security_and_filters(self):
        from app.main import app
        paths = app.openapi()["paths"]
        prefix = "/api/admin/employee-branches"
        for path, methods in ((prefix, ("get", "post")), (prefix + "/{id_empleado_sucursal}", ("get",)),
                              (prefix + "/{id_empleado_sucursal}/status", ("patch",))):
            self.assertEqual(set(paths[path]), set(methods))
            for method in methods:
                self.assertTrue(paths[path][method]["security"])
        parameters = {p["name"]: p["schema"] for p in paths[prefix]["get"]["parameters"]}
        self.assertEqual(set(parameters), {"id_sucursal", "id_empleado", "estado", "page", "page_size"})
        self.assertEqual(parameters["page"]["minimum"], 1)
        self.assertEqual(parameters["page_size"]["maximum"], 100)
        self.assertIn("201", paths[prefix]["post"]["responses"])
        self.assertIn("200", paths[prefix]["post"]["responses"])

    def test_denied_access_stops_all_endpoints(self):
        with patch("app.routers.admin_users.AdminUserService") as service:
            service.return_value.authenticate_administrator.side_effect = AdministratorRequiredError
            forbidden = require_administrator(HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"), MagicMock())
        unauthorized = require_administrator(None, MagicMock())
        self.assertEqual((forbidden.status_code, unauthorized.status_code), (403, 401))
        with patch.object(routes, "AdminEmployeeBranchService") as service:
            for denial in (forbidden, unauthorized):
                common = dict(administrator=denial, db=MagicMock())
                for result in (routes.list_assignable_employees(**common),
                               routes.list_assignments(**common), routes.get_assignment(9, **common),
                               routes.create_assignment(_payload(), response=Response(), **common),
                               routes.update_assignment_status(9, EmployeeBranchStatusUpdateRequest(estado=False), **common)):
                    self.assertIs(result, denial)
            service.assert_not_called()

    def test_post_status_and_response_for_creation_and_reactivation(self):
        with patch.object(routes, "AdminEmployeeBranchService") as service:
            for created, code in ((True, 201), (False, 200)):
                service.return_value.create_assignment.return_value = (AdminEmployeeBranchData(**_detail()), created)
                response = Response()
                result = routes.create_assignment(_payload(), administrator=MagicMock(), response=response, db=MagicMock())
                self.assertEqual(response.status_code, code)
                self.assertTrue(result.success)
                self.assertEqual(result.data.id_empleado_sucursal, 9)

    def test_error_codes_and_internal_details_hidden(self):
        with patch.object(routes, "AdminEmployeeBranchService") as service:
            for error, code in ((EmployeeBranchNotFoundError("No encontrado"), 404),
                                (EmployeeBranchValidationError("Inactivo"), 422),
                                (EmployeeBranchConflictError("Duplicado"), 409),
                                (AdminEmployeeBranchPersistenceError("private"), 500),
                                (SQLAlchemyError("private"), 500)):
                for method in ("create_assignment", "get_assignment", "list_assignments", "update_status"):
                    getattr(service.return_value, method).side_effect = error
                common = dict(administrator=MagicMock(), db=MagicMock())
                for result in (routes.create_assignment(_payload(), response=Response(), **common),
                               routes.get_assignment(9, **common), routes.list_assignments(**common),
                               routes.update_assignment_status(9, EmployeeBranchStatusUpdateRequest(estado=True), **common)):
                    self.assertEqual(result.status_code, code)
                    self.assertNotIn(b"private", result.body)

    def test_schema_rejects_invalid_ids_and_unrequested_fields(self):
        for values in ({}, {"id_empleado": 0, "id_sucursal": 7}, {"id_empleado": 3, "id_sucursal": -1},
                       {"id_empleado": 3, "id_sucursal": 7, "estado": False},
                       {"id_empleado": 3, "id_sucursal": 7, "fecha_asignacion": "2026-01-01"}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                EmployeeBranchCreateRequest(**values)
        for values in ({}, {"estado": None}, {"estado": True, "id_empleado": 4}):
            with self.assertRaises(ValidationError):
                EmployeeBranchStatusUpdateRequest(**values)


class AssignableEmployeeTests(TestCase):
    def test_query_uses_real_employee_profile_and_only_active_operational_roles(self):
        from app.services.admin_user_service import EMPLOYEE_ROLE_NAMES

        db = MagicMock()
        db.scalar.return_value = 2
        db.execute.return_value.mappings.return_value.all.return_value = []
        AdminEmployeeBranchRepository(db).list_assignable_employees(
            role_names=EMPLOYEE_ROLE_NAMES, page=2, page_size=1,
        )
        listing = db.execute.call_args.args[0]
        count = db.scalar.call_args.args[0]
        for statement in (listing, count):
            sql = str(statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
            ))
            self.assertIn("t_empleado.id_empleado", sql)
            self.assertIn("t_usuario.id_usuario", sql)
            self.assertIn("FROM t_empleado JOIN t_usuario ON t_usuario.id_usuario = t_empleado.id_usuario", sql)
            self.assertIn("JOIN t_rol ON t_rol.id_rol = t_usuario.id_rol", sql)
            self.assertIn("t_usuario.estado IS true", sql)
            self.assertIn("upper(t_rol.nombre) IN ('CAJERO', 'ENCARGADO_SUCURSAL')", sql)
            self.assertNotIn("CLIENTE", sql)
            self.assertNotIn("PROVEEDOR", sql)
            # No join/existence condition can exclude an employee without assignments.
            self.assertNotIn("t_empleado_sucursal", sql)
        compiled = listing.compile(dialect=postgresql.dialect())
        self.assertIn("ORDER BY t_usuario.nombre, t_usuario.apellido, t_empleado.id_empleado", str(compiled))
        self.assertEqual(compiled.params["param_1"], 1)
        self.assertEqual(compiled.params["param_2"], 1)
        db.commit.assert_not_called()
        db.add.assert_not_called()

    def test_service_preserves_distinct_ids_and_both_roles_with_pagination(self):
        from app.services.admin_user_service import EMPLOYEE_ROLE_NAMES

        service = AdminEmployeeBranchService(MagicMock())
        service.repository = MagicMock()
        rows = [dict(
            id_empleado=employee_id, id_usuario=user_id, nombre="Ana",
            apellido="Pérez", correo=f"user{user_id}@example.com", rol=role, estado=True,
        ) for employee_id, user_id, role in ((3, 50, "CAJERO"), (8, 71, "ENCARGADO_SUCURSAL"))]
        service.repository.list_assignable_employees.return_value = (rows, 3)
        data, pagination = service.list_assignable_employees(page=1, page_size=2)
        self.assertEqual([item.model_dump() for item in data], rows)
        self.assertEqual(pagination.model_dump(), dict(page=1, page_size=2, total=3, total_pages=2))
        service.repository.list_assignable_employees.assert_called_once_with(
            role_names=EMPLOYEE_ROLE_NAMES, page=1, page_size=2,
        )
        service.repository.list_assignable_employees.return_value = ([], 0)
        data, pagination = service.list_assignable_employees(page=1, page_size=20)
        self.assertEqual((data, pagination.total, pagination.total_pages), ([], 0, 0))

    def test_route_returns_list_and_safe_internal_error(self):
        from app.schemas.admin_employee_branch import EmployeeBranchPaginationData

        with patch.object(routes, "AdminEmployeeBranchService") as service:
            pagination = EmployeeBranchPaginationData(page=2, page_size=20, total=0, total_pages=0)
            service.return_value.list_assignable_employees.return_value = ([], pagination)
            result = routes.list_assignable_employees(
                administrator=MagicMock(), page=2, page_size=20, db=MagicMock(),
            )
            self.assertEqual(result.model_dump(), dict(success=True, data=[], pagination=pagination.model_dump()))
            service.return_value.list_assignable_employees.assert_called_once_with(page=2, page_size=20)
            service.return_value.list_assignable_employees.side_effect = SQLAlchemyError("private")
            result = routes.list_assignable_employees(administrator=MagicMock(), db=MagicMock())
            self.assertEqual(result.status_code, 500)
            self.assertNotIn(b"private", result.body)

    def test_static_route_precedes_detail_and_has_admin_security_and_limits(self):
        from app.main import app
        from starlette.routing import Match

        path = "/api/admin/employee-branches/options/employees"
        paths = [route.path for route in routes.router.routes]
        self.assertLess(paths.index(path), paths.index("/api/admin/employee-branches/{id_empleado_sucursal}"))
        scope = {"type": "http", "method": "GET", "path": path, "root_path": ""}
        matches = [route for route in routes.router.routes if route.matches(scope)[0] == Match.FULL]
        self.assertEqual([route.endpoint for route in matches], [routes.list_assignable_employees])
        operation = app.openapi()["paths"][path]["get"]
        self.assertTrue(operation["security"])
        self.assertIn("200", operation["responses"])
        parameters = {item["name"]: item["schema"] for item in operation["parameters"]}
        self.assertEqual(parameters["page"]["minimum"], 1)
        self.assertEqual(parameters["page_size"]["minimum"], 1)
        self.assertEqual(parameters["page_size"]["maximum"], 100)
