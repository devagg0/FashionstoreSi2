"""Endpoint FastAPI de CU01: registrar empresa contratante."""

from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.schemas import CompanyCreateRequest, CompanyCreateResponse
from app.PK07.CU01_RegistrarEmpresa.service import (
    CompanyCodeAlreadyExistsError,
    CompanyNitAlreadyExistsError,
    CompanyRegistrationPersistenceError,
    CompanyRegistrationService,
)
from app.routers.auth import bearer_scheme
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.services.auth_service import (
    AuthenticationConfigurationError,
    AuthService,
    InactiveAccountError,
    InvalidAccessTokenError,
)


router = APIRouter(prefix="/api/saas/empresas", tags=["PK07 - Empresas SaaS"])


def _error_response(
    status_code: int,
    message: str,
    *,
    bearer_challenge: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
        headers={"WWW-Authenticate": "Bearer"} if bearer_challenge else None,
    )


def require_superadmin(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token invÃ¡lido o expirado",
            bearer_challenge=True,
        )
    try:
        user = AuthService(db).get_current_user(credentials.credentials)
    except InvalidAccessTokenError:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token invÃ¡lido o expirado",
            bearer_challenge=True,
        )
    except InactiveAccountError:
        return _error_response(status.HTTP_403_FORBIDDEN, "La cuenta se encuentra inactiva")
    except AuthenticationConfigurationError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error de configuraciÃ³n del sistema",
        )
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible validar la autenticaciÃ³n",
        )

    if user.rol.upper() != "SUPERADMIN":
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "Se requiere el rol SUPERADMIN",
        )
    return user


SuperadminDependency = Annotated[
    AuthenticatedUserData | JSONResponse,
    Depends(require_superadmin),
]


@router.post(
    "",
    response_model=CompanyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar empresa contratante",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
def register_company(
    payload: CompanyCreateRequest,
    superadmin: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyCreateResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        company = CompanyRegistrationService(db).register(payload)
    except CompanyCodeAlreadyExistsError:
        return _error_response(status.HTTP_409_CONFLICT, "El cÃ³digo de empresa ya existe")
    except CompanyNitAlreadyExistsError:
        return _error_response(status.HTTP_409_CONFLICT, "El NIT ya pertenece a otra empresa")
    except CompanyRegistrationPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible registrar la empresa",
        )
    return CompanyCreateResponse(data=company)
