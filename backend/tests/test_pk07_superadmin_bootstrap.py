"""Bootstrap manual, idempotente y seguro de SUPERADMIN."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.PK07.superadmin_bootstrap.cli import run
from app.PK07.superadmin_bootstrap.repository import SuperadminBootstrapRepository
from app.PK07.superadmin_bootstrap.service import (
    BootstrapUserInactiveError,
    BootstrapUserNotEligibleError,
    BootstrapUserNotFoundError,
    InvalidBootstrapEmailError,
    SuperadminBootstrapResult,
    SuperadminBootstrapService,
)
from app.services.auth_service import AuthService, InvalidAccessTokenError


def user(**overrides):
    values = {
        "id_usuario": 7,
        "id_rol": 1,
        "nombre": "Admin",
        "apellido": "Inicial",
        "correo": "admin@example.com",
        "password_hash": "unchanged-password-hash",
        "estado": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def role(name: str, role_id: int):
    return SimpleNamespace(id_rol=role_id, nombre=name, estado=True)


class SuperadminRepositoryTests(TestCase):
    def test_assignment_changes_only_global_role(self):
        db = MagicMock()
        repository = SuperadminBootstrapRepository(db)
        target = user()
        membership = SimpleNamespace(id_rol=1, estado="ACTIVO")
        original_password = target.password_hash

        repository.assign_global_role(target, role("SUPERADMIN", 8))

        self.assertEqual(target.id_rol, 8)
        self.assertEqual(target.password_hash, original_password)
        self.assertEqual((membership.id_rol, membership.estado), (1, "ACTIVO"))
        db.flush.assert_called_once_with()
        db.commit.assert_not_called()


class SuperadminServiceTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = SuperadminBootstrapService(self.db)
        self.service.repository = MagicMock()
        self.admin = user()
        self.admin_role = role("ADMINISTRADOR", 1)
        self.superadmin_role = role("SUPERADMIN", 8)
        self.service.repository.get_user_with_global_role.return_value = (
            self.admin,
            self.admin_role,
        )
        self.service.repository.get_active_role.return_value = self.superadmin_role
        self.service.repository.has_active_admin_membership.return_value = True

    def test_dry_run_only_checks_eligibility(self):
        result = self.service.check(" Admin@Example.com ")
        self.assertEqual(result.status, "ELIGIBLE")
        self.service.repository.assign_global_role.assert_not_called()
        self.db.commit.assert_not_called()

    def test_assignment_is_explicit_and_transactional(self):
        result = self.service.assign("admin@example.com")
        self.assertEqual(result.status, "ASSIGNED")
        self.service.repository.assign_global_role.assert_called_once_with(
            self.admin,
            self.superadmin_role,
        )
        self.db.commit.assert_called_once_with()
        self.db.rollback.assert_not_called()

    def test_already_assigned_is_idempotent(self):
        current = role("SUPERADMIN", 8)
        self.service.repository.get_user_with_global_role.return_value = (
            self.admin,
            current,
        )
        result = self.service.assign("admin@example.com")
        self.assertEqual(result.status, "ALREADY_ASSIGNED")
        self.service.repository.assign_global_role.assert_not_called()
        self.service.repository.has_active_admin_membership.assert_not_called()
        self.db.commit.assert_called_once_with()

    def test_missing_inactive_and_common_users_are_rejected(self):
        cases = (
            (None, BootstrapUserNotFoundError),
            ((user(estado=False), self.admin_role), BootstrapUserInactiveError),
            ((self.admin, role("CLIENTE", 2)), BootstrapUserNotEligibleError),
        )
        for row, expected in cases:
            with self.subTest(expected=expected.__name__):
                self.service.repository.get_user_with_global_role.return_value = row
                with self.assertRaises(expected):
                    self.service.assign("admin@example.com")
                self.db.rollback.assert_called()
                self.service.repository.assign_global_role.assert_not_called()
                self.db.reset_mock()
                self.service.repository.assign_global_role.reset_mock()

    def test_administrator_requires_active_admin_membership(self):
        self.service.repository.has_active_admin_membership.return_value = False
        with self.assertRaises(BootstrapUserNotEligibleError):
            self.service.assign("admin@example.com")
        self.service.repository.assign_global_role.assert_not_called()
        self.db.rollback.assert_called_once_with()

    def test_invalid_email_never_queries_or_writes(self):
        with self.assertRaises(InvalidBootstrapEmailError):
            self.service.assign("not-an-email")
        self.service.repository.get_user_with_global_role.assert_not_called()
        self.service.repository.assign_global_role.assert_not_called()
        self.db.commit.assert_not_called()


class SuperadminCliTests(TestCase):
    def test_apply_requires_matching_confirmation_before_database_access(self):
        with patch("app.PK07.superadmin_bootstrap.cli.SessionLocal") as session:
            self.assertEqual(
                run(email="admin@example.com", confirm_email=None, apply=True),
                2,
            )
            self.assertEqual(
                run(
                    email="admin@example.com",
                    confirm_email="other@example.com",
                    apply=True,
                ),
                2,
            )
        session.assert_not_called()

    @patch("app.PK07.superadmin_bootstrap.cli.SuperadminBootstrapService")
    @patch("app.PK07.superadmin_bootstrap.cli.SessionLocal")
    def test_default_is_dry_run_and_apply_is_explicit(self, session_local, service_class):
        context = session_local.return_value
        context.__enter__.return_value = MagicMock()
        service = service_class.return_value
        service_class.normalize_email.side_effect = lambda value: value.strip().lower()
        service.check.return_value = SuperadminBootstrapResult(
            7, "admin@example.com", "ELIGIBLE"
        )
        service.assign.return_value = SuperadminBootstrapResult(
            7, "admin@example.com", "ASSIGNED"
        )

        self.assertEqual(
            run(email="admin@example.com", confirm_email=None, apply=False),
            0,
        )
        service.check.assert_called_once_with("admin@example.com")
        service.assign.assert_not_called()

        self.assertEqual(
            run(
                email="admin@example.com",
                confirm_email="admin@example.com",
                apply=True,
            ),
            0,
        )
        service.assign.assert_called_once_with("admin@example.com")


class SuperadminJwtTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.db.info = {}
        self.service = AuthService(self.db)
        self.service.repository = MagicMock()
        self.account = user(id_rol=8)
        self.service.repository.get_user_by_id.return_value = self.account
        self.service.repository.get_role_by_id.return_value = role("SUPERADMIN", 8)

    @patch("app.services.auth_service.decode_access_token")
    def test_pre_promotion_administrator_token_is_rejected(self, decode):
        decode.return_value = {
            "sub": "7",
            "role": "ADMINISTRADOR",
            "empresa_id": 1,
        }
        with self.assertRaises(InvalidAccessTokenError):
            self.service.get_current_user("old-signed-token")
        self.assertNotIn("effective_role", self.db.info)

    @patch("app.services.auth_service.decode_access_token")
    def test_new_superadmin_token_is_global_and_authorized_for_cu01(self, decode):
        decode.return_value = {
            "sub": "7",
            "role": "SUPERADMIN",
            "empresa_id": None,
        }
        authenticated = self.service.get_current_user("new-signed-token")
        self.assertEqual(authenticated.rol, "SUPERADMIN")
        self.assertIsNone(authenticated.id_empresa)
        self.assertTrue(self.db.info["is_superadmin"])
        self.assertEqual(self.db.info["effective_role"], "SUPERADMIN")
