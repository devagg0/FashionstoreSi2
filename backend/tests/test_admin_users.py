"""Pruebas unitarias de la gestión administrativa de usuarios y roles."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.routers.admin_users import router
from app.schemas.admin_user import (
    AdminUserCreateRequest,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from app.services.admin_user_service import (
    AdministratorRoleAssignmentError,
    AdministratorRequiredError,
    AdminUserPersistenceError,
    AdminUserService,
    InternalRoleNotAllowedError,
    RoleProfileConflictError,
    SelfDeactivationError,
    SelfRoleChangeError,
)
from app.services.auth_service import EmailAlreadyRegisteredError


def _user(user_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(
        id_usuario=user_id,
        id_rol=1,
        nombre="Ana",
        apellido="Pérez",
        correo="ana@example.com",
        estado=True,
        password_hash="never-expose-this-value",
    )


class AdminAuthorizationTests(TestCase):
    """Comprueba que el rol exigido proceda del flujo actual de auth."""

    def setUp(self) -> None:
        self.service = AdminUserService(MagicMock())
        self.service.auth_service = MagicMock()

    def test_accepts_database_administrator(self) -> None:
        current_user = SimpleNamespace(id_usuario=1, rol="ADMINISTRADOR")
        self.service.auth_service.get_current_user.return_value = current_user

        result = self.service.authenticate_administrator("signed-token")

        self.assertIs(result, current_user)
        self.service.auth_service.get_current_user.assert_called_once_with(
            "signed-token"
        )

    def test_rejects_non_administrator(self) -> None:
        self.service.auth_service.get_current_user.return_value = SimpleNamespace(
            id_usuario=2,
            rol="CLIENTE",
        )

        with self.assertRaises(AdministratorRequiredError):
            self.service.authenticate_administrator("signed-token")


class AdminUserRulesTests(TestCase):
    """Valida auto-protección y consistencia de perfiles por rol."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = AdminUserService(self.db)
        self.service.repository = MagicMock()

    def test_administrator_cannot_deactivate_itself(self) -> None:
        with self.assertRaises(SelfDeactivationError):
            self.service.update_status(
                current_admin_id=42,
                user_id=42,
                payload=UserStatusUpdateRequest(estado=False),
            )

        self.service.repository.update_status.assert_not_called()
        self.db.commit.assert_not_called()

    def test_administrator_cannot_change_its_own_role(self) -> None:
        with self.assertRaises(SelfRoleChangeError):
            self.service.update_role(
                current_admin_id=42,
                user_id=42,
                payload=UserRoleUpdateRequest(rol="CLIENTE"),
            )

        self.service.repository.update_role.assert_not_called()
        self.db.commit.assert_not_called()

    def test_client_role_requires_client_profile(self) -> None:
        self.service.repository.get_user_with_role.return_value = (
            _user(),
            "ADMINISTRADOR",
        )
        self.service.repository.get_role_by_name.return_value = SimpleNamespace(
            id_rol=2,
            nombre="CLIENTE",
        )
        self.service.repository.has_client_profile.return_value = False

        with self.assertRaisesRegex(RoleProfileConflictError, "t_cliente"):
            self.service.update_role(
                current_admin_id=1,
                user_id=42,
                payload=UserRoleUpdateRequest(rol="cliente"),
            )

        self.service.repository.update_role.assert_not_called()
        self.db.rollback.assert_called_once_with()

    def test_employee_roles_require_employee_profile(self) -> None:
        self.service.repository.has_employee_profile.return_value = False

        for role_name in ("CAJERO", "ENCARGADO_SUCURSAL"):
            with self.subTest(role=role_name):
                with self.assertRaisesRegex(
                    RoleProfileConflictError,
                    "t_empleado",
                ):
                    self.service._validate_role_profile(42, role_name)

    def test_supplier_role_requires_supplier_association(self) -> None:
        self.service.repository.has_supplier_profile.return_value = False

        with self.assertRaisesRegex(RoleProfileConflictError, "t_proveedor"):
            self.service._validate_role_profile(42, "PROVEEDOR")

    def test_administrator_role_needs_no_associated_profile(self) -> None:
        self.service._validate_role_profile(42, "ADMINISTRADOR")

        self.service.repository.has_client_profile.assert_not_called()
        self.service.repository.has_employee_profile.assert_not_called()
        self.service.repository.has_supplier_profile.assert_not_called()

    def test_role_is_resolved_by_name_and_committed(self) -> None:
        user = _user()
        role = SimpleNamespace(id_rol=7, nombre="CLIENTE")
        self.service.repository.get_user_with_role.return_value = (
            user,
            "ADMINISTRADOR",
        )
        self.service.repository.get_role_by_name.return_value = role
        self.service.repository.has_client_profile.return_value = True

        result = self.service.update_role(
            current_admin_id=1,
            user_id=42,
            payload=UserRoleUpdateRequest(rol="cliente"),
        )

        self.service.repository.get_role_by_name.assert_called_once_with("CLIENTE")
        self.service.repository.update_role.assert_called_once_with(user, role)
        self.db.commit.assert_called_once_with()
        self.assertEqual(result.rol, "CLIENTE")

    def test_administrator_role_cannot_be_assigned_to_another_user(self) -> None:
        self.service.repository.get_user_with_role.return_value = (
            _user(),
            "CAJERO",
        )
        self.service.repository.get_role_by_name.return_value = SimpleNamespace(
            id_rol=1,
            nombre="ADMINISTRADOR",
        )

        with self.assertRaises(AdministratorRoleAssignmentError):
            self.service.update_role(
                current_admin_id=1,
                user_id=42,
                payload=UserRoleUpdateRequest(rol="ADMINISTRADOR"),
            )

        self.service.repository.update_role.assert_not_called()
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once_with()

    def test_public_projection_never_contains_password_hash(self) -> None:
        result = self.service._to_user_data(_user(), "CLIENTE")

        self.assertNotIn("password_hash", result.model_dump())
        self.assertNotIn("password", result.model_dump())


