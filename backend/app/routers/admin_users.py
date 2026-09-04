"""Endpoints protegidos para gestionar usuarios y consultar roles."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.auth import bearer_scheme
from app.schemas.admin_user import (
    AdminRoleListResponse,
    AdminUserCreateRequest,
    AdminUserCreateResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse
from app.services.admin_user_service import (
    AdministratorRoleAssignmentError,
    AdministratorRequiredError,
    AdminUserPersistenceError,
    AdminUserService,
    InternalRoleNotConfiguredError,
    InternalRoleNotAllowedError,
    RoleNotFoundError,
    RoleProfileConflictError,
    SelfDeactivationError,
    SelfRoleChangeError,
    UserNotFoundError,
)
from app.services.auth_service import (
    AuthenticationConfigurationError,
    InactiveAccountError,
    InvalidAccessTokenError,
    EmailAlreadyRegisteredError,
)


router = APIRouter(prefix="/api/admin", tags=["Administración de usuarios"])


def _error_response(
    status_code: int,
    message: str,
    *,
    bearer_challenge: bool = False,
) -> JSONResponse:
    """Mantiene el formato seguro utilizado por los endpoints de auth."""
    headers = {"WWW-Authenticate": "Bearer"} if bearer_challenge else None
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message},
        headers=headers,
    )


def require_administrator(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    db: Session = Depends(get_db),
) -> AuthenticatedUserData | JSONResponse:
    """Valida el Bearer JWT y el rol actual consultado desde la BD."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido o expirado",
            bearer_challenge=True,
        )

    try:
        return AdminUserService(db).authenticate_administrator(
            credentials.credentials
        )
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
    except AdministratorRequiredError:
        return _error_response(
            status.HTTP_403_FORBIDDEN,
            "Se requiere el rol ADMINISTRADOR",
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


AdminDependency = Annotated[
    AuthenticatedUserData | JSONResponse,
    Depends(require_administrator),
]


COMMON_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Token inválido o expirado",
    },
    status.HTTP_403_FORBIDDEN: {
        "model": ErrorResponse,
        "description": "El usuario no es ADMINISTRADOR",
    },
}


@router.post(
    "/users",
    response_model=AdminUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario interno",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "El correo ya está registrado",
        },
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "El rol no está permitido para creación interna",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
            "description": "Datos de creación inválidos",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "No fue posible crear el usuario",
        },
    },
)
def create_user(
    payload: AdminUserCreateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminUserCreateResponse | JSONResponse:
    """Crea únicamente usuarios empleados sin asignar una sucursal."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        user = AdminUserService(db).create_user(payload)
    except EmailAlreadyRegisteredError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El correo ya se encuentra registrado",
        )
    except InternalRoleNotAllowedError:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "Solo se permite crear usuarios CAJERO o ENCARGADO_SUCURSAL",
        )
    except InternalRoleNotConfiguredError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "El rol interno solicitado no está configurado",
        )
    except AdminUserPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible crear el usuario",
        )

    return AdminUserCreateResponse(data=user)


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="Listar usuarios",
    responses=COMMON_ERROR_RESPONSES,
)
def list_users(
    administrator: AdminDependency,
    search: Annotated[
        str | None,
        Query(max_length=150, description="Nombre, apellido o correo"),
    ] = None,
    rol: Annotated[str | None, Query(max_length=50)] = None,
    estado: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AdminUserListResponse | JSONResponse:
    """Lista usuarios con búsqueda, filtros y paginación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    users, pagination = AdminUserService(db).list_users(
        search=search,
        role=rol,
        state=estado,
        page=page,
        page_size=page_size,
    )
    return AdminUserListResponse(data=users, pagination=pagination)


@router.get(
    "/users/{id_usuario}",
    response_model=AdminUserResponse,
    summary="Obtener detalle de usuario",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Usuario no encontrado",
        },
    },
)
def get_user(
    id_usuario: int,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminUserResponse | JSONResponse:
    """Devuelve únicamente los datos públicos del usuario."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        user = AdminUserService(db).get_user(id_usuario)
    except UserNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return AdminUserResponse(data=user)


@router.patch(
    "/users/{id_usuario}/status",
    response_model=AdminUserUpdateResponse,
    summary="Activar o desactivar usuario",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Usuario no encontrado",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Un administrador no puede desactivarse a sí mismo",
        },
    },
)
def update_user_status(
    id_usuario: int,
    payload: UserStatusUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminUserUpdateResponse | JSONResponse:
    """Actualiza el estado con protección contra auto-desactivación."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        user = AdminUserService(db).update_status(
            current_admin_id=administrator.id_usuario,
            user_id=id_usuario,
            payload=payload,
        )
    except UserNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    except SelfDeactivationError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Un administrador no puede desactivar su propia cuenta",
        )
    except AdminUserPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el estado del usuario",
        )
    return AdminUserUpdateResponse(
        message="Estado del usuario actualizado correctamente",
        data=user,
    )


@router.patch(
    "/users/{id_usuario}/role",
    response_model=AdminUserUpdateResponse,
    summary="Cambiar rol de usuario",
    responses={
        **COMMON_ERROR_RESPONSES,
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Usuario o rol no encontrado",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": (
                "Cambio propio, rol ADMINISTRADOR único o perfil asociado "
                "incompatible"
            ),
        },
    },
)
def update_user_role(
    id_usuario: int,
    payload: UserRoleUpdateRequest,
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminUserUpdateResponse | JSONResponse:
    """Asigna un rol existente por nombre y valida su perfil requerido."""
    if isinstance(administrator, JSONResponse):
        return administrator

    try:
        user = AdminUserService(db).update_role(
            current_admin_id=administrator.id_usuario,
            user_id=id_usuario,
            payload=payload,
        )
    except UserNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    except RoleNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Rol no encontrado")
    except AdministratorRoleAssignmentError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "No se puede asignar el rol ADMINISTRADOR; es un rol único",
        )
    except SelfRoleChangeError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Un administrador no puede cambiar su propio rol",
        )
    except RoleProfileConflictError as error:
        return _error_response(status.HTTP_409_CONFLICT, str(error))
    except AdminUserPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible actualizar el rol del usuario",
        )
    return AdminUserUpdateResponse(
        message="Rol del usuario actualizado correctamente",
        data=user,
    )


@router.get(
    "/roles",
    response_model=AdminRoleListResponse,
    summary="Listar roles disponibles",
    responses=COMMON_ERROR_RESPONSES,
)
def list_roles(
    administrator: AdminDependency,
    db: Session = Depends(get_db),
) -> AdminRoleListResponse | JSONResponse:
    """Lista los roles existentes en t_rol sin modificarlos."""
    if isinstance(administrator, JSONResponse):
        return administrator

    roles = AdminUserService(db).list_roles()
    return AdminRoleListResponse(data=roles)
