"""PK07/CU03: asignación y consulta de administrador de empresa por SUPERADMIN."""

from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.database import get_db
from app.PK07.CU03_AsignarAdministradorEmpresa.repository import CompanyAdminRepository
from app.PK07.CU03_AsignarAdministradorEmpresa.router import router
from app.PK07.CU03_AsignarAdministradorEmpresa.schemas import (
    AssignCompanyAdminRequest,
    AvailableUsersPaginationData,
    CompanyAdminData,
    CreateAndAssignCompanyAdminRequest,
)
from app.PK07.CU03_AsignarAdministradorEmpresa.service import (
    AdminAssignmentNotFoundError,
    AdminRoleNotConfiguredError,
    CannotAssignSuperadminError,
    CompanyAdminPersistenceError,
    CompanyAdminService,
    CompanyNotActiveError,
    CompanyNotFoundError,
    EmailAlreadyExistsError,
    UserAlreadyAssignedError,
    UserAlreadyAssignedToOtherCompanyError,
    UserInactiveError,
    UserNotEligibleRoleError,
    UserNotFoundError,
)
from app.core.security import decode_access_token
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import AuthenticatedUserData, LoginRequest
from app.services.auth_service import AuthService, InactiveAccountError, InvalidAccessTokenError


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


def user_record(**overrides):
    values = {
        "id_usuario": 10,
        "id_rol": 2,
        "nombre": "Carlos",
        "apellido": "Gomez",
        "correo": "carlos.gomez@example.com",
        "telefono": "78901234",
        "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def role_record(**overrides):
    values = {
        "id_rol": 2,
        "nombre": "ADMINISTRADOR",
        "descripcion": "Administrador de empresa",
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def membership_record(**overrides):
    values = {
        "id_empresa": 2,
        "id_usuario": 10,
        "id_rol": 2,
        "estado": "ACTIVO",
        "es_propietario": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def admin_data(**overrides) -> CompanyAdminData:
    values = {
        "id_empresa": 2,
        "id_usuario": 10,
        "nombre": "Carlos",
        "apellido": "Gomez",
        "correo": "carlos.gomez@example.com",
        "telefono": "78901234",
        "rol": "ADMINISTRADOR",
        "estado": "ACTIVO",
        "es_propietario": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return CompanyAdminData(**values)


class CompanyAdminSchemaTests(TestCase):
    def test_assign_request_valid_and_defaults(self):
        req = AssignCompanyAdminRequest(id_usuario=10)
        self.assertEqual(req.id_usuario, 10)
        self.assertEqual(req.estado, "ACTIVO")

        req_invited = AssignCompanyAdminRequest(id_usuario=10, estado="INVITADO")
        self.assertEqual(req_invited.estado, "INVITADO")

    def test_assign_request_rejects_invalid_values_and_extra_fields(self):
        for invalid in (
            {"id_usuario": 0},
            {"id_usuario": -5},
            {"id_usuario": 10, "estado": "INACTIVO"},
            {"id_usuario": 10, "estado": "RETIRADO"},
            {"id_usuario": 10, "extra": "prohibido"},
            {},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                AssignCompanyAdminRequest(**invalid)

    def test_create_and_assign_request_valid(self):
        req = CreateAndAssignCompanyAdminRequest(
            nombre="Laura",
            apellido="Mendoza",
            correo="laura.mendoza@fashionstore.com",
            password="Password123!",
            telefono="71234567",
        )
        self.assertEqual(req.nombre, "Laura")
        self.assertEqual(req.apellido, "Mendoza")
        self.assertEqual(req.correo, "laura.mendoza@fashionstore.com")
        self.assertEqual(req.password.get_secret_value(), "Password123!")
        self.assertEqual(req.telefono, "71234567")
        self.assertEqual(req.estado, "ACTIVO")

    def test_create_and_assign_request_rejects_weak_passwords(self):
        weak_passwords = [
            "short1!",        # menos de 8
            "alllowercase1!", # sin mayúscula
            "ALLUPPERCASE1!", # sin minúscula
            "NoDigitsAtAll!", # sin dígitos
            "NoSpecialChar1", # sin carácter especial
        ]
        for pwd in weak_passwords:
            with self.subTest(pwd=pwd), self.assertRaises(ValidationError):
                CreateAndAssignCompanyAdminRequest(
                    nombre="Test",
                    apellido="Admin",
                    correo="test@example.com",
                    password=pwd,
                )

    def test_create_and_assign_request_rejects_extra_fields(self):
        with self.assertRaises(ValidationError):
            CreateAndAssignCompanyAdminRequest(
                nombre="Test",
                apellido="Admin",
                correo="test@example.com",
                password="Password123!",
                campo_extra="prohibido",
            )

    def test_pagination_data_calculation(self):
        p1 = AvailableUsersPaginationData.create(page=1, page_size=20, total=45)
        self.assertEqual(p1.total_pages, 3)

        p2 = AvailableUsersPaginationData.create(page=1, page_size=20, total=0)
        self.assertEqual(p2.total_pages, 0)


class CompanyAdminRepositoryTests(TestCase):
    def test_get_company_and_get_user_with_role(self):
        db = MagicMock()
        company = company_record()
        db.get.return_value = company
        repo = CompanyAdminRepository(db)

        self.assertIs(repo.get_company(2), company)
        db.get.assert_called_once()

        db.execute.return_value.one_or_none.return_value = (user_record(), role_record())
        user_role = repo.get_user_with_role(10)
        self.assertIsNotNone(user_role)
        self.assertEqual(user_role[0].id_usuario, 10)
        self.assertEqual(user_role[1].nombre, "ADMINISTRADOR")

    def test_get_assigned_admin_prefers_owner(self):
        db = MagicMock()
        owner_tuple = (membership_record(es_propietario=True), user_record(), role_record())
        db.execute.return_value.one_or_none.return_value = owner_tuple

        repo = CompanyAdminRepository(db)
        admin = repo.get_assigned_admin(2)
        self.assertEqual(admin, owner_tuple)

    def test_get_assigned_admin_falls_back_to_admin_membership(self):
        db = MagicMock()
        fallback_tuple = (membership_record(es_propietario=False), user_record(), role_record())
        db.execute.return_value.one_or_none.return_value = None
        db.execute.return_value.first.return_value = fallback_tuple

        repo = CompanyAdminRepository(db)
        admin = repo.get_assigned_admin(2)
        self.assertEqual(admin, fallback_tuple)

    def test_clear_existing_owner_modifies_previous_owner(self):
        db = MagicMock()
        prev_owner = membership_record(id_usuario=5, es_propietario=True)
        db.scalars.return_value.all.return_value = [prev_owner]

        repo = CompanyAdminRepository(db)
        repo.clear_existing_owner(2, exclude_user_id=10)

        self.assertFalse(prev_owner.es_propietario)
        db.flush.assert_called_once()

    def test_save_admin_membership_updates_existing_row(self):
        db = MagicMock()
        existing = membership_record(id_usuario=10, es_propietario=False, estado="INVITADO")
        db.get.return_value = existing

        repo = CompanyAdminRepository(db)
        result = repo.save_admin_membership(
            company_id=2,
            user_id=10,
            role_id=2,
            state="ACTIVO",
        )
        self.assertIs(result, existing)
        self.assertTrue(result.es_propietario)
        self.assertEqual(result.estado, "ACTIVO")
        db.flush.assert_called_once()
        db.add.assert_not_called()

    def test_save_admin_membership_creates_new_row_if_missing(self):
        db = MagicMock()
        db.get.return_value = None

        repo = CompanyAdminRepository(db)
        result = repo.save_admin_membership(
            company_id=2,
            user_id=10,
            role_id=2,
            state="ACTIVO",
        )
        self.assertEqual(result.id_empresa, 2)
        self.assertEqual(result.id_usuario, 10)
        self.assertTrue(result.es_propietario)
        db.add.assert_called_once_with(result)
        db.flush.assert_called_once()

    def test_get_other_company_ownership(self):
        db = MagicMock()
        repo = CompanyAdminRepository(db)
        repo.get_other_company_ownership(user_id=10, exclude_company_id=2)

        statement = db.scalars.call_args[0][0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("t_usuario_empresa.id_usuario = 10", compiled)
        self.assertIn("t_usuario_empresa.es_propietario IS true", compiled)
        self.assertIn("t_usuario_empresa.id_empresa != 2", compiled)

    def test_search_available_users_filters_and_excludes_other_owners(self):
        db = MagicMock()
        db.scalar.return_value = 1
        db.execute.return_value.all.return_value = [(user_record(), role_record(nombre="ADMINISTRADOR"))]

        repo = CompanyAdminRepository(db)
        results, total = repo.search_available_users(search="carlos", company_id=2, page=1, page_size=10)

        self.assertEqual(total, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0].nombre, "Carlos")

        statement = db.execute.call_args[0][0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("NOT (EXISTS (SELECT 1", compiled)
        self.assertIn("t_usuario_empresa.id_empresa != 2", compiled)

    def test_get_user_by_email_and_create_admin_user(self):
        db = MagicMock()
        db.scalar.return_value = user_record(correo="nuevo@fs.com")

        repo = CompanyAdminRepository(db)
        found = repo.get_user_by_email("nuevo@fs.com")
        self.assertIsNotNone(found)
        self.assertEqual(found.correo, "nuevo@fs.com")

        created = repo.create_admin_user(
            first_name="Nuevo",
            last_name="Admin",
            email="nuevo@fs.com",
            password_hash="argon2hash",
            role_id=2,
            phone="70012345",
        )
        db.add.assert_called_once()
        db.flush.assert_called_once()
        self.assertEqual(created.nombre, "Nuevo")
        self.assertEqual(created.correo, "nuevo@fs.com")


class CompanyAdminServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = CompanyAdminService(self.db)
        self.service.repository = MagicMock()
        self.service.repository.get_other_company_ownership.return_value = None

    def test_get_assigned_admin_success(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_assigned_admin.return_value = (
            membership_record(),
            user_record(),
            role_record(),
        )

        data = self.service.get_assigned_admin(2)
        self.assertEqual(data.id_empresa, 2)
        self.assertEqual(data.id_usuario, 10)
        self.assertEqual(data.rol, "ADMINISTRADOR")
        self.assertTrue(data.es_propietario)

    def test_get_assigned_admin_company_not_found(self):
        self.service.repository.get_company.return_value = None
        with self.assertRaises(CompanyNotFoundError):
            self.service.get_assigned_admin(999)

    def test_get_assigned_admin_not_assigned(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_assigned_admin.return_value = None
        with self.assertRaises(AdminAssignmentNotFoundError):
            self.service.get_assigned_admin(2)

    def test_search_available_users_success(self):
        self.service.repository.search_available_users.return_value = (
            [(user_record(), role_record(nombre="ADMINISTRADOR"))],
            1,
        )
        data, pagination = self.service.search_available_users(search="carlos", company_id=2, page=1, page_size=20)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0].id_usuario, 10)
        self.assertEqual(data[0].rol_global, "ADMINISTRADOR")
        self.assertEqual(pagination.total, 1)
        self.service.repository.search_available_users.assert_called_with(
            search="carlos",
            company_id=2,
            page=1,
            page_size=20,
        )

    def test_assign_admin_success(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (user_record(), role_record(nombre="ADMINISTRADOR"))
        self.service.repository.get_other_company_ownership.return_value = None
        self.service.repository.get_role_by_name.return_value = role_record()
        self.service.repository.get_assigned_admin.return_value = None
        self.service.repository.save_admin_membership.return_value = membership_record()

        req = AssignCompanyAdminRequest(id_usuario=10)
        res = self.service.assign_admin(2, req)

        self.assertEqual(res.id_empresa, 2)
        self.assertEqual(res.id_usuario, 10)
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()

    def test_assign_admin_rejects_user_already_admin_of_another_company(self):
        self.service.repository.get_company.return_value = company_record(id_empresa=2)
        self.service.repository.get_user_with_role.return_value = (
            user_record(id_usuario=10),
            role_record(nombre="ADMINISTRADOR"),
        )
        # El usuario ya es titular en empresa 5
        self.service.repository.get_other_company_ownership.return_value = membership_record(
            id_empresa=5,
            id_usuario=10,
            es_propietario=True,
        )

        with self.assertRaises(UserAlreadyAssignedToOtherCompanyError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_assign_admin_rejects_ineligible_roles(self):
        ineligible_roles = ["CLIENTE", "CAJERO", "ENCARGADO_SUCURSAL"]
        for role_name in ineligible_roles:
            with self.subTest(role=role_name):
                self.service.repository.get_company.return_value = company_record()
                self.service.repository.get_user_with_role.return_value = (
                    user_record(),
                    role_record(nombre=role_name),
                )
                with self.assertRaises(UserNotEligibleRoleError):
                    self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
                self.db.rollback.assert_called()

    def test_assign_admin_reassign_clears_previous_owner(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (
            user_record(id_usuario=20),
            role_record(nombre="ADMINISTRADOR"),
        )
        self.service.repository.get_other_company_ownership.return_value = None
        self.service.repository.get_role_by_name.return_value = role_record()
        self.service.repository.get_assigned_admin.return_value = (
            membership_record(id_usuario=10),
            user_record(id_usuario=10),
            role_record(),
        )
        self.service.repository.save_admin_membership.return_value = membership_record(id_usuario=20)

        req = AssignCompanyAdminRequest(id_usuario=20)
        res = self.service.assign_admin(2, req)

        self.assertEqual(res.id_usuario, 20)
        self.service.repository.clear_existing_owner.assert_called_once_with(2, exclude_user_id=20)
        self.db.commit.assert_called_once()

    def test_assign_admin_rejects_inactive_company(self):
        self.service.repository.get_company.return_value = company_record(estado="SUSPENDIDA")
        with self.assertRaises(CompanyNotActiveError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_assign_admin_rejects_missing_company(self):
        self.service.repository.get_company.return_value = None
        with self.assertRaises(CompanyNotFoundError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_assign_admin_rejects_missing_user(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = None
        with self.assertRaises(UserNotFoundError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_assign_admin_rejects_inactive_user(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (user_record(estado=False), role_record())
        with self.assertRaises(UserInactiveError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_assign_admin_rejects_superadmin_user(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (user_record(), role_record(nombre="SUPERADMIN"))
        with self.assertRaises(CannotAssignSuperadminError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_assign_admin_rejects_duplicate_active_assignment(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (user_record(), role_record(nombre="ADMINISTRADOR"))
        self.service.repository.get_role_by_name.return_value = role_record()
        self.service.repository.get_assigned_admin.return_value = (
            membership_record(id_usuario=10, es_propietario=True, estado="ACTIVO"),
            user_record(id_usuario=10),
            role_record(),
        )

        with self.assertRaises(UserAlreadyAssignedError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10, estado="ACTIVO"))
        self.db.rollback.assert_called_once()

    def test_assign_admin_maps_unique_owner_constraint_race(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (user_record(), role_record(nombre="ADMINISTRADOR"))
        self.service.repository.get_role_by_name.return_value = role_record()
        self.service.repository.get_assigned_admin.return_value = None

        original = Exception("duplicate owner")
        original.diag = SimpleNamespace(constraint_name="uq_usuario_empresa_propietario")
        self.service.repository.save_admin_membership.side_effect = IntegrityError("INSERT", {}, original)

        with self.assertRaises(UserAlreadyAssignedError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_assign_admin_maps_other_db_errors_safely(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (user_record(), role_record(nombre="ADMINISTRADOR"))
        self.service.repository.get_role_by_name.return_value = role_record()
        self.service.repository.get_assigned_admin.return_value = None
        self.service.repository.save_admin_membership.side_effect = SQLAlchemyError("db error")

        with self.assertRaises(CompanyAdminPersistenceError):
            self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))
        self.db.rollback.assert_called_once()

    def test_create_and_assign_admin_success(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_role_by_name.return_value = role_record(id_rol=2)
        self.service.repository.get_user_by_email.return_value = None
        new_user = user_record(id_usuario=55, correo="nuevo.admin@fs.com")
        self.service.repository.create_admin_user.return_value = new_user
        self.service.repository.save_admin_membership.return_value = membership_record(id_usuario=55)

        payload = CreateAndAssignCompanyAdminRequest(
            nombre="Nuevo",
            apellido="Admin",
            correo="nuevo.admin@fs.com",
            password="SecurePassword2026!",
            telefono="71234567",
        )
        res = self.service.create_and_assign_admin(2, payload)

        self.assertEqual(res.id_usuario, 55)
        self.assertEqual(res.id_empresa, 2)
        self.service.repository.create_admin_user.assert_called_once()
        self.service.repository.clear_existing_owner.assert_called_once_with(2, exclude_user_id=55)
        self.service.repository.save_admin_membership.assert_called_once_with(
            company_id=2,
            user_id=55,
            role_id=2,
            state="ACTIVO",
        )
        self.db.commit.assert_called_once()

    def test_create_and_assign_admin_duplicate_email(self):
        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_role_by_name.return_value = role_record()
        self.service.repository.get_user_by_email.return_value = user_record(correo="existente@fs.com")

        payload = CreateAndAssignCompanyAdminRequest(
            nombre="Existente",
            apellido="User",
            correo="existente@fs.com",
            password="SecurePassword2026!",
        )
        with self.assertRaises(EmailAlreadyExistsError):
            self.service.create_and_assign_admin(2, payload)
        self.db.rollback.assert_called_once()


class CompanyAdminRouteTests(TestCase):
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
            correo="superadmin@fashionstore.com",
            rol="SUPERADMIN",
            id_empresa=None,
        )

    def tearDown(self):
        self.client.close()

    def test_authentication_and_authorization_guards(self):
        # 1. Sin credenciales -> 401
        res = self.client.get("/api/saas/empresas/2/administrador")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.headers.get("www-authenticate"), "Bearer")

        # 2. Token inválido -> 401
        with patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user", side_effect=InvalidAccessTokenError):
            res = self.client.get(
                "/api/saas/empresas/2/administrador",
                headers={"Authorization": "Bearer invalid"},
            )
            self.assertEqual(res.status_code, 401)

        # 3. Cuenta inactiva -> 403
        with patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user", side_effect=InactiveAccountError):
            res = self.client.get(
                "/api/saas/empresas/2/administrador",
                headers={"Authorization": "Bearer inactive"},
            )
            self.assertEqual(res.status_code, 403)

        # 4. Rol no SUPERADMIN -> 403
        normal_admin = self.superadmin.model_copy(update={"rol": "ADMINISTRADOR", "id_empresa": 2})
        with patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user", return_value=normal_admin):
            res = self.client.get(
                "/api/saas/empresas/2/administrador",
                headers={"Authorization": "Bearer signed"},
            )
            self.assertEqual(res.status_code, 403)

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU03_AsignarAdministradorEmpresa.router.CompanyAdminService")
    def test_get_assigned_admin_endpoints(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        headers = {"Authorization": "Bearer signed"}

        # Éxito 200
        service_class.return_value.get_assigned_admin.return_value = admin_data()
        res = self.client.get("/api/saas/empresas/2/administrador", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["data"]["id_usuario"], 10)

        # Empresa no encontrada 404
        service_class.return_value.get_assigned_admin.side_effect = CompanyNotFoundError
        res = self.client.get("/api/saas/empresas/999/administrador", headers=headers)
        self.assertEqual(res.status_code, 404)

        # Sin administrador asignado 404
        service_class.return_value.get_assigned_admin.side_effect = AdminAssignmentNotFoundError
        res = self.client.get("/api/saas/empresas/2/administrador", headers=headers)
        self.assertEqual(res.status_code, 404)

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU03_AsignarAdministradorEmpresa.router.CompanyAdminService")
    def test_list_available_users_endpoint(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        headers = {"Authorization": "Bearer signed"}

        service_class.return_value.search_available_users.return_value = (
            [
                {
                    "id_usuario": 10,
                    "nombre": "Carlos",
                    "apellido": "Gomez",
                    "correo": "carlos@example.com",
                    "telefono": "78901234",
                    "rol_global": "ADMINISTRADOR",
                    "estado": True,
                    "created_at": NOW,
                }
            ],
            AvailableUsersPaginationData(page=1, page_size=20, total=1, total_pages=1),
        )

        res = self.client.get("/api/saas/usuarios-disponibles?search=carlos&empresa_id=2", headers=headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["pagination"]["total"], 1)
        service_class.return_value.search_available_users.assert_called_with(
            search="carlos",
            company_id=2,
            page=1,
            page_size=20,
        )

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU03_AsignarAdministradorEmpresa.router.CompanyAdminService")
    def test_post_assign_admin_endpoint_success_and_errors(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        headers = {"Authorization": "Bearer signed"}

        # Éxito 201 con id_usuario existente
        service_class.return_value.assign_admin.return_value = admin_data()
        res = self.client.post(
            "/api/saas/empresas/2/administrador",
            headers=headers,
            json={"id_usuario": 10},
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["data"]["id_usuario"], 10)

        # Validación 422: payload inválido
        res = self.client.post(
            "/api/saas/empresas/2/administrador",
            headers=headers,
            json={"id_usuario": -1},
        )
        self.assertEqual(res.status_code, 422)

        # Errores de negocio
        conflicts = (
            (CompanyNotActiveError, 409),
            (UserInactiveError, 409),
            (CannotAssignSuperadminError, 409),
            (UserNotEligibleRoleError, 409),
            (UserAlreadyAssignedToOtherCompanyError, 409),
            (EmailAlreadyExistsError, 409),
            (UserAlreadyAssignedError, 409),
            (CompanyNotFoundError, 404),
            (UserNotFoundError, 404),
            (AdminRoleNotConfiguredError, 500),
        )
        for error_type, expected_code in conflicts:
            with self.subTest(error=error_type):
                service_class.return_value.assign_admin.side_effect = error_type
                res = self.client.post(
                    "/api/saas/empresas/2/administrador",
                    headers=headers,
                    json={"id_usuario": 10},
                )
                self.assertEqual(res.status_code, expected_code)
                self.assertFalse(res.json()["success"])

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU03_AsignarAdministradorEmpresa.router.CompanyAdminService")
    def test_post_create_and_assign_admin_endpoint(self, service_class, authenticate):
        authenticate.return_value = self.superadmin
        headers = {"Authorization": "Bearer signed"}

        valid_payload = {
            "nombre": "Mariana",
            "apellido": "Rios",
            "correo": "mariana.rios@fs.com",
            "password": "Password123!",
            "telefono": "78901234",
        }

        # 1. Éxito 201 en /empresas/{id}/administrador/nuevo
        service_class.return_value.create_and_assign_admin.return_value = admin_data(
            id_usuario=50,
            nombre="Mariana",
            apellido="Rios",
            correo="mariana.rios@fs.com",
        )
        res = self.client.post(
            "/api/saas/empresas/2/administrador/nuevo",
            headers=headers,
            json=valid_payload,
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["data"]["correo"], "mariana.rios@fs.com")

        # 2. Correo duplicado 409
        service_class.return_value.create_and_assign_admin.side_effect = EmailAlreadyExistsError
        res = self.client.post(
            "/api/saas/empresas/2/administrador/nuevo",
            headers=headers,
            json=valid_payload,
        )
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.json()["success"])

        # 3. Contraseña débil 422
        weak_payload = dict(valid_payload, password="weak")
        res = self.client.post(
            "/api/saas/empresas/2/administrador/nuevo",
            headers=headers,
            json=weak_payload,
        )
        self.assertEqual(res.status_code, 422)

    def test_openapi_documentation_registered(self):
        schema = self.client.app.openapi()
        paths = schema["paths"]
        self.assertIn("/api/saas/empresas/{id}/administrador", paths)
        self.assertIn("get", paths["/api/saas/empresas/{id}/administrador"])
        self.assertIn("post", paths["/api/saas/empresas/{id}/administrador"])
        self.assertIn("/api/saas/empresas/{id}/administrador/nuevo", paths)
        self.assertIn("post", paths["/api/saas/empresas/{id}/administrador/nuevo"])
        self.assertIn("/api/saas/usuarios-disponibles", paths)
        self.assertIn("get", paths["/api/saas/usuarios-disponibles"])


class CompanyAdminMultitenantIntegrityTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = CompanyAdminService(self.db)
        self.service.repository = MagicMock()

    def test_user_credentials_and_attributes_remain_intact(self):
        user = user_record()
        original_hash = user.password_hash
        original_email = user.correo
        original_role_id = user.id_rol

        self.service.repository.get_company.return_value = company_record()
        self.service.repository.get_user_with_role.return_value = (user, role_record(nombre="ADMINISTRADOR"))
        self.service.repository.get_other_company_ownership.return_value = None
        self.service.repository.get_role_by_name.return_value = role_record()
        self.service.repository.get_assigned_admin.return_value = None
        self.service.repository.save_admin_membership.return_value = membership_record()

        self.service.assign_admin(2, AssignCompanyAdminRequest(id_usuario=10))

        # El usuario global nunca se altera
        self.assertEqual(user.password_hash, original_hash)
        self.assertEqual(user.correo, original_email)
        self.assertEqual(user.id_rol, original_role_id)

    def test_membership_strictly_scoped_to_empresa_id(self):
        self.service.repository.get_company.return_value = company_record(id_empresa=5)
        self.service.repository.get_user_with_role.return_value = (user_record(), role_record(nombre="ADMINISTRADOR"))
        self.service.repository.get_other_company_ownership.return_value = None
        self.service.repository.get_role_by_name.return_value = role_record(id_rol=2)
        self.service.repository.get_assigned_admin.return_value = None
        self.service.repository.save_admin_membership.return_value = membership_record(id_empresa=5)

        res = self.service.assign_admin(5, AssignCompanyAdminRequest(id_usuario=10))

        self.assertEqual(res.id_empresa, 5)
        self.service.repository.save_admin_membership.assert_called_once_with(
            company_id=5,
            user_id=10,
            role_id=2,
            state="ACTIVO",
        )

    def test_clear_owner_strictly_scopes_by_company(self):
        db = MagicMock()
        repo = CompanyAdminRepository(db)
        repo.clear_existing_owner(company_id=3, exclude_user_id=10)

        # La consulta generada debe incluir el filtro por id_empresa == 3
        statement = db.scalars.call_args[0][0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("t_usuario_empresa.id_empresa = 3", compiled)
        self.assertIn("t_usuario_empresa.es_propietario IS true", compiled)
        self.assertIn("t_usuario_empresa.id_usuario != 10", compiled)



class CompanyAdminLoginIntegrationTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.info = {}
        self.service = CompanyAdminService(self.db)
        self.service.repository = MagicMock()
        self.auth_service = AuthService(self.db)
        self.auth_service.repository = MagicMock()

    def test_auth_repository_get_active_membership_query_structure(self):
        db = MagicMock()
        repo = AuthRepository(db)

        # 1. Sin company_id (flujo login) -> busca membresía activa del usuario ordenada por es_propietario
        repo.get_active_membership(user_id=12)
        statement = db.execute.call_args[0][0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("t_usuario_empresa.id_usuario = 12", compiled)
        self.assertIn("t_usuario_empresa.estado = 'ACTIVO'", compiled)
        self.assertIn("t_rol.estado IS true", compiled)
        self.assertIn("t_empresa.estado = 'ACTIVA'", compiled)
        self.assertIn("ORDER BY t_usuario_empresa.es_propietario DESC, t_usuario_empresa.created_at ASC", compiled)

        # 2. Con company_id (flujo token/validación específica) -> filtra además por empresa
        db.reset_mock()
        repo.get_active_membership(user_id=12, company_id=2)
        statement2 = db.execute.call_args[0][0]
        compiled2 = str(statement2.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("t_usuario_empresa.id_usuario = 12", compiled2)
        self.assertIn("t_usuario_empresa.id_empresa = 2", compiled2)
        self.assertIn("t_usuario_empresa.estado = 'ACTIVO'", compiled2)

    @patch("app.services.auth_service.verify_password", return_value=True)
    def test_creation_then_login_flow_assigns_tenant_company(self, _mock_verify):
        # 1. CU03 crea y asocia nuevo administrador a la empresa 2 (Moda Oriente SRL)
        company = company_record(id_empresa=2, nombre="Moda Oriente SRL")
        admin_role = role_record(id_rol=1, nombre="ADMINISTRADOR")
        new_user = user_record(
            id_usuario=12,
            correo="mariaadmin@gmail.com",
            nombre="Maria",
            apellido="Garcia",
            id_rol=1,
            estado=True,
        )
        membership = membership_record(
            id_empresa=2,
            id_usuario=12,
            id_rol=1,
            estado="ACTIVO",
            es_propietario=True,
        )

        self.service.repository.get_company.return_value = company
        self.service.repository.get_role_by_name.return_value = admin_role
        self.service.repository.get_user_by_email.return_value = None
        self.service.repository.create_admin_user.return_value = new_user
        self.service.repository.save_admin_membership.return_value = membership

        create_payload = CreateAndAssignCompanyAdminRequest(
            nombre="Maria",
            apellido="Garcia",
            correo="mariaadmin@gmail.com",
            password="SecurePassword2026!",
            telefono="77889900",
            estado="ACTIVO",
        )
        created_data = self.service.create_and_assign_admin(2, create_payload)
        self.assertEqual(created_data.id_empresa, 2)
        self.assertEqual(created_data.id_usuario, 12)
        self.assertEqual(created_data.rol, "ADMINISTRADOR")

        # 2. Login con las credenciales del administrador recién creado
        self.auth_service.repository.get_user_by_email.return_value = new_user
        self.auth_service.repository.get_role_by_id.return_value = admin_role
        self.auth_service.repository.get_active_membership.return_value = (membership, admin_role)

        login_payload = LoginRequest(
            correo="mariaadmin@gmail.com",
            password="SecurePassword2026!",
        )
        login_res = self.auth_service.login(login_payload)

        # 3. Validar respuesta de login y datos multitenant
        self.assertTrue(login_res.success)
        self.assertEqual(login_res.usuario.id_usuario, 12)
        self.assertEqual(login_res.usuario.correo, "mariaadmin@gmail.com")
        self.assertEqual(login_res.usuario.rol, "ADMINISTRADOR")
        self.assertEqual(login_res.usuario.id_empresa, 2)
        self.assertEqual(self.db.info.get("empresa_id"), 2)
        self.assertFalse(self.db.info.get("is_superadmin", False))

        # 4. Validar que el token decodificado contiene empresa_id=2
        token_payload = decode_access_token(login_res.access_token)
        self.assertEqual(token_payload["sub"], "12")
        self.assertEqual(token_payload["role"], "ADMINISTRADOR")
        self.assertEqual(token_payload["empresa_id"], 2)

        # 5. Validar get_current_user con el token emitido y contexto multitenant
        self.auth_service.repository.get_user_by_id.return_value = new_user
        user_from_token = self.auth_service.get_current_user(login_res.access_token)
        self.assertEqual(user_from_token.id_empresa, 2)
        self.assertEqual(user_from_token.rol, "ADMINISTRADOR")
        self.assertEqual(self.db.info.get("empresa_id"), 2)

    @patch("app.services.auth_service.verify_password", return_value=True)
    def test_login_rejects_inactive_membership(self, _mock_verify):
        user = user_record(id_usuario=15, id_rol=1, estado=True)
        admin_role = role_record(id_rol=1, nombre="ADMINISTRADOR")

        self.auth_service.repository.get_user_by_email.return_value = user
        self.auth_service.repository.get_role_by_id.return_value = admin_role
        self.auth_service.repository.get_active_membership.return_value = None

        with self.assertRaises(InactiveAccountError):
            self.auth_service.login(
                LoginRequest(correo="inactivo@example.com", password="Password123!")
            )

    @patch("app.services.auth_service.verify_password", return_value=True)
    def test_multitenant_isolation_per_company(self, _mock_verify):
        role = role_record(id_rol=1, nombre="ADMINISTRADOR")

        # Empresa 1
        user_emp1 = user_record(id_usuario=20, id_rol=1)
        mem_emp1 = membership_record(id_empresa=1, id_usuario=20)
        self.auth_service.repository.get_user_by_email.return_value = user_emp1
        self.auth_service.repository.get_role_by_id.return_value = role
        self.auth_service.repository.get_active_membership.return_value = (mem_emp1, role)

        res1 = self.auth_service.login(LoginRequest(correo="emp1@test.com", password="Pass1!"))
        self.assertEqual(res1.usuario.id_empresa, 1)
        self.assertEqual(self.db.info.get("empresa_id"), 1)

        # Empresa 2
        user_emp2 = user_record(id_usuario=21, id_rol=1)
        mem_emp2 = membership_record(id_empresa=2, id_usuario=21)
        self.auth_service.repository.get_user_by_email.return_value = user_emp2
        self.auth_service.repository.get_active_membership.return_value = (mem_emp2, role)

        res2 = self.auth_service.login(LoginRequest(correo="emp2@test.com", password="Pass2!"))
        self.assertEqual(res2.usuario.id_empresa, 2)
        self.assertEqual(self.db.info.get("empresa_id"), 2)
