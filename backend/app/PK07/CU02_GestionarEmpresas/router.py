"""Endpoints FastAPI de CU02: gestionar empresas contratantes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.router import SuperadminDependency, _error_response
from app.PK07.CU01_RegistrarEmpresa.service import (
    CompanyCodeAlreadyExistsError,
    CompanyNitAlreadyExistsError,
)
from app.PK07.CU02_GestionarEmpresas.schemas import (
    CompanyDetailResponse,
    CompanyListResponse,
    CompanyState,
    CompanyStateUpdateRequest,
    CompanyUpdateRequest,
    CompanyUpdateResponse,
)
from app.PK07.CU02_GestionarEmpresas.service import (
    CompanyManagementPersistenceError,
    CompanyManagementService,
    CompanyNotFoundError,
    CompanyStateTransitionError,
)
from app.schemas.auth import ErrorResponse


router = APIRouter(prefix="/api/saas/empresas", tags=["PK07 - Empresas SaaS"])

COMMON_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


@router.get("", response_model=CompanyListResponse, responses=COMMON_RESPONSES)
def list_companies(
    superadmin: SuperadminDependency,
    search: Annotated[str | None, Query(max_length=150)] = None,
    estado: CompanyState | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> CompanyListResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        companies, pagination = CompanyManagementService(db).list_companies(
            search=search,
            state=estado,
            page=page,
            page_size=page_size,
        )
    except CompanyManagementPersistenceError:
        return _error_response(500, "No fue posible listar las empresas")
    return CompanyListResponse(data=companies, pagination=pagination)


@router.get(
    "/{id_empresa}",
    response_model=CompanyDetailResponse,
    responses={**COMMON_RESPONSES, status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
def get_company(
    id_empresa: Annotated[int, Path(gt=0)],
    superadmin: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyDetailResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        company = CompanyManagementService(db).get_company(id_empresa)
    except CompanyNotFoundError:
        return _error_response(404, "Empresa no encontrada")
    except CompanyManagementPersistenceError:
        return _error_response(500, "No fue posible consultar la empresa")
    return CompanyDetailResponse(data=company)


@router.patch(
    "/{id_empresa}",
    response_model=CompanyUpdateResponse,
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
def update_company(
    id_empresa: Annotated[int, Path(gt=0)],
    payload: CompanyUpdateRequest,
    superadmin: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyUpdateResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        company = CompanyManagementService(db).update_company(
            company_id=id_empresa,
            payload=payload,
        )
    except CompanyNotFoundError:
        return _error_response(404, "Empresa no encontrada")
    except CompanyCodeAlreadyExistsError:
        return _error_response(409, "El cÃ³digo de empresa ya existe")
    except CompanyNitAlreadyExistsError:
        return _error_response(409, "El NIT ya pertenece a otra empresa")
    except CompanyManagementPersistenceError:
        return _error_response(500, "No fue posible actualizar la empresa")
    return CompanyUpdateResponse(message="Empresa actualizada correctamente", data=company)


@router.patch(
    "/{id_empresa}/estado",
    response_model=CompanyUpdateResponse,
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
def update_company_state(
    id_empresa: Annotated[int, Path(gt=0)],
    payload: CompanyStateUpdateRequest,
    superadmin: SuperadminDependency,
    db: Session = Depends(get_db),
) -> CompanyUpdateResponse | JSONResponse:
    if isinstance(superadmin, JSONResponse):
        return superadmin
    try:
        company = CompanyManagementService(db).update_state(
            company_id=id_empresa,
            payload=payload,
        )
    except CompanyNotFoundError:
        return _error_response(404, "Empresa no encontrada")
    except CompanyStateTransitionError:
        return _error_response(409, "Una empresa cancelada no puede reactivarse")
    except CompanyManagementPersistenceError:
        return _error_response(500, "No fue posible actualizar el estado de la empresa")
    return CompanyUpdateResponse(
        message="Estado de la empresa actualizado correctamente",
        data=company,
    )
