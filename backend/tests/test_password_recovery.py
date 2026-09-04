"""Pruebas unitarias de recuperación de contraseña."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError

from app.core.security import (
    create_password_reset_token,
    decode_access_token,
    decode_password_reset_token,
    hash_recovery_code,
    verify_recovery_code,
)
from app.routers.auth import router
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import (
    PasswordRecoveryEmailRequest,
    PasswordRecoveryResetRequest,
    PasswordRecoveryVerifyRequest,
)
from app.services.auth_service import (
    AuthService,
    InvalidRecoveryCodeError,
    PasswordRecoveryRequestError,
)


class PasswordRecoveryServiceTests(TestCase):
    """Valida orquestación, intentos y transacciones sin usar PostgreSQL ni Brevo."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.service = AuthService(self.db)
        self.service.repository = MagicMock()
        self.service.email_client = MagicMock()
        self.user = SimpleNamespace(
            id_usuario=42,
            nombre="Marcelo",
            apellido="Perez",
            correo="marcelo@example.com",
            estado=True,
        )

    @patch("app.services.auth_service.hash_recovery_code", return_value="stored-hmac")
    @patch("app.services.auth_service.secrets.randbelow", return_value=123456)
    def test_request_invalidates_previous_codes_and_sends_email(
        self,
        _randbelow: MagicMock,
        _hash_recovery_code: MagicMock,
    ) -> None:
        self.service.repository.get_user_by_email.return_value = self.user
        payload = PasswordRecoveryEmailRequest(correo=" MARCELO@example.com ")

        self.service.request_password_recovery(payload)

        self.service.repository.invalidate_pending_recoveries.assert_called_once_with(42)
        create_call = self.service.repository.create_password_recovery.call_args.kwargs
        self.assertEqual(create_call["user_id"], 42)
        self.assertEqual(create_call["code_hash"], "stored-hmac")
        self.service.email_client.send_password_recovery_code.assert_called_once_with(
            recipient_email="marcelo@example.com",
            recipient_name="Marcelo Perez",
            code="123456",
        )
        self.db.commit.assert_called_once_with()
        self.db.rollback.assert_not_called()

    def test_unknown_email_does_not_create_or_send_anything(self) -> None:
        self.service.repository.get_user_by_email.return_value = None

        self.service.request_password_recovery(
            PasswordRecoveryEmailRequest(correo="unknown@example.com")
        )

        self.service.repository.create_password_recovery.assert_not_called()
        self.service.email_client.send_password_recovery_code.assert_not_called()
        self.db.commit.assert_not_called()

    def test_email_failure_rolls_back_without_committing(self) -> None:
        self.service.repository.get_user_by_email.return_value = self.user
        self.service.email_client.send_password_recovery_code.side_effect = RuntimeError

        with self.assertRaises(PasswordRecoveryRequestError):
            self.service.request_password_recovery(
                PasswordRecoveryEmailRequest(correo="marcelo@example.com")
            )

        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once_with()

    @patch("app.services.auth_service.verify_recovery_code", return_value=False)
    def test_wrong_code_registers_an_attempt(
        self,
        _verify_recovery_code: MagicMock,
    ) -> None:
        recovery = self._recovery()
        self.service.repository.get_user_by_email.return_value = self.user
        self.service.repository.get_latest_pending_recovery_for_update.return_value = (
            recovery
        )

        with self.assertRaises(InvalidRecoveryCodeError):
            self.service.verify_password_recovery(
                PasswordRecoveryVerifyRequest(
                    correo="marcelo@example.com",
                    codigo="000000",
                )
            )

        self.service.repository.register_failed_recovery_attempt.assert_called_once_with(
            recovery,
            max_attempts=5,
        )
        self.db.commit.assert_called_once_with()

    @patch("app.services.auth_service.hash_recovery_code", return_value="invalidated-hmac")
    @patch("app.services.auth_service.create_password_reset_token", return_value="reset.jwt")
    @patch("app.services.auth_service.verify_recovery_code", return_value=True)
    def test_correct_code_is_invalidated_and_returns_reset_token(
        self,
        _verify_recovery_code: MagicMock,
        _create_password_reset_token: MagicMock,
        _hash_recovery_code: MagicMock,
    ) -> None:
        recovery = self._recovery()
        self.service.repository.get_user_by_email.return_value = self.user
        self.service.repository.get_latest_pending_recovery_for_update.return_value = (
            recovery
        )

        response = self.service.verify_password_recovery(
            PasswordRecoveryVerifyRequest(
                correo="marcelo@example.com",
                codigo="123456",
            )
        )

        self.assertEqual(response.reset_token, "reset.jwt")
        prepare_call = self.service.repository.prepare_recovery_for_reset.call_args
        self.assertIs(prepare_call.args[0], recovery)
        self.assertEqual(
            prepare_call.kwargs["invalidated_code_hash"],
            "invalidated-hmac",
        )
        self.db.commit.assert_called_once_with()

    @patch("app.services.auth_service.hash_password", return_value="new-argon2-hash")
    @patch(
        "app.services.auth_service.decode_password_reset_token",
        return_value={"sub": "42", "recovery_id": 9},
    )
    def test_reset_updates_password_and_consumes_recovery_in_one_commit(
        self,
        _decode_password_reset_token: MagicMock,
        _hash_password: MagicMock,
    ) -> None:
        recovery = self._recovery()
        self.service.repository.get_user_by_id.return_value = self.user
        self.service.repository.get_password_recovery_for_update.return_value = recovery

        self.service.reset_password(
            PasswordRecoveryResetRequest(
                reset_token="reset.jwt",
                new_password="Nueva@2026",
                confirm_password="Nueva@2026",
            )
        )

        self.service.repository.update_password_hash.assert_called_once_with(
            self.user,
            "new-argon2-hash",
        )
        self.service.repository.mark_recovery_as_used.assert_called_once_with(recovery)
        self.db.commit.assert_called_once_with()
        self.db.rollback.assert_not_called()

    @staticmethod
    def _recovery() -> SimpleNamespace:
        return SimpleNamespace(
            id_recuperacion=9,
            id_usuario=42,
            codigo_hash="stored-hmac",
            intentos=0,
            usado=False,
            expira_en=datetime.now(timezone.utc) + timedelta(minutes=10),
        )


