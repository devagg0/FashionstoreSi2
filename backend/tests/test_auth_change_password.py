"""Pruebas unitarias del cambio de contraseña autenticado."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.core.security import verify_password
from app.routers.auth import router
from app.schemas.auth import ChangePasswordRequest
from app.services.auth_service import (
    AuthService,
    IncorrectCurrentPasswordError,
    PasswordReuseError,
)


class ChangePasswordServiceTests(TestCase):
    """Valida la transacción sin conectarse a una base de datos real."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = AuthService(self.db)
        self.service.repository = MagicMock()
        self.user = SimpleNamespace(
            id_usuario=42,
            estado=True,
            password_hash=(
                "$argon2id$v=19$m=65536,t=3,p=4$"
                "dGVzdHNhbHQxMjM0NTY3OA$"
                "DFbVaBMSHU+aLSPlQvPssAzz1gL2F0eF5JtB08pW62I"
            ),
        )

    @patch("app.services.auth_service.hash_password", return_value="new-argon2-hash")
    @patch("app.services.auth_service.verify_password")
    @patch("app.services.auth_service.decode_access_token", return_value={"sub": "42"})
    def test_changes_password_for_user_from_token_and_commits_once(
        self,
        _decode_access_token: MagicMock,
        verify_password_mock: MagicMock,
        _hash_password: MagicMock,
    ) -> None:
        verify_password_mock.side_effect = [True, False]
        self.service.repository.get_user_by_id.return_value = self.user
        payload = ChangePasswordRequest(
            current_password="Actual@2026",
            new_password="Nueva@2026",
            confirm_password="Nueva@2026",
        )

        self.service.change_password("signed-token", payload)

        self.service.repository.get_user_by_id.assert_called_once_with(42)
        self.service.repository.update_password_hash.assert_called_once_with(
            self.user,
            "new-argon2-hash",
        )
        self.db.commit.assert_called_once_with()
        self.db.rollback.assert_not_called()

    @patch("app.services.auth_service.verify_password", return_value=False)
    @patch("app.services.auth_service.decode_access_token", return_value={"sub": "42"})
    def test_wrong_current_password_rolls_back(
        self,
        _decode_access_token: MagicMock,
        _verify_password: MagicMock,
    ) -> None:
        self.service.repository.get_user_by_id.return_value = self.user
        payload = ChangePasswordRequest(
            current_password="Incorrecta@2026",
            new_password="Nueva@2026",
            confirm_password="Nueva@2026",
        )

        with self.assertRaises(IncorrectCurrentPasswordError):
            self.service.change_password("signed-token", payload)

        self.service.repository.update_password_hash.assert_not_called()
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once_with()

    @patch("app.services.auth_service.verify_password")
    @patch("app.services.auth_service.decode_access_token", return_value={"sub": "42"})
    def test_reusing_current_password_rolls_back(
        self,
        _decode_access_token: MagicMock,
        verify_password_mock: MagicMock,
    ) -> None:
        verify_password_mock.side_effect = [True, True]
        self.service.repository.get_user_by_id.return_value = self.user
        payload = ChangePasswordRequest(
            current_password="Actual@2026",
            new_password="Actual@2026",
            confirm_password="Actual@2026",
        )

        with self.assertRaises(PasswordReuseError):
            self.service.change_password("signed-token", payload)

        self.service.repository.update_password_hash.assert_not_called()
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once_with()


class ChangePasswordSchemaTests(TestCase):
    """Valida el contrato estricto y la política de contraseña."""

    def test_rejects_weak_password(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="Actual@2026",
                new_password="debil",
                confirm_password="debil",
            )

    def test_rejects_mismatched_confirmation(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest(
                current_password="Actual@2026",
                new_password="Nueva@2026",
                confirm_password="Distinta@2026",
            )

    def test_rejects_user_id_in_request(self) -> None:
        with self.assertRaises(ValidationError):
            ChangePasswordRequest.model_validate(
                {
                    "id_usuario": 99,
                    "current_password": "Actual@2026",
                    "new_password": "Nueva@2026",
                    "confirm_password": "Nueva@2026",
                }
            )


class ChangePasswordRouteTests(TestCase):
    """Comprueba que el endpoint quede registrado con el método requerido."""

    def test_put_route_is_registered(self) -> None:
        matching_routes = [
            route
            for route in router.routes
            if route.path == "/api/auth/change-password"
        ]

        self.assertEqual(len(matching_routes), 1)
        self.assertIn("PUT", matching_routes[0].methods)


class PasswordHashTests(TestCase):
    """Documenta que la infraestructura de contraseña utiliza Argon2."""

    def test_argon2_hash_verification(self) -> None:
        from app.core.security import hash_password

        password_hash = hash_password("Nueva@2026")

        self.assertTrue(password_hash.startswith("$argon2"))
        self.assertTrue(verify_password("Nueva@2026", password_hash))
