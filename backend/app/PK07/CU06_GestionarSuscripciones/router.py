"""Endpoints FastAPI para PK07 / CU06: Gestionar suscripciones empresariales."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU06_GestionarSuscripciones.schemas import (
    CheckoutSessionResponse,
    CommercialPlansListResponse,
    CreateCheckoutRequest,
    CurrentSubscriptionResponse,
    SubscriptionAdminListResponse,
    SubscriptionDetailData,
    SubscriptionHistoryResponse,
    UpdateSubscriptionStatusRequest,
    VerifyPaymentResponse,
)
from app.PK07.CU06_GestionarSuscripciones.service import (
    CompanyNotFoundError,
    InvalidPlanChangeError,
    InvalidSubscriptionOperationError,
    PaymentNotCompletedError,
    PlanNotFoundError,
    SaasSubscriptionService,
    StripeValidationError,
    SubscriptionAlreadyActiveError,
    SubscriptionNotFoundError,
    SubscriptionPersistenceError,
    SubscriptionStateTransitionError,
    TenantMismatchError,
)
from app.routers.auth import bearer_scheme
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.services.auth_service import (
    AuthenticationConfigurationError,
    AuthService,
    InactiveAccountError,
    InvalidAccessTokenError,
)

router = APIRouter(prefix="/api/saas/suscripciones", tags=["PK07 - Suscripciones SaaS"])

COMMON_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


def require_admin_or_superadmin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    """Verifica JWT y asegura rol ADMINISTRADOR o SUPERADMIN."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )
    try:
        user = AuthService(db).get_current_user(credentials.credentials)
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

    role_upper = user.rol.upper()
    if role_upper not in ("SUPERADMIN", "ADMINISTRADOR"):
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "Se requiere rol ADMINISTRADOR o SUPERADMIN para gestionar suscripciones",
        )

    if role_upper == "ADMINISTRADOR" and not user.id_empresa:
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "El administrador no tiene una empresa asociada",
        )

    return user


def require_superadmin_only(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    """Verifica JWT y restringe exclusivamente a SUPERADMIN."""
    auth_result = require_admin_or_superadmin(credentials, db)
    if isinstance(auth_result, JSONResponse):
        return auth_result
    if auth_result.rol.upper() != "SUPERADMIN":
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "Acceso exclusivo para SUPERADMIN",
        )
    return auth_result


AdminOrSuperadminDependency = Annotated[AuthenticatedUserData, Depends(require_admin_or_superadmin)]
SuperadminOnlyDependency = Annotated[AuthenticatedUserData, Depends(require_superadmin_only)]


