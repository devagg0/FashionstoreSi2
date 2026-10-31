"""Pruebas unitarias y de integración para PK07 / CU04: Asociar usuarios y sucursales a empresa."""

from datetime import datetime, time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.repository import CompanyResourcesRepository
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.router import router
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.schemas import (
    AssociateExistingBranchRequest,
    AssociateUserRequest,
    CompanyBranchData,
    CompanyResourcesData,
    CompanyUserData,
    CreateCompanyBranchRequest,
)
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.service import (
    AdministratorRoleNotAllowedInCU04Error,
    BranchAlreadyAssociatedError,
    BranchBelongsToAnotherCompanyError,
    BranchCityInactiveError,
    BranchCityNotFoundError,
    BranchNotFoundError,
    CannotAssignSuperadminError,
    CompanyNotActiveError,
    CompanyNotFoundError,
    CompanyResourcesService,
    OwnershipAssignmentNotAllowedInCU04Error,
    RoleNotConfiguredError,
    UserAlreadyAssociatedError,
    UserAlreadyOwnerOfOtherCompanyError,
    UserInactiveError,
    UserNotFoundError,
)
from app.schemas.auth import AuthenticatedUserData


NOW = datetime(2026, 10, 30, 12, 0, 0)


def dummy_company(**overrides):
    values = {
        "id_empresa": 2,
        "codigo": "moda-oriente",
        "nombre": "Moda Oriente SRL",
        "estado": "ACTIVA",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def dummy_user(**overrides):
    values = {
        "id_usuario": 10,
        "id_rol": 3,
        "nombre": "Carlos",
        "apellido": "Gomez",
        "correo": "carlos@example.com",
        "telefono": "78901234",
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def dummy_role(**overrides):
    values = {
        "id_rol": 3,
        "nombre": "CAJERO",
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def dummy_membership(**overrides):
    values = {
        "id_empresa": 2,
        "id_usuario": 10,
        "id_rol": 3,
        "estado": "ACTIVO",
        "es_propietario": False,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def dummy_branch(**overrides):
    values = {
        "id_sucursal": 5,
        "empresa_id": 2,
        "id_ciudad": 1,
        "nombre": "Sucursal Central",
        "direccion": "Av. San Martín 123",
        "telefono": "78901234",
        "hora_apertura": time(8, 30),
        "hora_cierre": time(20, 0),
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def dummy_city(**overrides):
    values = {
        "id_ciudad": 1,
        "nombre": "Santa Cruz",
        "estado": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CompanyResourcesRouteAndSecurityTests(TestCase):
    """Pruebas de permisos SUPERADMIN y exposición HTTP de los endpoints de CU04."""

    def setUp(self):
        self.db = MagicMock()
        test_app = FastAPI()
        test_app.include_router(router)
        test_app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(test_app)
        self.superadmin = AuthenticatedUserData(
            id_usuario=99,
            nombre="Super",
            apellido="Admin",
            correo="superadmin@fashionstore.com",
            rol="SUPERADMIN",
            id_empresa=None,
        )

    def tearDown(self):
        self.client.close()

    def test_superadmin_permissions_required(self):
        """1. Valida que solicitudes sin token respondan 401 y sin rol SUPERADMIN respondan 403."""
        # Sin token -> 401
        res1 = self.client.get("/api/saas/empresas/2/usuarios")
        self.assertEqual(res1.status_code, 401)

        # Con rol ADMINISTRADOR (no SUPERADMIN) -> 403
        normal_admin = self.superadmin.model_copy(update={"rol": "ADMINISTRADOR", "id_empresa": 2})
        with patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user", return_value=normal_admin):
            res2 = self.client.get(
                "/api/saas/empresas/2/usuarios",
                headers={"Authorization": "Bearer token"},
            )
            self.assertEqual(res2.status_code, 403)

    @patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService.get_current_user")
    @patch("app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.router.CompanyResourcesService")
    def test_list_company_users_and_branches_and_resources(self, service_class, authenticate):
        """2. Valida consulta de usuarios, sucursales y consolidado de recursos."""
        authenticate.return_value = self.superadmin
        headers = {"Authorization": "Bearer supertoken"}

        service_instance = service_class.return_value
        service_instance.list_company_users.return_value = []
        service_instance.list_company_branches.return_value = []
        service_instance.get_company_resources.return_value = CompanyResourcesData(
            id_empresa=2,
            empresa_nombre="Moda Oriente SRL",
            empresa_codigo="moda-oriente",
            usuarios=[],
            sucursales=[],
        )

        res_users = self.client.get("/api/saas/empresas/2/usuarios", headers=headers)
        self.assertEqual(res_users.status_code, 200)
        self.assertTrue(res_users.json()["success"])

        res_branches = self.client.get("/api/saas/empresas/2/sucursales", headers=headers)
        self.assertEqual(res_branches.status_code, 200)
        self.assertTrue(res_branches.json()["success"])

        res_consolidated = self.client.get("/api/saas/empresas/2/asociaciones", headers=headers)
        self.assertEqual(res_consolidated.status_code, 200)
        self.assertTrue(res_consolidated.json()["success"])


class CompanyResourcesServiceTests(TestCase):
    """Pruebas funcionales de negocio: asociación, duplicados, validaciones y aislamiento."""

    def setUp(self):
        self.db = MagicMock()
        self.db.info = {}
        self.service = CompanyResourcesService(self.db)
        self.service.repository = MagicMock()

    def test_associate_existing_user_success(self):
        """3. Asocia usuario existente con rol CAJERO y crea perfil de empleado."""
        self.service.repository.get_company.return_value = dummy_company(id_empresa=2)
        self.service.repository.get_user_with_role.return_value = (dummy_user(id_usuario=10), dummy_role(id_rol=3, nombre="CAJERO"))
        self.service.repository.get_role_by_name.return_value = dummy_role(id_rol=3, nombre="CAJERO")
        self.service.repository.get_user_membership.return_value = None
        self.service.repository.save_user_membership.return_value = dummy_membership(id_empresa=2, id_usuario=10, id_rol=3)
        self.service.repository.get_employee.return_value = None

        payload = AssociateUserRequest(
            id_usuario=10,
            rol="CAJERO",
            estado="ACTIVO",
            es_propietario=False,
        )
        res = self.service.associate_user(2, payload)

        self.assertEqual(res.id_empresa, 2)
        self.assertEqual(res.id_usuario, 10)
        self.assertEqual(res.rol, "CAJERO")
        self.service.repository.create_employee.assert_called_once_with(
            user_id=10,
            company_id=2,
            cargo="CAJERO",
        )
        self.db.commit.assert_called_once()

    def test_associate_user_rejects_duplicates_and_conflicts(self):
        """4. Rechaza asociar a un usuario que ya cuenta con membresía activa con el mismo rol."""
        self.service.repository.get_company.return_value = dummy_company()
        self.service.repository.get_user_with_role.return_value = (dummy_user(), dummy_role())
        self.service.repository.get_role_by_name.return_value = dummy_role(id_rol=3)
        self.service.repository.get_user_membership.return_value = dummy_membership(
            id_empresa=2, id_usuario=10, id_rol=3, estado="ACTIVO", es_propietario=False
        )

        payload = AssociateUserRequest(
            id_usuario=10,
            rol="CAJERO",
            estado="ACTIVO",
            es_propietario=False,
        )
        with self.assertRaises(UserAlreadyAssociatedError):
            self.service.associate_user(2, payload)
        self.db.rollback.assert_called_once()

    def test_associate_user_rejects_superadmin_role(self):
        """5. Impide asociar un usuario con rol global SUPERADMIN o asignar dicho rol."""
        self.service.repository.get_company.return_value = dummy_company()
        superadmin_user = dummy_user(id_usuario=99)
        superadmin_role = dummy_role(id_rol=99, nombre="SUPERADMIN")
        self.service.repository.get_user_with_role.return_value = (superadmin_user, superadmin_role)

        payload = AssociateUserRequest(id_usuario=99, rol="CAJERO")
        with self.assertRaises(CannotAssignSuperadminError):
            self.service.associate_user(2, payload)

        # También si se solicita rol SUPERADMIN (rechazado por schema y por servicio)
        with self.assertRaises(ValueError):
            AssociateUserRequest(id_usuario=10, rol="SUPERADMIN")

        self.service.repository.get_user_with_role.return_value = (dummy_user(), dummy_role())
        payload_sa = AssociateUserRequest(id_usuario=10, rol="CAJERO")
        payload_sa.rol = "SUPERADMIN"
        with self.assertRaises(CannotAssignSuperadminError):
            self.service.associate_user(2, payload_sa)

    def test_associate_user_validates_active_company_and_active_user(self):
        """6. Valida que empresa y usuario estén activos y rol configurado."""
        # Empresa inactiva
        self.service.repository.get_company.return_value = dummy_company(estado="SUSPENDIDA")
        with self.assertRaises(CompanyNotActiveError):
            self.service.associate_user(2, AssociateUserRequest(id_usuario=10, rol="CAJERO"))

        # Usuario inactivo
        self.service.repository.get_company.return_value = dummy_company(estado="ACTIVA")
        self.service.repository.get_user_with_role.return_value = (dummy_user(estado=False), dummy_role())
        with self.assertRaises(UserInactiveError):
            self.service.associate_user(2, AssociateUserRequest(id_usuario=10, rol="CAJERO"))

        # Rol no configurado
        self.service.repository.get_user_with_role.return_value = (dummy_user(estado=True), dummy_role())
        self.service.repository.get_role_by_name.return_value = None
        with self.assertRaises(RoleNotConfiguredError):
            self.service.associate_user(2, AssociateUserRequest(id_usuario=10, rol="INVENTADO"))

    def test_create_company_branch_success(self):
        """7. Crea sucursal dentro de la empresa garantizando propiedad exclusiva y asignando empresa_id."""
        self.service.repository.get_company.return_value = dummy_company(id_empresa=2)
        self.service.repository.get_city.return_value = dummy_city(id_ciudad=1, estado=True)
        self.service.repository.create_branch.return_value = dummy_branch(empresa_id=2, id_sucursal=101)

        payload = CreateCompanyBranchRequest(
            id_ciudad=1,
            nombre="Sucursal Norte",
            direccion="Calle Libertad #456",
        )
        res = self.service.create_company_branch(2, payload)

        self.assertEqual(res.id_sucursal, 101)
        self.assertEqual(res.empresa_id, 2)
        self.service.repository.create_branch.assert_called_once()
        self.db.commit.assert_called_once()

    def test_create_branch_validates_city_and_company(self):
        """8. Valida ciudad existente y activa, y empresa activa al crear sucursal."""
        self.service.repository.get_company.return_value = dummy_company(estado="ACTIVA")
        self.service.repository.get_city.return_value = None

        payload = CreateCompanyBranchRequest(id_ciudad=99, nombre="Sucursal Test", direccion="Dir")
        with self.assertRaises(BranchCityNotFoundError):
            self.service.create_company_branch(2, payload)

        # Ciudad inactiva
        self.service.repository.get_city.return_value = dummy_city(estado=False)
        with self.assertRaises(BranchCityInactiveError):
            self.service.create_company_branch(2, payload)

    def test_branch_exclusive_ownership_rejects_cross_company_transfer(self):
        """9. Garantiza propiedad exclusiva: prohíbe asociar sucursal de otra empresa y duplicados."""
        self.service.repository.get_company.return_value = dummy_company(id_empresa=2)

        # Sucursal pertenece a empresa 1 -> No puede asociarse a empresa 2
        branch_emp1 = dummy_branch(id_sucursal=5, empresa_id=1)
        self.service.repository.get_branch.return_value = (branch_emp1, dummy_city())

        with self.assertRaises(BranchBelongsToAnotherCompanyError):
            self.service.associate_existing_branch(2, AssociateExistingBranchRequest(id_sucursal=5))

        # Sucursal ya pertenece activamente a empresa 2 -> Duplicado
        branch_emp2 = dummy_branch(id_sucursal=6, empresa_id=2, estado=True)
        self.service.repository.get_branch.return_value = (branch_emp2, dummy_city())

        with self.assertRaises(BranchAlreadyAssociatedError):
            self.service.associate_existing_branch(2, AssociateExistingBranchRequest(id_sucursal=6))

    def test_multitenant_isolation_and_ownership_limit(self):
        """10. Valida que CU04 rechaza asociar ADMINISTRADOR o asignar propiedad, y filtros multitenant."""
        self.service.repository.get_company.return_value = dummy_company(id_empresa=2)
        self.service.repository.get_user_with_role.return_value = (dummy_user(id_usuario=10), dummy_role(id_rol=1, nombre="ADMINISTRADOR"))
        self.service.repository.get_role_by_name.return_value = dummy_role(id_rol=1, nombre="ADMINISTRADOR")
        self.service.repository.get_user_membership.return_value = None

        # 1. En CU04 no se permite asociar ADMINISTRADOR (corresponde a CU03)
        with self.assertRaises(ValueError):
            AssociateUserRequest(
                id_usuario=10,
                rol="ADMINISTRADOR",
                estado="ACTIVO",
            )

        # 2. En CU04 no se permite asignar la condición de titular / propietario
        with self.assertRaises(ValueError):
            AssociateUserRequest(
                id_usuario=10,
                rol="CAJERO",
                estado="ACTIVO",
                es_propietario=True,
            )

        # 3. Verificación de servicio rechazando asignación administrativa o titularidad
        payload_bypass = AssociateUserRequest(id_usuario=10, rol="CAJERO")
        payload_bypass.rol = "ADMINISTRADOR"
        with self.assertRaises(AdministratorRoleNotAllowedInCU04Error):
            self.service.associate_user(2, payload_bypass)

        payload_bypass.rol = "CAJERO"
        payload_bypass.es_propietario = True
        with self.assertRaises(OwnershipAssignmentNotAllowedInCU04Error):
            self.service.associate_user(2, payload_bypass)

        # Verificación de que list_company_branches filtra por la empresa indicada
        repo_db = MagicMock()
        repo = CompanyResourcesRepository(repo_db)
        repo.list_company_branches(company_id=7)
        statement = repo_db.execute.call_args[0][0]
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("t_sucursal.empresa_id = 7", compiled)
