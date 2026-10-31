"""Endpoints FastAPI de CU03: asignar y consultar administrador de empresa."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.router import SuperadminDependency, _error_response
from app.PK07.CU03_AsignarAdministradorEmpresa.schemas import (
    AssignCompanyAdminRequest,
    AssignCompanyAdminResponse,
    AvailableUsersResponse,
    CompanyAdminResponse,
    CreateAndAssignCompanyAdminRequest,
)
from app.PK07.CU03_AsignarAdministradorEmpresa.service import (
    AdminAssignmentNotFoundError,
    AdminRoleNotConfiguredError,
    CannotAssignSuperadminError,
    CompanyAdminPersistenceError,
    CompanyAdminService,
    CompanyNotActiveError,
    CompanyNotFoundError,
    EmailAlreadyExistsError,
    UserAlreadyAssignedError,
    UserAlreadyAssignedToOtherCompanyError,
    UserInactiveError,
    UserNotEligibleRoleError,
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
    "/empresas/{id}/administrador",
    response_model=CompanyAdminResponse,
    summary="Consultar administrador asignado a una empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
def get_company_admin(
    id: Annotated[int, Path(gt=0, description="Identificador único de la empresa")],
    superadmin: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyAdminResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        admin_data = CompanyAdminService(db).get_assigned_admin(id)
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Empresa no encontrada")
    except AdminAssignmentNotFoundError:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "La empresa no tiene un administrador asignado",
        )
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible consultar el administrador de la empresa",
        )
    return CompanyAdminResponse(data=admin_data)


@router.get(
    "/usuarios-disponibles",
    response_model=AvailableUsersResponse,
    summary="Buscar usuarios disponibles para asignación",
    responses=COMMON_RESPONSES,
)
def list_available_users(
    superadmin: SuperadminDependency,
    search: Annotated[str | None, Query(max_length=150)] = None,
    empresa_id: Annotated[
        int | None,
        Query(gt=0, description="Filtrar excluyendo titulares asignados a otra empresa"),
    ] = None,
    id_empresa: Annotated[int | None, Query(gt=0, include_in_schema=False)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> AvailableUsersResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        effective_company_id = empresa_id or id_empresa
        users, pagination = CompanyAdminService(db).search_available_users(
            search=search,
            company_id=effective_company_id,
            page=page,
            page_size=page_size,
        )
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible consultar los usuarios disponibles",
        )
    return AvailableUsersResponse(data=users, pagination=pagination)


@router.post(
    "/empresas/{id}/administrador",
    response_model=AssignCompanyAdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar administrador a una empresa (existente o nuevo)",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
def assign_company_admin(
    id: Annotated[int, Path(gt=0, description="Identificador único de la empresa")],
    payload: AssignCompanyAdminRequest | CreateAndAssignCompanyAdminRequest,
    superadmin: SuperadminDependency,
    db: Session = Depends(get_db),
) -> AssignCompanyAdminResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        service = CompanyAdminService(db)
        if isinstance(payload, CreateAndAssignCompanyAdminRequest):
            admin_data = service.create_and_assign_admin(id, payload)
        else:
            admin_data = service.assign_admin(id, payload)
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Empresa no encontrada")
    except UserNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    except CompanyNotActiveError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "La empresa se encuentra inactiva, suspendida o cancelada",
        )
    except UserInactiveError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El usuario seleccionado se encuentra inactivo",
        )
    except CannotAssignSuperadminError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "No se permite asignar a un usuario SUPERADMIN como administrador de empresa",
        )
    except UserNotEligibleRoleError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "Solo se pueden asignar usuarios con rol ADMINISTRADOR",
        )
    except UserAlreadyAssignedToOtherCompanyError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El usuario ya es administrador principal de otra empresa. Cada administrador solo puede estar a cargo de una única empresa",
        )
    except EmailAlreadyExistsError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El correo electrónico ya se encuentra registrado",
        )
    except UserAlreadyAssignedError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El usuario ya se encuentra asignado como administrador de la empresa",
        )
    except AdminRoleNotConfiguredError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "El rol ADMINISTRADOR no se encuentra configurado en el sistema",
        )
    except CompanyAdminPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error de persistencia al registrar la asignación del administrador",
        )
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible asignar el administrador a la empresa",
        )
    return AssignCompanyAdminResponse(data=admin_data)


@router.post(
    "/empresas/{id}/administrador/nuevo",
    response_model=AssignCompanyAdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear y asociar directamente un nuevo administrador a la empresa",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)
@router.post(
    "/empresas/{id}/administrador/crear",
    response_model=AssignCompanyAdminResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_and_assign_company_admin(
    id: Annotated[int, Path(gt=0, description="Identificador único de la empresa")],
    payload: CreateAndAssignCompanyAdminRequest,
    superadmin: SuperadminDependency,
    db: Session = Depends(get_db),
) -> AssignCompanyAdminResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        admin_data = CompanyAdminService(db).create_and_assign_admin(id, payload)
    except CompanyNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "Empresa no encontrada")
    except CompanyNotActiveError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "La empresa se encuentra inactiva, suspendida o cancelada",
        )
    except EmailAlreadyExistsError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El correo electrónico ya se encuentra registrado",
        )
    except UserAlreadyAssignedToOtherCompanyError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El usuario ya es administrador principal de otra empresa. Cada administrador solo puede estar a cargo de una única empresa",
        )
    except UserAlreadyAssignedError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "El usuario ya se encuentra asignado como administrador de la empresa",
        )
    except AdminRoleNotConfiguredError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "El rol ADMINISTRADOR no se encuentra configurado en el sistema",
        )
    except CompanyAdminPersistenceError:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error de persistencia al registrar la asignación del administrador",
        )
    except Exception:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible registrar y asignar el administrador a la empresa",
        )
    return AssignCompanyAdminResponse(data=admin_data)