@router.get(
    "/planes",
    response_model=CommercialPlansListResponse,
    summary="Listar planes comerciales vigentes para suscripción",
    responses=COMMON_RESPONSES,
)
def list_commercial_plans(
    current_user: AdminOrSuperadminDependency,
    db: Session = Depends(get_db),
) -> CommercialPlansListResponse | JSONResponse:
    """Consulta los planes comerciales BÁSICO y PROFESIONAL disponibles para contratación."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasSubscriptionService(db)
    plans = service.list_commercial_plans()
    return CommercialPlansListResponse(data=plans, total=len(plans))


@router.get(
    "/actual",
    response_model=CurrentSubscriptionResponse,
    summary="Consultar suscripción vigente de la empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa no encontrada"},
    },
)
def get_current_subscription(
    current_user: AdminOrSuperadminDependency,
    empresa_id: Annotated[int | None, Query(gt=0, description="Filtrar por empresa (solo SUPERADMIN)")] = None,
    db: Session = Depends(get_db),
) -> CurrentSubscriptionResponse | JSONResponse:
    """Retorna la suscripción activa de la empresa con días restantes y cambios programados."""
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company_id = _resolve_company_id(current_user, empresa_id)
    if isinstance(target_company_id, JSONResponse):
        return target_company_id

    service = SaasSubscriptionService(db)
    try:
        return service.get_current_subscription(target_company_id)
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))


@router.get(
    "/historial",
    response_model=SubscriptionHistoryResponse,
    summary="Consultar historial de suscripciones de la empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa no encontrada"},
    },
)
def get_subscription_history(
    current_user: AdminOrSuperadminDependency,
    empresa_id: Annotated[int | None, Query(gt=0, description="Filtrar por empresa (solo SUPERADMIN)")] = None,
    db: Session = Depends(get_db),
) -> SubscriptionHistoryResponse | JSONResponse:
    """Retorna el historial cronológico de todas las suscripciones contratadas por la empresa."""
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company_id = _resolve_company_id(current_user, empresa_id)
    if isinstance(target_company_id, JSONResponse):
        return target_company_id

    service = SaasSubscriptionService(db)
    try:
        history = service.get_subscription_history(target_company_id)
        return SubscriptionHistoryResponse(data=history, total=len(history))
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))


@router.post(
    "/checkout/tarjeta",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear sesión Stripe Checkout para pago con tarjeta",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
def create_card_checkout(
    payload: CreateCheckoutRequest,
    current_user: AdminOrSuperadminDependency,
    db: Session = Depends(get_db),
) -> CheckoutSessionResponse | JSONResponse:
    """Inicia sesión Stripe Checkout de pago único TEST con tarjeta de crédito/débito."""
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company_id = _resolve_company_id(current_user, payload.empresa_id)
    if isinstance(target_company_id, JSONResponse):
        return target_company_id

    service = SaasSubscriptionService(db)
    try:
        return service.create_checkout_session(
            company_id=target_company_id,
            payload=payload,
            payment_method="TARJETA",
        )
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except PlanNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except SubscriptionAlreadyActiveError as err:
        return _error_response(status.HTTP_409_CONFLICT, str(err))
    except InvalidPlanChangeError as err:
        return _error_response(status.HTTP_400_BAD_REQUEST, str(err))
    except SubscriptionNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except InvalidPlanChangeError as err:
        return _error_response(status.HTTP_400_BAD_REQUEST, str(err))
    except Exception as err:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error al crear Checkout: {str(err)}")


@router.post(
    "/checkout/qr",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear sesión Stripe Checkout para pago asistido por QR",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
def create_qr_checkout(
    payload: CreateCheckoutRequest,
    current_user: AdminOrSuperadminDependency,
    db: Session = Depends(get_db),
) -> CheckoutSessionResponse | JSONResponse:
    """
    Inicia sesión Stripe Checkout configurada para escaneo QR.
    El QR abre la sesión oficial de Stripe Checkout; no representa una transferencia bancaria paralela.
    """
    if isinstance(current_user, JSONResponse):
        return current_user

    target_company_id = _resolve_company_id(current_user, payload.empresa_id)
    if isinstance(target_company_id, JSONResponse):
        return target_company_id

    service = SaasSubscriptionService(db)
    try:
        return service.create_checkout_session(
            company_id=target_company_id,
            payload=payload,
            payment_method="QR",
        )
    except CompanyNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except PlanNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except SubscriptionAlreadyActiveError as err:
        return _error_response(status.HTTP_409_CONFLICT, str(err))
    except InvalidPlanChangeError as err:
        return _error_response(status.HTTP_400_BAD_REQUEST, str(err))
    except SubscriptionNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except InvalidPlanChangeError as err:
        return _error_response(status.HTTP_400_BAD_REQUEST, str(err))
    except Exception as err:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error al crear Checkout QR: {str(err)}")


@router.post(
    "/verificar-pago/{session_id}",
    response_model=VerifyPaymentResponse,
    summary="Verificar y conciliar pago Stripe Checkout",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
def verify_payment(
    session_id: Annotated[str, Path(description="Identificador de sesión Stripe Checkout (cs_test_...)")],
    current_user: AdminOrSuperadminDependency,
    db: Session = Depends(get_db),
) -> VerifyPaymentResponse | JSONResponse:
    """
    Concilia el pago consultando directamente a Stripe desde el backend.
    Verifica livemode=false, payment_status='paid', importes y pertenencia tenant.
    Nunca activa por redirección del frontend.
    """
    if isinstance(current_user, JSONResponse):
        return current_user

    is_superadmin = current_user.rol.upper() == "SUPERADMIN"
    user_company_id = current_user.id_empresa

    service = SaasSubscriptionService(db)
    try:
        return service.verify_and_sync_payment(
            session_id=session_id,
            authenticated_company_id=user_company_id,
            is_superadmin=is_superadmin,
        )
    except TenantMismatchError as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))
    except (PaymentNotCompletedError, StripeValidationError) as err:
        return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err))
    except PlanNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except SubscriptionAlreadyActiveError as err:
        return _error_response(status.HTTP_409_CONFLICT, str(err))
    except InvalidPlanChangeError as err:
        return _error_response(status.HTTP_400_BAD_REQUEST, str(err))
    except SubscriptionNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except SubscriptionPersistenceError as err:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(err))
    except Exception as err:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"No fue posible conciliar el pago con Stripe: {str(err)}",
        )


@router.get(
    "",
    response_model=SubscriptionAdminListResponse,
    summary="Listado administrativo de suscripciones (SUPERADMIN)",
    responses=COMMON_RESPONSES,
)
def admin_list_subscriptions(
    current_user: SuperadminOnlyDependency,
    empresa_id: Annotated[int | None, Query(gt=0, description="Filtrar por empresa")] = None,
    estado: Annotated[str | None, Query(description="Filtrar por estado")] = None,
    plan_id: Annotated[int | None, Query(gt=0, description="Filtrar por plan")] = None,
    db: Session = Depends(get_db),
) -> SubscriptionAdminListResponse | JSONResponse:
    """Listado multiempresa exclusivo para SUPERADMIN."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasSubscriptionService(db)
    subs = service.admin_list_all_subscriptions(
        company_id=empresa_id,
        status=estado,
        plan_id=plan_id,
    )
    return SubscriptionAdminListResponse(data=subs, total=len(subs))


