"""Endpoints HTTP de registro, sesión y credenciales."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    ClientRegisterRequest,
    ClientRegisterResponse,
    CurrentUserResponse,
    ErrorResponse,
    LoginRequest,
    LoginResponse,
    PasswordRecoveryEmailRequest,
    PasswordRecoveryRequestResponse,
    PasswordRecoveryResetRequest,
    PasswordRecoveryResetResponse,
    PasswordRecoveryVerifyRequest,
    PasswordRecoveryVerifyResponse,
)
from app.services.auth_service import (
    AuthenticationConfigurationError,
    AuthService,
    ClientRegistrationError,
    ClientRoleNotConfiguredError,
    EmailAlreadyRegisteredError,
    InactiveAccountError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    IncorrectCurrentPasswordError,
    PasswordChangeError,
    InvalidPasswordResetTokenError,
    InvalidRecoveryCodeError,
    PasswordRecoveryRequestError,
    PasswordRecoveryVerificationError,
    PasswordResetError,
    PasswordReuseError,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Autenticación"])
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Access token JWT obtenido en POST /api/auth/login",
)


def _error_response(
    status_code: int,
    message: str,
    *,
    bearer_challenge: bool = False,
) -> JSONResponse:
    """Construye el formato de error sin exponer detalles internos."""
    headers = {"WWW-Authenticate": "Bearer"} if bearer_challenge else None
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
        headers=headers,
    )


@router.post(
    "/register",
    response_model=ClientRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar cliente",
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El correo ya está registrado",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Error interno o de configuración",
        },
    },
)
def register_client(
    payload: ClientRegisterRequest,
    db: Session = Depends(get_db),
) -> ClientRegisterResponse | JSONResponse:
    """Crea una cuenta pública con el rol CLIENTE."""
    service = AuthService(db)

    try:
        registered_client = service.register_client(payload)
    except EmailAlreadyRegisteredError:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "message": "El correo ya se encuentra registrado",
            },
        )
    except ClientRoleNotConfiguredError:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "Error de configuración del sistema",
            },
        )
    except ClientRegistrationError:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "No fue posible completar el registro",
            },
        )

    return ClientRegisterResponse(data=registered_client)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Correo o contraseña incorrectos",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Cuenta inactiva",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Error interno o de configuración",
        },
    },
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse | JSONResponse:
    """Autentica correo y contraseña sin aplicar reglas de complejidad."""
    service = AuthService(db)

    try:
        return service.login(payload)
    except InvalidCredentialsError:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Correo o contraseña incorrectos",
            bearer_challenge=True,
        )
    except InactiveAccountError:
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "La cuenta se encuentra inactiva",
        )
    except AuthenticationConfigurationError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error de configuración del sistema",
        )
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible iniciar sesión",
        )


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener usuario autenticado",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Token inválido o expirado",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Cuenta inactiva",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Error interno o de configuración",
        },
    },
)
def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    db: Session = Depends(get_db),
) -> CurrentUserResponse | JSONResponse:
    """Valida un Bearer JWT y recupera el usuario actual desde la BD."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )

    service = AuthService(db)
    try:
        user = service.get_current_user(credentials.credentials)
    except InvalidAccessTokenError:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )
    except InactiveAccountError:
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "La cuenta se encuentra inactiva",
        )
    except AuthenticationConfigurationError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error de configuración del sistema",
        )
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible validar la autenticación",
        )

    return CurrentUserResponse(data=user)


@router.put(
    "/change-password",
    response_model=ChangePasswordResponse,
    status_code=status.HTTP_200_OK,
    summary="Cambiar contraseña",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Contraseña actual incorrecta o contraseña nueva repetida",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Token inválido o expirado",
        },
        status.HTTP_403_FORBIDDEN: {
            "model": ErrorResponse,
            "description": "Cuenta inactiva",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible actualizar la contraseña",
        },
    },
)
def change_password(
    payload: ChangePasswordRequest,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    db: Session = Depends(get_db),
) -> ChangePasswordResponse | JSONResponse:
    """Actualiza la contraseña del usuario identificado por el Bearer JWT."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )

    service = AuthService(db)
    try:
        service.change_password(credentials.credentials, payload)
    except InvalidAccessTokenError:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )
    except InactiveAccountError:
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "La cuenta se encuentra inactiva",
        )
    except IncorrectCurrentPasswordError:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "La contraseña actual es incorrecta",
        )
    except PasswordReuseError:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "La nueva contraseña debe ser diferente a la actual",
        )
    except PasswordChangeError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar la contraseña",
        )

    return ChangePasswordResponse()


@router.post(
    "/password-recovery/request",
    response_model=PasswordRecoveryRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Solicitar recuperación de contraseña",
    responses={
        status.HTTP_200_OK: {
            "description": "Respuesta indistinguible exista o no el correo",
        },
    },
)
def request_password_recovery(
    payload: PasswordRecoveryEmailRequest,
    db: Session = Depends(get_db),
) -> PasswordRecoveryRequestResponse:
    """Solicita el correo sin revelar si la cuenta existe."""
    try:
        AuthService(db).request_password_recovery(payload)
    except PasswordRecoveryRequestError:
        logger.exception("No fue posible procesar una solicitud de recuperación")
    except Exception:
        logger.exception("Error inesperado al solicitar una recuperación")

    return PasswordRecoveryRequestResponse()


@router.post(
    "/password-recovery/verify",
    response_model=PasswordRecoveryVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verificar código de recuperación",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Código inválido, usado, expirado o sin intentos",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible verificar el código",
        },
    },
)
def verify_password_recovery(
    payload: PasswordRecoveryVerifyRequest,
    db: Session = Depends(get_db),
) -> PasswordRecoveryVerifyResponse | JSONResponse:
    """Verifica el código y devuelve un reset token temporal."""
    try:
        return AuthService(db).verify_password_recovery(payload)
    except InvalidRecoveryCodeError:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "Código inválido o expirado",
        )
    except PasswordRecoveryVerificationError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible verificar el código",
        )


@router.post(
    "/password-recovery/reset",
    response_model=PasswordRecoveryResetResponse,
    status_code=status.HTTP_200_OK,
    summary="Restablecer contraseña",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Reset token inválido, usado o expirado",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible restablecer la contraseña",
        },
    },
)
def reset_password(
    payload: PasswordRecoveryResetRequest,
    db: Session = Depends(get_db),
) -> PasswordRecoveryResetResponse | JSONResponse:
    """Restablece la contraseña usando únicamente un reset token válido."""
    try:
        AuthService(db).reset_password(payload)
    except InvalidPasswordResetTokenError:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "Token de restablecimiento inválido o expirado",
        )
    except PasswordResetError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible restablecer la contraseña",
        )

    return PasswordRecoveryResetResponse()
