"""Dependencias de autorización y control de límites para PK07 / CU07."""

from typing import Annotated

from fastapi import Depends, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import current_company_id
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.service import (
    BranchLimitExceededError,
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
    SaasPlanLimitsService,
)
from app.routers.auth import bearer_scheme
from app.schemas.auth import AuthenticatedUserData
from app.services.auth_service import (
    AuthenticationConfigurationError,
    AuthService,
    InactiveAccountError,
    InvalidAccessTokenError,
)


def get_current_authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    """Valida el JWT y retorna el usuario autenticado con su rol y empresa."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )
    try:
        return AuthService(db).get_current_user(credentials.credentials)
    except InvalidAccessTokenError:
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )
    except InactiveAccountError:
        return _error_response(status.HTTP_403_FORBIDDEN, "La cuenta se encuentra inactiva")
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


def require_company_feature(feature_code: str):
    """Genera una dependencia FastAPI que exige una suscripción activa con la funcionalidad indicada."""

    def _dependency(
        user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
        db: Session = Depends(get_db),
    ) -> AuthenticatedUserData | JSONResponse:
        if isinstance(user, JSONResponse):
            return user

        # Resolver la empresa del usuario
        company_id = user.id_empresa or current_company_id(db, required=False)
        if company_id is None:
            # Si es SUPERADMIN operando sin contexto de empresa, permitir o denegar según diseño
            if user.rol.upper() == "SUPERADMIN":
                return user
            return _error_response(
                status.HTTP_403_FORBIDDEN,
                "El usuario no tiene una empresa asociada para validar el plan",
            )

        service = SaasPlanLimitsService(db)
        try:
            service.validate_feature_enabled(company_id, feature_code)
        except NoActiveSubscriptionError as err:
            return _error_response(status.HTTP_403_FORBIDDEN, str(err))
        except FeatureNotEnabledError as err:
            return _error_response(status.HTTP_403_FORBIDDEN, str(err))

        return user

    return _dependency


def require_active_saas_subscription(
    user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    """Exige que la empresa del usuario autenticado tenga una suscripción comercial activa vigente."""
    if isinstance(user, JSONResponse):
        return user

    company_id = user.id_empresa or current_company_id(db, required=False)
    if company_id is None:
        if user.rol.upper() == "SUPERADMIN":
            return user
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "El usuario no tiene una empresa asociada para validar la suscripción",
        )

    service = SaasPlanLimitsService(db)
    try:
        service.validate_active_subscription(company_id)
    except NoActiveSubscriptionError as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))

    return user

