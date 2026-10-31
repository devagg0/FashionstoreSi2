"""PK07/CU02: gestiÃ³n exclusiva de empresas por SUPERADMIN."""

from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.service import (
    CompanyCodeAlreadyExistsError,
    CompanyNitAlreadyExistsError,
)
from app.PK07.CU02_GestionarEmpresas.repository import CompanyManagementRepository
from app.PK07.CU02_GestionarEmpresas.router import router
from app.PK07.CU02_GestionarEmpresas.schemas import (
    CompanyPaginationData,
    CompanyStateUpdateRequest,
    CompanyUpdateRequest,
)
from app.PK07.CU02_GestionarEmpresas.service import (
    CompanyManagementPersistenceError,
    CompanyManagementService,
    CompanyNotFoundError,
    CompanyStateTransitionError,
)
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import AuthenticatedUserData
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError


NOW = datetime(2026, 10, 30, 12, 0, 0)


def company_record(**overrides):
    values = {
        "id_empresa": 2,
        "codigo": "moda-andina",
        "nombre": "Moda Andina SRL",
        "nit": "1020304050",
        "zona_horaria": "America/La_Paz",
        "estado": "ACTIVA",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CompanyManagementSchemaTests(TestCase):
    def test_update_normalizes_fields_and_allows_clearing_nit(self):
        request = CompanyUpdateRequest(
            codigo=" moda-oriente ",
            nombre="  Moda Oriente  ",
            nit="   ",
            zona_horaria=" America/Lima ",
        )
        self.assertEqual(request.codigo, "moda-oriente")
        self.assertEqual(request.nombre, "Moda Oriente")
        self.assertIsNone(request.nit)
        self.assertEqual(request.zona_horaria, "America/Lima")

    def test_update_rejects_empty_invalid_forbidden_and_extra_fields(self):
        invalid = (
            {},
            {"codigo": None},
            {"codigo": "INVALID CODE"},
            {"nombre": "  "},
            {"nit": "ABC"},
            {"zona_horaria": "Bolivia/NoExiste"},
            {"id_empresa": 9},
            {"estado": "SUSPENDIDA"},
            {"administradores": []},
            {"suscripcion": None},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                CompanyUpdateRequest(**values)

    def test_state_accepts_only_database_states_and_no_extra_fields(self):
        for state in ("ACTIVA", "SUSPENDIDA", "CANCELADA"):
            self.assertEqual(CompanyStateUpdateRequest(estado=state).estado, state)
        for values in ({"estado": "INACTIVA"}, {"estado": "ACTIVA", "motivo": "x"}):
            with self.assertRaises(ValidationError):
                CompanyStateUpdateRequest(**values)


class CompanyManagementRepositoryTests(TestCase):
    def test_list_applies_search_to_name_code_nit_state_and_pagination(self):
        db = MagicMock()
        db.scalars.return_value.all.return_value = [company_record()]
        db.scalar.return_value = 1
        repository = CompanyManagementRepository(db)

        rows, total = repository.list_companies(
            search=" moda%_ ", state="ACTIVA", page=2, page_size=10
        )

        self.assertEqual((len(rows), total), (1, 1))
        statement = db.scalars.call_args.args[0]
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).lower()
        self.assertIn("t_empresa.nombre ilike", sql)
        self.assertIn("t_empresa.codigo ilike", sql)
        self.assertIn("t_empresa.nit ilike", sql)
        self.assertIn("t_empresa.estado = 'activa'", sql)
        self.assertIn("limit 10 offset 10", sql)

    def test_duplicate_lookup_can_exclude_the_current_company(self):
        db = MagicMock()
        repository = CompanyManagementRepository(db)
        repository.get_by_code("moda", exclude_company_id=7)
        repository.get_by_nit("12345", exclude_company_id=7)
        for call in db.scalar.call_args_list:
            sql = str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
            self.assertIn("t_empresa.id_empresa != 7", sql)

    def test_updates_only_the_supplied_model_and_flushes_without_commit(self):
        db = MagicMock()
        repository = CompanyManagementRepository(db)
        company = company_record()
        repository.update(company, nombre="Nuevo nombre", nit=None)
        self.assertEqual(company.nombre, "Nuevo nombre")
        self.assertIsNone(company.nit)
        self.assertGreater(company.updated_at, NOW)
        db.flush.assert_called_once_with()
        db.commit.assert_not_called()

    def test_active_membership_requires_an_active_company(self):
        db = MagicMock()
        AuthRepository(db).get_active_membership(user_id=4, company_id=2)
        statement = db.execute.call_args.args[0]
        sql = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("JOIN t_empresa", sql)
        self.assertIn("t_empresa.estado = 'ACTIVA'", sql)


class CompanyManagementServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = CompanyManagementService(self.db)
        self.service.repository = MagicMock()

    def test_lists_with_pagination_and_gets_detail(self):
        records = [company_record(), company_record(id_empresa=3, codigo="otra")]
        self.service.repository.list_companies.return_value = (records, 21)
        data, pagination = self.service.list_companies(
            search="moda", state="ACTIVA", page=2, page_size=10
        )
        self.assertEqual([item.id_empresa for item in data], [2, 3])
        self.assertEqual(
            pagination,
            CompanyPaginationData(page=2, page_size=10, total=21, total_pages=3),
        )
        self.service.repository.get_by_id.return_value = records[0]
        self.assertEqual(self.service.get_company(2).codigo, "moda-andina")
        self.db.commit.assert_not_called()

    def test_missing_detail_and_database_read_errors_are_safe(self):
        self.service.repository.get_by_id.return_value = None
        with self.assertRaises(CompanyNotFoundError):
            self.service.get_company(99)
        self.service.repository.list_companies.side_effect = SQLAlchemyError("private")
        with self.assertRaises(CompanyManagementPersistenceError):
            self.service.list_companies(search=None, state=None, page=1, page_size=20)
        self.db.rollback.assert_called_once_with()

    def test_partial_update_checks_duplicates_excluding_itself_and_commits(self):
        record = company_record()
        self.service.repository.get_by_id.return_value = record
        self.service.repository.get_by_code.return_value = None
        self.service.repository.get_by_nit.return_value = None
        payload = CompanyUpdateRequest(
            codigo="moda-oriente", nombre="Moda Oriente", nit="99887766"
        )

        result = self.service.update_company(company_id=2, payload=payload)

        self.service.repository.get_by_id.assert_called_once_with(2, for_update=True)
        self.service.repository.get_by_code.assert_called_once_with(
            "moda-oriente", exclude_company_id=2
        )
        self.service.repository.get_by_nit.assert_called_once_with(
            "99887766", exclude_company_id=2
        )
        self.service.repository.update.assert_called_once_with(
            record,
            codigo="moda-oriente",
            nombre="Moda Oriente",
            nit="99887766",
        )
        self.assertEqual(result.id_empresa, 2)
        self.db.commit.assert_called_once_with()

    def test_update_allows_clearing_nit_without_duplicate_lookup(self):
        record = company_record()
        self.service.repository.get_by_id.return_value = record
        self.service.update_company(company_id=2, payload=CompanyUpdateRequest(nit=None))
        self.service.repository.get_by_nit.assert_not_called()
        self.service.repository.update.assert_called_once_with(record, nit=None)

    def test_update_rejects_missing_and_duplicate_companies_with_rollback(self):
        self.service.repository.get_by_id.return_value = None
        with self.assertRaises(CompanyNotFoundError):
            self.service.update_company(
                company_id=99, payload=CompanyUpdateRequest(nombre="Nueva")
            )
        self.db.rollback.assert_called_once_with()

        self.db.reset_mock()
        self.service.repository.get_by_id.return_value = company_record()
        self.service.repository.get_by_code.return_value = company_record(id_empresa=3)
        with self.assertRaises(CompanyCodeAlreadyExistsError):
            self.service.update_company(
                company_id=2, payload=CompanyUpdateRequest(codigo="ocupado")
            )
        self.db.rollback.assert_called_once_with()

    def test_integrity_races_map_unique_constraints(self):
        self.service.repository.get_by_id.return_value = company_record()
        self.service.repository.get_by_code.return_value = None
        for constraint, expected in (
            ("uq_empresa_codigo", CompanyCodeAlreadyExistsError),
            ("uq_empresa_nit", CompanyNitAlreadyExistsError),
        ):
            with self.subTest(constraint=constraint):
                original = Exception("duplicate")
                original.diag = SimpleNamespace(constraint_name=constraint)
                self.service.repository.update.side_effect = IntegrityError("UPDATE", {}, original)
                payload = (
                    CompanyUpdateRequest(codigo="nuevo")
                    if constraint.endswith("codigo")
                    else CompanyUpdateRequest(nit="123456")
                )
                with self.assertRaises(expected):
                    self.service.update_company(company_id=2, payload=payload)
                self.service.repository.update.reset_mock(side_effect=True)

    def test_state_transitions_commit_and_cancellation_is_terminal(self):
        active = company_record()
        self.service.repository.get_by_id.return_value = active
        result = self.service.update_state(
            company_id=2,
            payload=CompanyStateUpdateRequest(estado="SUSPENDIDA"),
        )
        self.service.repository.update_state.assert_called_once_with(
            active, state="SUSPENDIDA"
        )
        self.assertEqual(result.id_empresa, 2)
        self.db.commit.assert_called_once_with()

        self.db.reset_mock()
        self.service.repository.reset_mock()
        self.service.repository.get_by_id.return_value = company_record(estado="CANCELADA")
        with self.assertRaises(CompanyStateTransitionError):
            self.service.update_state(
                company_id=2,
                payload=CompanyStateUpdateRequest(estado="ACTIVA"),
            )
        self.db.rollback.assert_called_once_with()
        self.service.repository.update_state.assert_not_called()


class CompanyManagementRouteTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer signed"}
        self.superadmin = AuthenticatedUserData(
            id_usuario=99,
            nombre="Global",
            apellido="Admin",
            correo="global@example.com",
            rol="SUPERADMIN",
            id_empresa=None,
        )

    def tearDown(self):
        self.client.close()

    def test_all_routes_require_jwt_and_superadmin(self):
        requests = (
            ("get", "/api/saas/empresas", None),
            ("get", "/api/saas/empresas/2", None),
            ("patch", "/api/saas/empresas/2", {"nombre": "Nueva"}),
            ("patch", "/api/saas/empresas/2/estado", {"estado": "SUSPENDIDA"}),
        )
        for method, url, body in requests:
            response = self.client.request(method, url, json=body)
            self.assertEqual(response.status_code, 401)

        administrator = self.superadmin.model_copy(
            update={"rol": "ADMINISTRADOR", "id_empresa": 1}
        )
        with patch(
            "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user",
            return_value=administrator,
        ):
            response = self.client.get("/api/saas/empresas", headers=self.headers)
        self.assertEqual(response.status_code, 403)

        with patch(
            "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user",
            side_effect=InvalidAccessTokenError,
        ):
            response = self.client.get("/api/saas/empresas", headers=self.headers)
        self.assertEqual(response.status_code, 401)

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU02_GestionarEmpresas.router.CompanyManagementService")
    def test_list_forwards_filters_and_returns_pagination(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        service_class.return_value.list_companies.return_value = (
            [],
            CompanyPaginationData(page=2, page_size=10, total=0, total_pages=0),
        )
        response = self.client.get(
            "/api/saas/empresas?search=moda&estado=ACTIVA&page=2&page_size=10",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pagination"]["page"], 2)
        service_class.return_value.list_companies.assert_called_once_with(
            search="moda", state="ACTIVA", page=2, page_size=10
        )

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU02_GestionarEmpresas.router.CompanyManagementService")
    def test_detail_update_and_state_success(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        data = company_record()
        from app.PK07.CU01_RegistrarEmpresa.schemas import CompanyData

        projected = CompanyData.model_validate(vars(data))
        service_class.return_value.get_company.return_value = projected
        service_class.return_value.update_company.return_value = projected
        service_class.return_value.update_state.return_value = projected.model_copy(
            update={"estado": "SUSPENDIDA"}
        )

        detail = self.client.get("/api/saas/empresas/2", headers=self.headers)
        update = self.client.patch(
            "/api/saas/empresas/2",
            headers=self.headers,
            json={"nombre": "Moda Oriente"},
        )
        state = self.client.patch(
            "/api/saas/empresas/2/estado",
            headers=self.headers,
            json={"estado": "SUSPENDIDA"},
        )
        self.assertEqual((detail.status_code, update.status_code, state.status_code), (200, 200, 200))
        self.assertEqual(state.json()["data"]["estado"], "SUSPENDIDA")

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU02_GestionarEmpresas.router.CompanyManagementService")
    def test_maps_not_found_duplicates_and_invalid_transition(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        service = service_class.return_value
        service.get_company.side_effect = CompanyNotFoundError
        self.assertEqual(
            self.client.get("/api/saas/empresas/99", headers=self.headers).status_code,
            404,
        )
        service.update_company.side_effect = CompanyNitAlreadyExistsError
        self.assertEqual(
            self.client.patch(
                "/api/saas/empresas/2", headers=self.headers, json={"nit": "123456"}
            ).status_code,
            409,
        )
        service.update_state.side_effect = CompanyStateTransitionError
        self.assertEqual(
            self.client.patch(
                "/api/saas/empresas/2/estado",
                headers=self.headers,
                json={"estado": "ACTIVA"},
            ).status_code,
            409,
        )

    @patch(
        "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user",
        return_value=AuthenticatedUserData(
            id_usuario=99,
            nombre="Global",
            apellido="Admin",
            correo="global@example.com",
            rol="SUPERADMIN",
            id_empresa=None,
        ),
    )
    def test_validation_blocks_identifiers_relations_bad_filters_and_delete(self, _authenticate):
        invalid_requests = (
            ("get", "/api/saas/empresas?estado=INACTIVA", None),
            ("get", "/api/saas/empresas?page=0", None),
            ("get", "/api/saas/empresas/0", None),
            ("patch", "/api/saas/empresas/2", {}),
            ("patch", "/api/saas/empresas/2", {"id_empresa": 3}),
            ("patch", "/api/saas/empresas/2", {"suscripcion": 4}),
            ("patch", "/api/saas/empresas/2/estado", {"estado": "INACTIVA"}),
        )
        for method, url, body in invalid_requests:
            with self.subTest(method=method, url=url):
                response = self.client.request(method, url, headers=self.headers, json=body)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self.client.delete("/api/saas/empresas/2", headers=self.headers).status_code,
            405,
        )

    def test_openapi_registers_management_without_physical_delete(self):
        paths = self.client.app.openapi()["paths"]
        self.assertEqual(set(paths["/api/saas/empresas"]), {"get"})
        self.assertEqual(set(paths["/api/saas/empresas/{id_empresa}"]), {"get", "patch"})
        self.assertEqual(set(paths["/api/saas/empresas/{id_empresa}/estado"]), {"patch"})
