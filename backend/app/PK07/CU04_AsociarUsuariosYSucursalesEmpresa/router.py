"""Endpoints FastAPI de PK07 / CU04: Asociar usuarios y sucursales a empresa."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.router import SuperadminDependency, _error_response
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.schemas import (
    AssociateExistingBranchRequest,
    AssociateUserRequest,
    CompanyBranchesListResponse,
    CompanyBranchResponse,
    CompanyResourcesResponse,
    CompanyUserResponse,
    CompanyUsersListResponse,
    CreateCompanyBranchRequest,
)
from app.PK07.CU07_ConsultarPlanLimites.service import (
    BranchLimitExceededError,
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
)
from app.PK07.CU04_AsociarUsuariosYSucursalesEmpresa.service import (
    AdministratorRoleNotAllowedInCU04Error,
    BranchAlreadyAssociatedError,
    BranchBelongsToAnotherCompanyError,
    BranchCityInactiveError,
    BranchCityNotFoundError,
    BranchNotFoundError,
    CannotAssignSuperadminError,
    CompanyNotActiveError,
    CompanyNotFoundError,
    CompanyResourcesPersistenceError,
    CompanyResourcesService,
    OwnershipAssignmentNotAllowedInCU04Error,
    RoleNotConfiguredError,
    UserAlreadyAssociatedError,
    UserAlreadyOwnerOfOtherCompanyError,
    UserInactiveError,
    UserNotFoundError,
)
from app.schemas.auth import ErrorResponse


router = APIRouter(prefix="/api/saas", tags=["PK07 - Empresas SaaS"])

COMMON_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


@router.get(
    "/empresas/{id}/usuarios",
    response_model=CompanyUsersListResponse,
    summary="Consultar usuarios asociados a una empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa no encontrada"},
    },
)
def list_company_users(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    current_user: SuperadminDependency,
    role: Annotated[str | None, Query(description="Filtrar por nombre de rol")] = None,
    estado: Annotated[str | None, Query(description="Filtrar por estado de membresía")] = None,
    search: Annotated[str | None, Query(description="Búsqueda por nombre o correo")] = None,
    db: Session = Depends(get_db),
) -> CompanyUsersListResponse | JSONResponse:
    """Retorna los usuarios asociados a la empresa indicada."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = CompanyResourcesService(db)
    try:
        users = service.list_company_users(
            company_id,
            role_name=role,
            state=estado,
            search=search,
        )
        return CompanyUsersListResponse(data=users, total=len(users))
    except (BranchLimitExceededError, NoActiveSubscriptionError, FeatureNotEnabledError) as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La empresa solicitada no existe")
    except CompanyResourcesPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error al consultar usuarios asociados")


@router.get(
    "/empresas/{id}/sucursales",
    response_model=CompanyBranchesListResponse,
    summary="Consultar sucursales asociadas a una empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa no encontrada"},
    },
)
def list_company_branches(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    current_user: SuperadminDependency,
    estado: Annotated[bool | None, Query(description="Filtrar por estado activo/inactivo")] = None,
    search: Annotated[str | None, Query(description="Búsqueda por nombre de sucursal")] = None,
    db: Session = Depends(get_db),
) -> CompanyBranchesListResponse | JSONResponse:
    """Retorna las sucursales pertenecientes exclusivamente a la empresa indicada."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = CompanyResourcesService(db)
    try:
        branches = service.list_company_branches(
            company_id,
            state=estado,
            search=search,
        )
        return CompanyBranchesListResponse(data=branches, total=len(branches))
    except (BranchLimitExceededError, NoActiveSubscriptionError, FeatureNotEnabledError) as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La empresa solicitada no existe")
    except CompanyResourcesPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error al consultar sucursales asociadas")


@router.get(
    "/empresas/{id}/asociaciones",
    response_model=CompanyResourcesResponse,
    summary="Consultar vista consolidada de usuarios y sucursales de la empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa no encontrada"},
    },
)
def get_company_resources(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyResourcesResponse | JSONResponse:
    """Retorna la consolidación de usuarios y sucursales de la empresa."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = CompanyResourcesService(db)
    try:
        resources = service.get_company_resources(company_id)
        return CompanyResourcesResponse(data=resources)
    except (BranchLimitExceededError, NoActiveSubscriptionError, FeatureNotEnabledError) as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La empresa solicitada no existe")
    except CompanyResourcesPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error al consultar recursos de la empresa")


