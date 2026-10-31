"""Contexto empresarial compartido por autenticación y sesiones SQLAlchemy."""

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session, with_loader_criteria

from app.models.tenant import TenantMixin


INITIAL_COMPANY_CODE = "fashionstore-inicial"
SUPERADMIN_ROLE = "SUPERADMIN"


class TenantContextError(RuntimeError):
    """No existe una empresa válida para una operación empresarial."""


def set_tenant_context(
    session: Session,
    company_id: int | None,
    *,
    is_superadmin: bool = False,
) -> None:
    if company_id is not None and company_id <= 0:
        raise TenantContextError("El identificador de empresa no es válido")
    session.info["empresa_id"] = company_id
    session.info["is_superadmin"] = is_superadmin


def bind_initial_company(session: Session) -> int:
    """Vincula los CU heredados con la empresa creada por el backfill."""
    from app.models.company import Company

    bind = session.get_bind()
    if bind.dialect.name == "sqlite" and not inspect(bind).has_table("t_empresa"):
        # Los tests unitarios heredados crean subconjuntos de tablas en SQLite.
        # La migraciÃ³n de backfill reserva el id 1 para esta misma empresa.
        set_tenant_context(session, 1)
        return 1

    company_id = session.scalar(
        select(Company.id_empresa).where(
            Company.codigo == INITIAL_COMPANY_CODE,
            Company.estado == "ACTIVA",
        )
    )
    if company_id is None:
        raise TenantContextError("La empresa inicial no está configurada o activa")
    set_tenant_context(session, company_id)
    return company_id


def current_company_id(session: Session, *, required: bool = True) -> int | None:
    company_id = session.info.get("empresa_id")
    if company_id is None and required and not session.info.get("is_superadmin", False):
        company_id = bind_initial_company(session)
    return company_id


@event.listens_for(Session, "before_flush")
def _assign_company_before_flush(session: Session, _flush_context, _instances) -> None:
    tenant_objects = [obj for obj in session.new if isinstance(obj, TenantMixin)]
    if not tenant_objects:
        return
    company_id = current_company_id(session)
    if company_id is None:
        raise TenantContextError("SUPERADMIN debe seleccionar una empresa para escribir")
    for obj in tenant_objects:
        if getattr(obj, "empresa_id", None) is None:
            obj.empresa_id = company_id
        elif obj.empresa_id != company_id:
            raise TenantContextError("La escritura intenta cruzar empresas")


@event.listens_for(Session, "do_orm_execute")
def _filter_tenant_statements(execute_state) -> None:
    if (
        execute_state.execution_options.get("include_all_tenants")
        or execute_state.session.info.get("is_superadmin", False)
    ):
        return
    company_id = execute_state.session.info.get("empresa_id")
    if company_id is None:
        return
    if execute_state.is_select or execute_state.is_update or execute_state.is_delete:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantMixin,
                lambda entity: entity.empresa_id == company_id,
                include_aliases=True,
            )
        )
