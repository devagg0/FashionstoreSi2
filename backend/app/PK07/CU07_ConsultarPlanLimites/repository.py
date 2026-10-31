"""Acceso a datos para PK07 / CU07: Consultar plan, límites y funcionalidades habilitadas."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.company import Company
from app.models.plan_feature import PlanFeature
from app.models.saas_feature import SaasFeature
from app.models.saas_plan import SaasPlan
from app.models.subscription import Subscription


class SaasPlanLimitsRepository:
    """Encapsula las consultas de base de datos para límites, suscripciones y consumo multitenant."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_company_by_id(self, company_id: int) -> Company | None:
        """Obtiene la empresa por su identificador primario."""
        statement = select(Company).where(Company.id_empresa == company_id)
        return self.db.execute(statement).scalar_one_or_none()

    def get_active_subscription(
        self,
        company_id: int,
        now: datetime | None = None,
    ) -> Subscription | None:
        """Retorna la suscripción activa y vigente de la empresa."""
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        statement = (
            select(Subscription)
            .where(
                Subscription.id_empresa == company_id,
                Subscription.estado.in_(("ACTIVA", "PRUEBA")),
                Subscription.fecha_fin_periodo > current_time,
            )
            .order_by(Subscription.id_suscripcion.desc())
        )
        return self.db.execute(statement).scalars().first()

    def get_latest_subscription(self, company_id: int) -> Subscription | None:
        """Retorna la suscripción más reciente de la empresa (incluso expirada o cancelada)."""
        statement = (
            select(Subscription)
            .where(Subscription.id_empresa == company_id)
            .order_by(Subscription.id_suscripcion.desc())
        )
        return self.db.execute(statement).scalars().first()

    def get_plan_by_id(self, plan_id: int) -> SaasPlan | None:
        """Obtiene el plan SaaS por su identificador."""
        statement = select(SaasPlan).where(SaasPlan.id_plan_saas == plan_id)
        return self.db.execute(statement).scalar_one_or_none()

    def list_plan_features(self, plan_id: int) -> list[tuple[PlanFeature, SaasFeature]]:
        """Retorna las funcionalidades y límites configurados dinámicamente para el plan."""
        statement = (
            select(PlanFeature, SaasFeature)
            .join(
                SaasFeature,
                SaasFeature.id_funcionalidad_saas == PlanFeature.id_funcionalidad_saas,
            )
            .where(
                PlanFeature.id_plan_saas == plan_id,
                SaasFeature.estado.is_(True),
            )
            .order_by(SaasFeature.id_funcionalidad_saas.asc())
        )
        return list(self.db.execute(statement).all())

    def list_all_active_features(self) -> list[SaasFeature]:
        """Retorna el catálogo global de funcionalidades SaaS activas."""
        statement = (
            select(SaasFeature)
            .where(SaasFeature.estado.is_(True))
            .order_by(SaasFeature.id_funcionalidad_saas.asc())
        )
        return list(self.db.execute(statement).scalars().all())

    def count_company_branches(
        self,
        company_id: int,
        *,
        active_only: bool = False,
    ) -> int:
        """Cuenta las sucursales pertenecientes a la empresa (todas o solo activas)."""
        statement = select(func.count(Branch.id_sucursal)).where(Branch.empresa_id == company_id)
        if active_only:
            statement = statement.where(Branch.estado.is_(True))
        return self.db.execute(statement).scalar() or 0

    def list_company_branches(self, company_id: int) -> list[Branch]:
        """Lista todas las sucursales de la empresa ordenadas por ID."""
        statement = (
            select(Branch)
            .where(Branch.empresa_id == company_id)
            .order_by(Branch.id_sucursal.asc())
        )
        return list(self.db.execute(statement).scalars().all())