@router.post(
    "/empresas/{id}/usuarios",
    response_model=CompanyUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asociar un usuario existente con rol empresarial a la empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa o usuario no encontrado"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Conflicto de membresía o empresa inactiva"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse, "description": "Rol inválido o datos inconsistentes"},
    },
)
def associate_user_to_company(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    payload: AssociateUserRequest,
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyUserResponse | JSONResponse:
    """Asocia un usuario existente a una empresa con un rol empresarial válido."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = CompanyResourcesService(db)
    try:
        user_data = service.associate_user(company_id, payload)
        return CompanyUserResponse(
            message="Usuario asociado correctamente a la empresa",
            data=user_data,
        )
    except (BranchLimitExceededError, NoActiveSubscriptionError, FeatureNotEnabledError) as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La empresa solicitada no existe")
    except CompanyNotActiveError:
        return _error_response(status.HTTP_409_CONFLICT, "La empresa seleccionada no se encuentra activa")
    except UserNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "El usuario seleccionado no existe")
    except UserInactiveError:
        return _error_response(status.HTTP_409_CONFLICT, "El usuario seleccionado se encuentra inactivo")
    except CannotAssignSuperadminError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "No se permite asociar usuarios con rol SUPERADMIN a nivel empresarial",
        )
    except AdministratorRoleNotAllowedInCU04Error:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "La asignación del rol ADMINISTRADOR corresponde exclusivamente a CU03",
        )
    except OwnershipAssignmentNotAllowedInCU04Error:
        return _error_response(
            status.HTTP_400_BAD_REQUEST,
            "La asignación de Titular / Propietario corresponde exclusivamente a CU03",
        )
    except RoleNotConfiguredError:
        return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "El rol empresarial solicitado no está disponible")
    except UserAlreadyAssociatedError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El usuario ya se encuentra activamente asociado a esta empresa con el rol especificado",
        )
    except UserAlreadyOwnerOfOtherCompanyError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El usuario ya es administrador principal de otra empresa",
        )
    except CompanyResourcesPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo asociar el usuario a la empresa")


@router.post(
    "/empresas/{id}/sucursales",
    response_model=CompanyBranchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva sucursal dentro de la empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa o ciudad no encontrada"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Empresa o ciudad inactiva"},
    },
)
def create_company_branch(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    payload: CreateCompanyBranchRequest,
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyBranchResponse | JSONResponse:
    """Crea una nueva sucursal asociada con propiedad exclusiva a la empresa."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = CompanyResourcesService(db)
    try:
        branch_data = service.create_company_branch(company_id, payload)
        return CompanyBranchResponse(
            message="Sucursal creada y asociada correctamente a la empresa",
            data=branch_data,
        )
    except (BranchLimitExceededError, NoActiveSubscriptionError, FeatureNotEnabledError) as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La empresa solicitada no existe")
    except CompanyNotActiveError:
        return _error_response(status.HTTP_409_CONFLICT, "La empresa seleccionada no se encuentra activa")
    except BranchCityNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La ciudad indicada para la sucursal no existe")
    except BranchCityInactiveError:
        return _error_response(status.HTTP_409_CONFLICT, "La ciudad indicada para la sucursal no se encuentra activa")
    except CompanyResourcesPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo crear la sucursal en la empresa")


@router.post(
    "/empresas/{id}/sucursales/asociar",
    response_model=CompanyBranchResponse,
    summary="Asociar o reactivar una sucursal existente para la empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Empresa o sucursal no encontrada"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Conflicto de pertenencia o empresa inactiva"},
    },
)
def associate_existing_branch(
    company_id: Annotated[int, Path(alias="id", gt=0)],
    payload: AssociateExistingBranchRequest,
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyBranchResponse | JSONResponse:
    """Asocia o reactiva una sucursal respetando la propiedad exclusiva e impidiendo cruces entre empresas."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = CompanyResourcesService(db)
    try:
        branch_data = service.associate_existing_branch(company_id, payload)
        return CompanyBranchResponse(
            message="Sucursal asociada correctamente a la empresa",
            data=branch_data,
        )
    except (BranchLimitExceededError, NoActiveSubscriptionError, FeatureNotEnabledError) as err:
        return _error_response(status.HTTP_403_FORBIDDEN, str(err))
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La empresa solicitada no existe")
    except CompanyNotActiveError:
        return _error_response(status.HTTP_409_CONFLICT, "La empresa seleccionada no se encuentra activa")
    except BranchNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "La sucursal solicitada no existe")
    except BranchAlreadyAssociatedError:
        return _error_response(status.HTTP_409_CONFLICT, "La sucursal ya pertenece activamente a esta empresa")
    except BranchBelongsToAnotherCompanyError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "La sucursal pertenece a otra empresa y no puede transferirse entre empresas",
        )
    except CompanyResourcesPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo asociar la sucursal a la empresa")