class AdminUserCreationTests(TestCase):
    """Comprueba roles permitidos y atomicidad al crear usuarios internos."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = AdminUserService(self.db)
        self.service.repository = MagicMock()
        self.service.auth_repository = MagicMock()
        self.payload = AdminUserCreateRequest(
            nombre="Andrea",
            apellido="Flores",
            correo="andrea@fashionstore.com",
            telefono="70000000",
            rol="CAJERO",
            password="Fashion@2026",
            confirm_password="Fashion@2026",
        )

    @patch(
        "app.services.admin_user_service.hash_password",
        return_value="argon2-hash",
    )
    def test_employee_role_creates_user_and_employee_in_one_commit(
        self,
        hash_password_mock: MagicMock,
    ) -> None:
        role = SimpleNamespace(id_rol=3, nombre="CAJERO")
        user = _user()
        self.service.repository.get_role_by_name.return_value = role
        self.service.auth_repository.get_user_by_email.return_value = None
        self.service.auth_repository.create_user.return_value = user

        result = self.service.create_user(self.payload)

        hash_password_mock.assert_called_once_with("Fashion@2026")
        self.service.auth_repository.create_user.assert_called_once_with(
            role_id=3,
            first_name="Andrea",
            last_name="Flores",
            email="andrea@fashionstore.com",
            phone="70000000",
            password_hash="argon2-hash",
        )
        self.service.repository.create_employee.assert_called_once_with(
            user_id=user.id_usuario
        )
        self.db.commit.assert_called_once_with()
        self.assertEqual(result.rol, "CAJERO")
        self.assertNotIn("password_hash", result.model_dump())

    @patch(
        "app.services.admin_user_service.hash_password",
        return_value="argon2-hash",
    )
    def test_administrator_creation_is_rejected_by_service_defense(
        self,
        _hash_password_mock: MagicMock,
    ) -> None:
        payload = self.payload.model_copy(update={"rol": "ADMINISTRADOR"})

        with self.assertRaises(InternalRoleNotAllowedError):
            self.service.create_user(payload)

        self.service.auth_repository.create_user.assert_not_called()
        self.service.repository.create_employee.assert_not_called()
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once_with()

    def test_duplicate_email_rolls_back(self) -> None:
        self.service.auth_repository.get_user_by_email.return_value = _user()

        with self.assertRaises(EmailAlreadyRegisteredError):
            self.service.create_user(self.payload)

        self.service.auth_repository.create_user.assert_not_called()
        self.service.repository.create_employee.assert_not_called()
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once_with()

    @patch(
        "app.services.admin_user_service.hash_password",
        return_value="argon2-hash",
    )
    def test_employee_failure_rolls_back_complete_creation(
        self,
        _hash_password_mock: MagicMock,
    ) -> None:
        self.service.repository.get_role_by_name.return_value = SimpleNamespace(
            id_rol=3,
            nombre="CAJERO",
        )
        self.service.auth_repository.get_user_by_email.return_value = None
        self.service.auth_repository.create_user.return_value = _user()
        self.service.repository.create_employee.side_effect = RuntimeError(
            "employee insert failed"
        )

        with self.assertRaises(AdminUserPersistenceError):
            self.service.create_user(self.payload)

        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once_with()

    def test_rejects_public_client_and_supplier_roles(self) -> None:
        raw_payload = {
            "nombre": "Andrea",
            "apellido": "Flores",
            "correo": "andrea@fashionstore.com",
            "telefono": "70000000",
            "password": "Fashion@2026",
            "confirm_password": "Fashion@2026",
        }
        for role_name in ("ADMINISTRADOR", "CLIENTE", "PROVEEDOR"):
            with self.subTest(role=role_name):
                with self.assertRaises(ValidationError) as context:
                    AdminUserCreateRequest.model_validate(
                        {**raw_payload, "rol": role_name}
                    )
                self.assertIn(("rol",), [error["loc"] for error in context.exception.errors()])
                self.assertIn(
                    "Solo se permite crear usuarios",
                    str(context.exception),
                )

    def test_reuses_password_strength_and_confirmation_policy(self) -> None:
        with self.assertRaises(ValidationError):
            AdminUserCreateRequest.model_validate(
                {
                    "nombre": "Andrea",
                    "apellido": "Flores",
                    "correo": "andrea@fashionstore.com",
                    "telefono": "70000000",
                    "rol": "CAJERO",
                    "password": "debil",
                    "confirm_password": "distinta",
                }
            )


class AdminUserRouteTests(TestCase):
    """Documenta los cinco endpoints requeridos por CU03."""

    def test_required_routes_are_registered(self) -> None:
        registered = {
            (method, route.path)
            for route in router.routes
            for method in route.methods
        }
        expected = {
            ("POST", "/api/admin/users"),
            ("GET", "/api/admin/users"),
            ("GET", "/api/admin/users/{id_usuario}"),
            ("PATCH", "/api/admin/users/{id_usuario}/status"),
            ("PATCH", "/api/admin/users/{id_usuario}/role"),
            ("GET", "/api/admin/roles"),
        }

        self.assertTrue(expected.issubset(registered))
