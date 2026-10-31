"""Endpoints FastAPI para PK07 / CU05: Gestionar planes SaaS."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.PK07.CU01_RegistrarEmpresa.router import SuperadminDependency, _error_response
from app.PK07.CU05_GestionarPlanesSaaS.schemas import (
    ConfigurePlanFeaturesRequest,
    CreateSaasPlanRequest,
    MessageResponse,
    SaasFeaturesListResponse,
    SaasPlanDetailResponse,
    SaasPlanListResponse,
    UpdateSaasPlanRequest,
    UpdateSaasPlanStatusRequest,
)
from app.PK07.CU05_GestionarPlanesSaaS.service import (
    FeatureNotFoundError,
    InvalidPlanLimitError,
    PlanActiveConditionsProtectedError,
    PlanCodeAlreadyExistsError,
    PlanHasActiveSubscriptionsError,
    PlanNotFoundError,
    PlanPersistenceError,
    SaasPlanService,
)
from app.schemas.auth import ErrorResponse

router = APIRouter(prefix="/api/saas", tags=["PK07 - Planes SaaS"])

COMMON_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


@router.get(
    "/planes",
    response_model=SaasPlanListResponse,
    summary="Listar planes SaaS",
    responses=COMMON_RESPONSES,
)
def list_plans(
    current_user: SuperadminDependency,
    search: Annotated[str | None, Query(description="Búsqueda por código, nombre o descripción")] = None,
    estado: Annotated[bool | None, Query(description="Filtrar por estado activo/inactivo")] = None,
    db: Session = Depends(get_db),
) -> SaasPlanListResponse | JSONResponse:
    """Retorna todos los planes SaaS configurados con sus funcionalidades y límites."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    service.ensure_default_catalog()
    plans = service.list_plans(search=search, state=estado)
    return SaasPlanListResponse(data=plans, total=len(plans))


@router.get(
    "/planes/{id}",
    response_model=SaasPlanDetailResponse,
    summary="Obtener detalle de un plan SaaS",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Plan no encontrado"},
    },
)
def get_plan(
    id: Annotated[int, Path(gt=0, description="Identificador único del plan SaaS")],
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> SaasPlanDetailResponse | JSONResponse:
    """Consulta el detalle de un plan SaaS con sus funcionalidades asignadas y suscriptores activos."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    try:
        plan = service.get_plan(id)
        return SaasPlanDetailResponse(message="Plan SaaS obtenido correctamente", data=plan)
    except PlanNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "El plan SaaS solicitado no existe")


@router.post(
    "/planes",
    response_model=SaasPlanDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nuevo plan SaaS",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Código de plan duplicado"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse, "description": "Datos o límites inválidos"},
    },
)
def create_plan(
    payload: CreateSaasPlanRequest,
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> SaasPlanDetailResponse | JSONResponse:
    """Crea un nuevo plan SaaS asegurando código único y configurando funcionalidades opcionales."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    try:
        plan = service.create_plan(payload)
        return SaasPlanDetailResponse(message="Plan SaaS creado correctamente", data=plan)
    except PlanCodeAlreadyExistsError:
        return _error_response(status.HTTP_409_CONFLICT, f"Ya existe un plan SaaS con el código '{payload.codigo}'")
    except FeatureNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except InvalidPlanLimitError as err:
        return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err))
    except PlanPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo registrar el plan SaaS")


