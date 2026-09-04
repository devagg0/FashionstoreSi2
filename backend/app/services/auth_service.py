"""Reglas de negocio para registro, sesión y credenciales."""

from datetime import datetime, timedelta, timezone
import secrets

from jwt.exceptions import InvalidTokenError as JWTInvalidTokenError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    decode_access_token,
    decode_password_reset_token,
    hash_password,
    hash_recovery_code,
    verify_recovery_code,
    verify_password,
)
from app.integrations.brevo import BrevoEmailClient
from app.models.password_recovery import PasswordRecovery
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import (
    AuthenticatedUserData,
    ChangePasswordRequest,
    ClientRegisterRequest,
    LoginRequest,
    LoginResponse,
    PasswordRecoveryEmailRequest,
    PasswordRecoveryResetRequest,
    PasswordRecoveryVerifyRequest,
    PasswordRecoveryVerifyResponse,
    RegisteredClientData,
)


CLIENT_ROLE_NAME = "CLIENTE"
PASSWORD_RECOVERY_TTL = timedelta(minutes=10)
PASSWORD_RECOVERY_MAX_ATTEMPTS = 5


class EmailAlreadyRegisteredError(Exception):
    """El correo solicitado ya pertenece a otro usuario."""


class ClientRoleNotConfiguredError(Exception):
    """El rol requerido para el registro público no está configurado."""


class ClientRegistrationError(Exception):
    """La operación de registro no pudo completarse de forma segura."""


class InvalidCredentialsError(Exception):
    """El correo no existe o la contraseña no coincide."""


class InactiveAccountError(Exception):
    """La cuenta existe, pero actualmente está inactiva."""


class InvalidAccessTokenError(Exception):
    """El access token no puede autenticar a un usuario."""


class AuthenticationConfigurationError(Exception):
    """Los datos requeridos para autenticar están incompletos."""


class IncorrectCurrentPasswordError(Exception):
    """La contraseña actual proporcionada no coincide con el hash almacenado."""


class PasswordReuseError(Exception):
    """La contraseña nueva coincide con la contraseña actual."""


class PasswordChangeError(Exception):
    """La actualización de contraseña no pudo completarse de forma segura."""


class PasswordRecoveryRequestError(Exception):
    """No fue posible preparar o enviar la recuperación."""


class InvalidRecoveryCodeError(Exception):
    """El código no existe, expiró, fue usado o agotó sus intentos."""


class PasswordRecoveryVerificationError(Exception):
    """La verificación no pudo completarse por un error interno."""


class InvalidPasswordResetTokenError(Exception):
    """El reset token no autoriza un restablecimiento vigente."""


class PasswordResetError(Exception):
    """El restablecimiento no pudo completarse de forma segura."""