@router.patch(
    "/{id}/estado",
    response_model=SubscriptionDetailData,
    summary="Actualizar administrativamente el estado de una suscripción (SUPERADMIN)",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
def admin_update_status(
    id: Annotated[int, Path(gt=0, description="Identificador único de la suscripción")],
    payload: UpdateSubscriptionStatusRequest,
    current_user: SuperadminOnlyDependency,
    db: Session = Depends(get_db),
) -> SubscriptionDetailData | JSONResponse:
    """Permite a SUPERADMIN suspender, reactivar o cancelar una suscripción."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasSubscriptionService(db)
    try:
        return service.admin_update_subscription_status(
            subscription_id=id,
            new_status=payload.nuevo_estado,
            reason=payload.motivo,
        )
    except SubscriptionNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except SubscriptionStateTransitionError as err:
        return _error_response(status.HTTP_409_CONFLICT, str(err))
    except Exception as err:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error al actualizar estado: {str(err)}")


def _resolve_company_id(user: AuthenticatedUserData, query_empresa_id: int | None) -> int | JSONResponse:
    """Resuelve la empresa destino garantizando aislamiento para ADMINISTRADOR y flexibilidad para SUPERADMIN."""
    if user.rol.upper() == "SUPERADMIN":
        if query_empresa_id is not None:
            return query_empresa_id
        if user.id_empresa is not None:
            return user.id_empresa
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "SUPERADMIN debe especificar 'empresa_id' como parámetro de consulta",
        )

    # Rol ADMINISTRADOR: aislamiento forzoso al ID empresarial del token
    if query_empresa_id is not None and query_empresa_id != user.id_empresa:
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "No tiene autorización para acceder a recursos de otra empresa",
        )
    return user.id_empresa