@router.put(
    "/planes/{id}",
    response_model=SaasPlanDetailResponse,
    summary="Actualizar un plan SaaS",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Plan no encontrado"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Protección de suscripciones activas"},
    },
)
def update_plan(
    id: Annotated[int, Path(gt=0, description="Identificador único del plan")],
    payload: UpdateSaasPlanRequest,
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> SaasPlanDetailResponse | JSONResponse:
    """Modifica datos de un plan SaaS protegiendo condiciones comerciales si tiene suscripciones vigentes."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    try:
        plan = service.update_plan(id, payload)
        return SaasPlanDetailResponse(message="Plan SaaS actualizado correctamente", data=plan)
    except PlanNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "El plan SaaS solicitado no existe")
    except PlanActiveConditionsProtectedError as err:
        return _error_response(status.HTTP_409_CONFLICT, str(err))
    except PlanPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo actualizar el plan SaaS")


@router.patch(
    "/planes/{id}/estado",
    response_model=SaasPlanDetailResponse,
    summary="Activar o desactivar un plan SaaS",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Plan no encontrado"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "Conflicto por suscripciones activas"},
    },
)
def update_plan_status(
    id: Annotated[int, Path(gt=0, description="Identificador único del plan")],
    payload: UpdateSaasPlanStatusRequest,
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> SaasPlanDetailResponse | JSONResponse:
    """Activa o desactiva un plan, impidiendo la desactivación si tiene suscripciones activas vigentes."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    try:
        plan = service.update_plan_status(id, payload)
        return SaasPlanDetailResponse(message="Estado del plan SaaS actualizado correctamente", data=plan)
    except PlanNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "El plan SaaS solicitado no existe")
    except PlanHasActiveSubscriptionsError as err:
        return _error_response(status.HTTP_409_CONFLICT, str(err))
    except PlanPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo modificar el estado del plan")


@router.delete(
    "/planes/{id}",
    response_model=MessageResponse,
    summary="Eliminar un plan SaaS",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Plan no encontrado"},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "El plan cuenta con suscripciones vinculadas"},
    },
)
def delete_plan(
    id: Annotated[int, Path(gt=0, description="Identificador único del plan")],
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> MessageResponse | JSONResponse:
    """Elimina un plan SaaS exclusivamente si no tiene suscripciones asociadas."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    try:
        service.delete_plan(id)
        return MessageResponse(message="Plan SaaS eliminado correctamente")
    except PlanNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "El plan SaaS solicitado no existe")
    except PlanHasActiveSubscriptionsError as err:
        return _error_response(status.HTTP_409_CONFLICT, str(err))
    except PlanPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo eliminar el plan SaaS")


@router.put(
    "/planes/{id}/funcionalidades",
    response_model=SaasPlanDetailResponse,
    summary="Configurar funcionalidades y límites de un plan",
    responses={
        **COMMON_RESPONSES,
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Plan o funcionalidad no encontrada"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse, "description": "Límite inválido"},
    },
)
def configure_plan_features(
    id: Annotated[int, Path(gt=0, description="Identificador único del plan")],
    payload: ConfigurePlanFeaturesRequest,
    current_user: SuperadminDependency,
    db: Session = Depends(get_db),
) -> SaasPlanDetailResponse | JSONResponse:
    """Asigna o actualiza las funcionalidades y límites configurables de un plan SaaS."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    try:
        plan = service.configure_plan_features(id, payload)
        return SaasPlanDetailResponse(message="Funcionalidades del plan configuradas correctamente", data=plan)
    except PlanNotFoundError:
        return _error_response(status.HTTP_404_NOT_FOUND, "El plan SaaS solicitado no existe")
    except FeatureNotFoundError as err:
        return _error_response(status.HTTP_404_NOT_FOUND, str(err))
    except InvalidPlanLimitError as err:
        return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err))
    except PlanPersistenceError:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudieron configurar las funcionalidades")


@router.get(
    "/funcionalidades",
    response_model=SaasFeaturesListResponse,
    summary="Listar catálogo de funcionalidades SaaS",
    responses=COMMON_RESPONSES,
)
def list_features(
    current_user: SuperadminDependency,
    estado: Annotated[bool | None, Query(description="Filtrar por estado activo/inactivo")] = None,
    db: Session = Depends(get_db),
) -> SaasFeaturesListResponse | JSONResponse:
    """Retorna todas las funcionalidades disponibles en el plano de control SaaS."""
    if isinstance(current_user, JSONResponse):
        return current_user
    service = SaasPlanService(db)
    service.ensure_default_catalog()
    features = service.list_features(state=estado)
    return SaasFeaturesListResponse(data=features, total=len(features))
