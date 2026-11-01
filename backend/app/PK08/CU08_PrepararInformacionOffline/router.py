"""Endpoints FastAPI para PK08 - CU08: Preparar información para operación offline en FashionStore (Web Angular PWA)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import set_tenant_context
from app.PK07.CU01_RegistrarEmpresa.router import _error_response
from app.PK07.CU07_ConsultarPlanLimites.dependencies import get_current_authenticated_user
from app.PK08.CU08_PrepararInformacionOffline.schemas import (
    OfflinePackageResponse,
    OfflineStatusResponse,
)
from app.PK08.CU08_PrepararInformacionOffline.service import (
    OfflineService,
    OfflineServiceError,
)
from app.schemas.auth import AuthenticatedUserData, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/offline", tags=["PK08 - Operación Offline"])

COMMON_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


@router.get(
    "/status",
    response_model=OfflineStatusResponse,
    summary="Verificar vigencia y cambios del paquete offline",
    responses=COMMON_RESPONSES,
)
def check_offline_package_status(
    current_user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
    version: Annotated[
        str | None,
        Query(description="Versión actual del paquete almacenada localmente en IndexedDB"),
    ] = None,
    since_version: Annotated[
        str | None,
        Query(description="Alias de versión previa (since_version)"),
    ] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    id_sucursal: Annotated[
        int | None,
        Query(gt=0, description="ID de sucursal específica para validar"),
    ] = None,
    empresa_id: Annotated[
        int | None,
        Query(gt=0, description="ID de empresa (requerido para SUPERADMIN)"),
    ] = None,
    db: Session = Depends(get_db),
) -> OfflineStatusResponse | JSONResponse:
    """Verifica si el paquete offline almacenado en la PWA se encuentra vigente y actualizado."""
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineService(db)
    try:
        effective_company_id = empresa_id or current_user.id_empresa
        if effective_company_id:
            set_tenant_context(
                db,
                effective_company_id,
                is_superadmin=(current_user.rol.upper() == "SUPERADMIN"),
            )

        candidate_version = version or since_version or (if_none_match.strip('"') if if_none_match else None)
        return service.check_offline_status(
            current_user,
            requested_company_id=empresa_id,
            requested_branch_id=id_sucursal,
            client_version=candidate_version,
        )
    except OfflineServiceError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado en consulta de estado offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al verificar vigencia del paquete offline.",
        )


@router.get(
    "/package",
    response_model=OfflinePackageResponse,
    summary="Descargar paquete de datos offline para Angular PWA",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_304_NOT_MODIFIED: {"description": "El paquete local se encuentra actualizado"},
    },
)
def download_offline_package(
    response: Response,
    current_user: Annotated[AuthenticatedUserData | JSONResponse, Depends(get_current_authenticated_user)],
    id_sucursal: Annotated[
        int | None,
        Query(gt=0, description="Filtrar opcionalmente por una sucursal autorizada"),
    ] = None,
    since_version: Annotated[
        str | None,
        Query(description="Versión previa en IndexedDB para verificar si requiere recarga"),
    ] = None,
    version: Annotated[
        str | None,
        Query(description="Alias de since_version para verificar si requiere recarga"),
    ] = None,
    empresa_id: Annotated[
        int | None,
        Query(gt=0, description="ID de empresa (requerido para SUPERADMIN)"),
    ] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    db: Session = Depends(get_db),
) -> OfflinePackageResponse | Response | JSONResponse:
    """Descarga el paquete completo de datos offline (catálogo, variantes, existencias y clientes).

    - Filtra estrictamente por la empresa del token JWT y el rol del usuario.
    - Excluye información confidencial, contraseñas y datos de otras empresas.
    - No duplica registros ni modifica existencias ni inventario en la base de datos.
    - Soporta validación condicional 304 Not Modified vía query param o header ETag.
    """
    if isinstance(current_user, JSONResponse):
        return current_user

    service = OfflineService(db)
    try:
        effective_company_id = empresa_id or current_user.id_empresa
        if effective_company_id:
            set_tenant_context(
                db,
                effective_company_id,
                is_superadmin=(current_user.rol.upper() == "SUPERADMIN"),
            )

        # Si el cliente envía version para verificar cambios antes de descargar
        candidate_version = since_version or version or (if_none_match.strip('"') if if_none_match else None)
        if candidate_version:
            status_check = service.check_offline_status(
                current_user,
                requested_company_id=empresa_id,
                requested_branch_id=id_sucursal,
                client_version=candidate_version,
            )
            if status_check.vigente and not status_check.requiere_actualizacion:
                return Response(
                    status_code=status.HTTP_304_NOT_MODIFIED,
                    headers={"ETag": f'"{status_check.version_actual}"'},
                )

        package = service.prepare_offline_package(
            current_user,
            requested_company_id=empresa_id,
            requested_branch_id=id_sucursal,
        )

        response.headers["ETag"] = f'"{package.metadata.version}"'
        response.headers["Cache-Control"] = "private, no-cache"
        return package

    except OfflineServiceError as err:
        return _error_response(err.status_code, err.message)
    except Exception as exc:
        logger.exception("Error inesperado al preparar paquete offline: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error interno al preparar el paquete de datos offline.",
        )