class PasswordRecoverySecurityTests(TestCase):
    """Comprueba HMAC y separación entre reset tokens y access tokens."""

    def test_code_is_not_stored_in_plain_text(self) -> None:
        code_hash = hash_recovery_code("123456")

        self.assertNotEqual(code_hash, "123456")
        self.assertTrue(verify_recovery_code("123456", code_hash))
        self.assertFalse(verify_recovery_code("654321", code_hash))

    def test_reset_token_has_correct_purpose_and_is_not_an_access_token(self) -> None:
        token = create_password_reset_token(subject="42", recovery_id=9)
        payload = decode_password_reset_token(token)

        self.assertEqual(payload["sub"], "42")
        self.assertEqual(payload["purpose"], "password_reset")
        self.assertEqual(payload["recovery_id"], 9)
        self.assertIn("jti", payload)
        with self.assertRaises(InvalidTokenError):
            decode_access_token(token)

    def test_fifth_failed_attempt_invalidates_recovery(self) -> None:
        db = MagicMock()
        repository = AuthRepository(db)
        recovery = SimpleNamespace(intentos=4, usado=False)

        repository.register_failed_recovery_attempt(
            recovery,
            max_attempts=5,
        )

        self.assertEqual(recovery.intentos, 5)
        self.assertTrue(recovery.usado)
        db.flush.assert_called_once_with()


class PasswordRecoveryContractTests(TestCase):
    """Valida contratos y registro de endpoints."""

    def test_rejects_non_numeric_code(self) -> None:
        with self.assertRaises(ValidationError):
            PasswordRecoveryVerifyRequest(
                correo="marcelo@example.com",
                codigo="12AB56",
            )

    def test_rejects_weak_or_mismatched_passwords(self) -> None:
        with self.assertRaises(ValidationError):
            PasswordRecoveryResetRequest(
                reset_token="reset.jwt",
                new_password="debil",
                confirm_password="distinta",
            )

    def test_three_recovery_routes_are_registered(self) -> None:
        paths = {
            route.path
            for route in router.routes
            if route.path.startswith("/api/auth/password-recovery/")
        }

        self.assertEqual(
            paths,
            {
                "/api/auth/password-recovery/request",
                "/api/auth/password-recovery/verify",
                "/api/auth/password-recovery/reset",
            },
        )
