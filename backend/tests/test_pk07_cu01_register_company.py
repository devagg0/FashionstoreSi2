"""PK07/CU01: registro exclusivo de empresas por SUPERADMIN."""

from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.repository import CompanyRegistrationRepository
from app.PK07.CU01_RegistrarEmpresa.router import router
from app.PK07.CU01_RegistrarEmpresa.schemas import CompanyCreateRequest, CompanyData
from app.PK07.CU01_RegistrarEmpresa.service import (
    CompanyCodeAlreadyExistsError,
    CompanyNitAlreadyExistsError,
    CompanyRegistrationPersistenceError,
    CompanyRegistrationService,
)
from app.schemas.auth import AuthenticatedUserData
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError


NOW = datetime(2026, 10, 30, 12, 0, 0)


def payload(**overrides) -> CompanyCreateRequest:
    values = {
        "codigo": "moda-andina",
        "nombre": "Moda Andina SRL",
        "nit": "1020304050",
        "zona_horaria": "America/La_Paz",
    }
    values.update(overrides)
    return CompanyCreateRequest(**values)


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


def company_data(**overrides) -> CompanyData:
    return CompanyData.model_validate(vars(company_record(**overrides)))


class CompanySchemaTests(TestCase):
    def test_normalizes_text_and_accepts_optional_nit(self):
        request = payload(nombre="  Moda Andina SRL  ", nit=" 1020304050 ")
        self.assertEqual(request.nombre, "Moda Andina SRL")
        self.assertEqual(request.nit, "1020304050")
        self.assertIsNone(payload(nit="  ").nit)

    def test_rejects_invalid_code_name_nit_timezone_and_extra_fields(self):
        invalid_payloads = (
            {"codigo": "Moda-Andina"},
            {"codigo": "moda--andina"},
            {"nombre": "   "},
            {"nit": "ABC-123"},
            {"nit": "1234"},
            {"zona_horaria": "Bolivia/NoExiste"},
            {"estado": "ACTIVA"},
        )
        for changes in invalid_payloads:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                payload(**changes)

    def test_enforces_database_lengths(self):
        for changes in (
            {"codigo": "a" * 64},
            {"nombre": "a" * 151},
            {"nit": "1" * 31},
            {"zona_horaria": "a" * 51},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                payload(**changes)


class CompanyRepositoryTests(TestCase):
    def test_create_forces_active_state_and_flushes_without_commit(self):
        db = MagicMock()
        repository = CompanyRegistrationRepository(db)
        company = repository.create(
            code="moda-andina",
            name="Moda Andina SRL",
            nit=None,
            timezone="America/La_Paz",
        )
        self.assertEqual(company.estado, "ACTIVA")
        self.assertIsNone(company.nit)
        db.add.assert_called_once_with(company)
        db.flush.assert_called_once_with()
        db.commit.assert_not_called()

    def test_duplicate_lookups_use_scalar_queries(self):
        db = MagicMock()
        expected = company_record()
        db.scalar.side_effect = [expected, expected]
        repository = CompanyRegistrationRepository(db)
        self.assertIs(repository.get_by_code("moda-andina"), expected)
        self.assertIs(repository.get_by_nit("1020304050"), expected)
        self.assertEqual(db.scalar.call_count, 2)


class CompanyServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = CompanyRegistrationService(self.db)
        self.service.repository = MagicMock()
        self.service.repository.get_by_code.return_value = None
        self.service.repository.get_by_nit.return_value = None

    def test_success_commits_company_only(self):
        record = company_record()
        self.service.repository.create.return_value = record
        result = self.service.register(payload())
        self.assertEqual((result.id_empresa, result.estado), (2, "ACTIVA"))
        self.service.repository.create.assert_called_once_with(
            code="moda-andina",
            name="Moda Andina SRL",
            nit="1020304050",
            timezone="America/La_Paz",
        )
        self.db.commit.assert_called_once_with()
        self.db.rollback.assert_not_called()

    def test_duplicate_code_and_nit_rollback(self):
        self.service.repository.get_by_code.return_value = company_record()
        with self.assertRaises(CompanyCodeAlreadyExistsError):
            self.service.register(payload())
        self.db.rollback.assert_called_once_with()
        self.service.repository.create.assert_not_called()

        self.db.reset_mock()
        self.service.repository.reset_mock()
        self.service.repository.get_by_code.return_value = None
        self.service.repository.get_by_nit.return_value = company_record()
        with self.assertRaises(CompanyNitAlreadyExistsError):
            self.service.register(payload())
        self.db.rollback.assert_called_once_with()

    def test_optional_nit_skips_duplicate_lookup(self):
        self.service.repository.create.return_value = company_record(nit=None)
        self.service.register(payload(nit=None))
        self.service.repository.get_by_nit.assert_not_called()

    def test_integrity_races_map_named_unique_constraints(self):
        for constraint, expected_error in (
            ("uq_empresa_codigo", CompanyCodeAlreadyExistsError),
            ("uq_empresa_nit", CompanyNitAlreadyExistsError),
        ):
            with self.subTest(constraint=constraint):
                original = Exception("duplicate")
                original.diag = SimpleNamespace(constraint_name=constraint)
                self.service.repository.create.side_effect = IntegrityError(
                    "INSERT", {}, original
                )
                with self.assertRaises(expected_error):
                    self.service.register(payload())
                self.db.rollback.assert_called()
                self.service.repository.create.reset_mock(side_effect=True)

    def test_other_database_errors_are_safe(self):
        self.service.repository.create.side_effect = SQLAlchemyError("private")
        with self.assertRaises(CompanyRegistrationPersistenceError):
            self.service.register(payload())
        self.db.rollback.assert_called_once_with()

    def test_commit_failure_rolls_back(self):
        self.service.repository.create.return_value = company_record()
        self.db.commit.side_effect = RuntimeError("commit failure")
        with self.assertRaises(CompanyRegistrationPersistenceError):
            self.service.register(payload())
        self.db.rollback.assert_called_once_with()


class CompanyRouteTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        test_app = FastAPI()
        test_app.include_router(router)
        test_app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(test_app)
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

    def test_missing_invalid_and_non_superadmin_credentials(self):
        response = self.client.post("/api/saas/empresas", json=payload().model_dump())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

        with patch(
            "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user",
            side_effect=InvalidAccessTokenError,
        ):
            response = self.client.post(
                "/api/saas/empresas",
                headers={"Authorization": "Bearer invalid"},
                json=payload().model_dump(),
            )
        self.assertEqual(response.status_code, 401)

        with patch(
            "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user",
            side_effect=InactiveAccountError,
        ):
            response = self.client.post(
                "/api/saas/empresas",
                headers={"Authorization": "Bearer inactive"},
                json=payload().model_dump(),
            )
        self.assertEqual(response.status_code, 403)

        administrator = self.superadmin.model_copy(update={"rol": "ADMINISTRADOR", "id_empresa": 1})
        with patch(
            "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user",
            return_value=administrator,
        ):
            response = self.client.post(
                "/api/saas/empresas",
                headers={"Authorization": "Bearer signed"},
                json=payload().model_dump(),
            )
        self.assertEqual(response.status_code, 403)

    @patch(
        "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user"
    )
    @patch("app.PK07.CU01_RegistrarEmpresa.router.CompanyRegistrationService")
    def test_success_and_response_contract(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        service_class.return_value.register.return_value = company_data()
        response = self.client.post(
            "/api/saas/empresas",
            headers={"Authorization": "Bearer signed"},
            json=payload().model_dump(),
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["estado"], "ACTIVA")
        self.assertNotIn("id_plan_saas", body["data"])
        service_class.return_value.register.assert_called_once()

    @patch(
        "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user"
    )
    @patch("app.PK07.CU01_RegistrarEmpresa.router.CompanyRegistrationService")
    def test_duplicates_return_conflict(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        headers = {"Authorization": "Bearer signed"}
        for error in (CompanyCodeAlreadyExistsError, CompanyNitAlreadyExistsError):
            service_class.return_value.register.side_effect = error
            response = self.client.post(
                "/api/saas/empresas", headers=headers, json=payload().model_dump()
            )
            self.assertEqual(response.status_code, 409)

    @patch(
        "app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user"
    )
    def test_invalid_payload_returns_422_before_persistence(self, authenticate):
        authenticate.return_value = self.superadmin
        response = self.client.post(
            "/api/saas/empresas",
            headers={"Authorization": "Bearer signed"},
            json={"codigo": "INVALID CODE", "nombre": "Empresa", "nit": "abc"},
        )
        self.assertEqual(response.status_code, 422)

    def test_route_is_registered_once(self):
        schema = self.client.app.openapi()
        operation = schema["paths"]["/api/saas/empresas"]["post"]
        self.assertEqual(operation["responses"]["201"]["description"], "Successful Response")