class AuthService:
    """Coordina el registro, la autenticación y las credenciales."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AuthRepository(db)
        self.email_client = BrevoEmailClient()

    def register_client(self, payload: ClientRegisterRequest) -> RegisteredClientData:
        """Registra un usuario CLIENTE y confirma ambas altas juntas."""
        try:
            if self.repository.get_user_by_email(str(payload.correo)) is not None:
                raise EmailAlreadyRegisteredError

            client_role = self.repository.get_role_by_name(CLIENT_ROLE_NAME)
            if client_role is None:
                raise ClientRoleNotConfiguredError

            password_hash = hash_password(payload.password.get_secret_value())
            user = self.repository.create_user(
                role_id=client_role.id_rol,
                first_name=payload.nombre,
                last_name=payload.apellido,
                email=str(payload.correo),
                phone=payload.telefono,
                password_hash=password_hash,
            )
            self.repository.create_client(user_id=user.id_usuario)
            registered_client = RegisteredClientData(
                id_usuario=user.id_usuario,
                nombre=user.nombre,
                apellido=user.apellido,
                correo=user.correo,
            )
            self.db.commit()
            return registered_client
        except (EmailAlreadyRegisteredError, ClientRoleNotConfiguredError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()

            # También cubre una colisión de correo ocurrida entre la
            # comprobación inicial y el INSERT.
            try:
                email_exists = (
                    self.repository.get_user_by_email(str(payload.correo)) is not None
                )
            except Exception as lookup_error:
                self.db.rollback()
                raise ClientRegistrationError from lookup_error

            self.db.rollback()
            if email_exists:
                raise EmailAlreadyRegisteredError from error

            raise ClientRegistrationError from error
        except Exception as error:
            self.db.rollback()
            raise ClientRegistrationError from error

    def login(self, payload: LoginRequest) -> LoginResponse:
        """Valida credenciales y emite un access token individual."""
        normalized_email = str(payload.correo).strip().lower()
        user = self.repository.get_user_by_email(normalized_email)

        if user is None or not verify_password(
            payload.password.get_secret_value(),
            user.password_hash,
        ):
            raise InvalidCredentialsError

        if not user.estado:
            raise InactiveAccountError

        role = self.repository.get_role_by_id(user.id_rol)
        if role is None:
            raise AuthenticationConfigurationError

        authenticated_user = self._to_authenticated_user(user, role.nombre)
        access_token = create_access_token(
            subject=str(user.id_usuario),
            role=role.nombre,
        )
        return LoginResponse(
            access_token=access_token,
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
            usuario=authenticated_user,
        )

    def get_current_user(self, token: str) -> AuthenticatedUserData:
        """Valida el JWT y recupera el estado y rol actuales desde la BD."""
        user = self._get_user_from_token(token)

        role = self.repository.get_role_by_id(user.id_rol)
        if role is None:
            raise AuthenticationConfigurationError

        return self._to_authenticated_user(user, role.nombre)

    def change_password(self, token: str, payload: ChangePasswordRequest) -> None:
        """Cambia la contraseña del usuario identificado exclusivamente por el JWT."""
        try:
            user = self._get_user_from_token(token)
            current_password = payload.current_password.get_secret_value()
            new_password = payload.new_password.get_secret_value()

            if not verify_password(current_password, user.password_hash):
                raise IncorrectCurrentPasswordError

            if verify_password(new_password, user.password_hash):
                raise PasswordReuseError

            self.repository.update_password_hash(
                user,
                hash_password(new_password),
            )
            self.db.commit()
        except (
            InactiveAccountError,
            IncorrectCurrentPasswordError,
            InvalidAccessTokenError,
            PasswordReuseError,
        ):
            self.db.rollback()
            raise
        except Exception as error:
            self.db.rollback()
            raise PasswordChangeError from error

    def request_password_recovery(
        self,
        payload: PasswordRecoveryEmailRequest,
    ) -> None:
        """Crea y envía un código si el correo corresponde a un usuario activo."""
        try:
            user = self.repository.get_user_by_email(str(payload.correo))
            if user is None or not user.estado:
                return

            code = f"{secrets.randbelow(1_000_000):06d}"
            expires_at = datetime.now(timezone.utc) + PASSWORD_RECOVERY_TTL
            self.repository.invalidate_pending_recoveries(user.id_usuario)
            self.repository.create_password_recovery(
                user_id=user.id_usuario,
                code_hash=hash_recovery_code(code),
                expires_at=expires_at,
            )
            self.email_client.send_password_recovery_code(
                recipient_email=user.correo,
                recipient_name=f"{user.nombre} {user.apellido}".strip(),
                code=code,
            )
            self.db.commit()
        except Exception as error:
            self.db.rollback()
            raise PasswordRecoveryRequestError from error

    def verify_password_recovery(
        self,
        payload: PasswordRecoveryVerifyRequest,
    ) -> PasswordRecoveryVerifyResponse:
        """Valida el código, limita intentos y emite un reset token de un solo uso."""
        try:
            user = self.repository.get_user_by_email(str(payload.correo))
            if user is None or not user.estado:
                raise InvalidRecoveryCodeError

            recovery = self.repository.get_latest_pending_recovery_for_update(
                user.id_usuario
            )
            now = datetime.now(timezone.utc)
            self._validate_pending_recovery(recovery, user.id_usuario, now)

            if not verify_recovery_code(
                payload.codigo.get_secret_value(),
                recovery.codigo_hash,
            ):
                self.repository.register_failed_recovery_attempt(
                    recovery,
                    max_attempts=PASSWORD_RECOVERY_MAX_ATTEMPTS,
                )
                self.db.commit()
                raise InvalidRecoveryCodeError

            reset_expires_at = now + PASSWORD_RECOVERY_TTL
            reset_token = create_password_reset_token(
                subject=str(user.id_usuario),
                recovery_id=recovery.id_recuperacion,
                expires_delta=PASSWORD_RECOVERY_TTL,
            )
            self.repository.prepare_recovery_for_reset(
                recovery,
                invalidated_code_hash=hash_recovery_code(
                    secrets.token_urlsafe(32)
                ),
                expires_at=reset_expires_at,
            )
            self.db.commit()
            return PasswordRecoveryVerifyResponse(reset_token=reset_token)
        except InvalidRecoveryCodeError:
            self.db.rollback()
            raise
        except Exception as error:
            self.db.rollback()
            raise PasswordRecoveryVerificationError from error

    def reset_password(self, payload: PasswordRecoveryResetRequest) -> None:
        """Consume un reset token y cambia la contraseña en un único commit."""
        try:
            token_payload = decode_password_reset_token(
                payload.reset_token.get_secret_value()
            )
            user_id = int(token_payload["sub"])
            recovery_id = int(token_payload["recovery_id"])
            if user_id <= 0 or recovery_id <= 0:
                raise ValueError
        except (JWTInvalidTokenError, KeyError, TypeError, ValueError) as error:
            self.db.rollback()
            raise InvalidPasswordResetTokenError from error

        try:
            user = self.repository.get_user_by_id(user_id)
            recovery = self.repository.get_password_recovery_for_update(
                recovery_id
            )
            self._validate_pending_recovery(
                recovery,
                user_id,
                datetime.now(timezone.utc),
            )
            if user is None or not user.estado:
                raise InvalidPasswordResetTokenError

            self.repository.update_password_hash(
                user,
                hash_password(payload.new_password.get_secret_value()),
            )
            self.repository.mark_recovery_as_used(recovery)
            self.db.commit()
        except (InvalidPasswordResetTokenError, InvalidRecoveryCodeError) as error:
            self.db.rollback()
            raise InvalidPasswordResetTokenError from error
        except Exception as error:
            self.db.rollback()
            raise PasswordResetError from error

    @staticmethod
    def _validate_pending_recovery(
        recovery: PasswordRecovery | None,
        user_id: int,
        now: datetime,
    ) -> None:
        """Comprueba pertenencia, uso, expiración y límite de intentos."""
        if (
            recovery is None
            or recovery.id_usuario != user_id
            or recovery.usado
            or recovery.intentos >= PASSWORD_RECOVERY_MAX_ATTEMPTS
            or recovery.expira_en <= now
        ):
            raise InvalidRecoveryCodeError

    def _get_user_from_token(self, token: str) -> User:
        """Resuelve el usuario activo indicado por el subject de un JWT válido."""
        try:
            payload = decode_access_token(token)
            user_id = int(payload["sub"])
            if user_id <= 0:
                raise ValueError
        except (JWTInvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise InvalidAccessTokenError from error

        user = self.repository.get_user_by_id(user_id)
        if user is None:
            raise InvalidAccessTokenError

        if not user.estado:
            raise InactiveAccountError

        return user

    @staticmethod
    def _to_authenticated_user(user: User, role_name: str) -> AuthenticatedUserData:
        """Expone únicamente los campos seguros requeridos por autenticación."""
        return AuthenticatedUserData(
            id_usuario=user.id_usuario,
            nombre=user.nombre,
            apellido=user.apellido,
            correo=user.correo,
            rol=role_name,
        )
