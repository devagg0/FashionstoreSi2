"""Repositorio de persistencia para PK07 / CU05: Gestionar planes SaaS."""

from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.plan_feature import PlanFeature
from app.models.saas_feature import SaasFeature
from app.models.saas_plan import SaasPlan
from app.models.subscription import Subscription

ACTIVE_SUBSCRIPTION_STATES = ("PRUEBA", "ACTIVA", "SUSPENDIDA")


class SaasPlanRepository:
    """Encapsula consultas y mutaciones en las tablas SaaS de control."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_plans(
        self,
        *,
        search: str | None = None,
        state: bool | None = None,
    ) -> list[SaasPlan]:
        """Obtiene la lista de planes ordenada por precio ascendente."""
        statement = select(SaasPlan)
        if state is not None:
            statement = statement.where(SaasPlan.estado.is_(state))
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(SaasPlan.codigo).like(term)
                | func.lower(SaasPlan.nombre).like(term)
                | func.lower(func.coalesce(SaasPlan.descripcion, "")).like(term)
            )
        statement = statement.order_by(SaasPlan.precio.asc(), SaasPlan.codigo.asc())
        return list(self.db.scalars(statement).all())

    def get_plan_by_id(self, plan_id: int, *, for_update: bool = False) -> SaasPlan | None:
        """Busca un plan por su ID primario."""
        statement = select(SaasPlan).where(SaasPlan.id_plan_saas == plan_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_plan_by_code(self, code: str) -> SaasPlan | None:
        """Busca un plan por su código único."""
        statement = select(SaasPlan).where(func.upper(SaasPlan.codigo) == code.strip().upper())
        return self.db.scalar(statement)

    def create_plan(
        self,
        *,
        codigo: str,
        nombre: str,
        descripcion: str | None = None,
        precio: Decimal,
        moneda: str = "BOB",
        periodo_meses: int = 1,
        estado: bool = True,
    ) -> SaasPlan:
        """Crea y persiste un nuevo plan SaaS."""
        plan = SaasPlan(
            codigo=codigo.strip().upper(),
            nombre=nombre.strip(),
            descripcion=descripcion.strip() if descripcion else None,
            precio=precio,
            moneda=moneda.strip().upper(),
            periodo_meses=periodo_meses,
            estado=estado,
        )
        self.db.add(plan)
        self.db.flush()
        return plan

    def update_plan(
        self,
        plan: SaasPlan,
        *,
        nombre: str | None = None,
        descripcion: str | None = None,
        precio: Decimal | None = None,
        periodo_meses: int | None = None,
    ) -> SaasPlan:
        """Actualiza atributos editables de un plan existente."""
        if nombre is not None:
            plan.nombre = nombre.strip()
        if descripcion is not None:
            plan.descripcion = descripcion.strip() if descripcion else None
        if precio is not None:
            plan.precio = precio
        if periodo_meses is not None:
            plan.periodo_meses = periodo_meses
        self.db.flush()
        return plan

    def set_plan_state(self, plan: SaasPlan, *, state: bool) -> SaasPlan:
        """Modifica el estado activo/inactivo de un plan."""
        plan.estado = state
        self.db.flush()
        return plan

    def delete_plan(self, plan: SaasPlan) -> None:
        """Elimina físicamente un plan que no tenga relaciones protegidas."""
        self.db.delete(plan)
        self.db.flush()

    def count_active_subscriptions(self, plan_id: int) -> int:
        """Cuenta suscripciones vigentes ('PRUEBA', 'ACTIVA', 'SUSPENDIDA') que utilizan este plan."""
        statement = (
            select(func.count(Subscription.id_suscripcion))
            .where(
                Subscription.id_plan_saas == plan_id,
                Subscription.estado.in_(ACTIVE_SUBSCRIPTION_STATES),
            )
        )
        return int(self.db.scalar(statement) or 0)

    def count_total_subscriptions(self, plan_id: int) -> int:
        """Cuenta todas las suscripciones históricas o vigentes vinculadas al plan."""
        statement = select(func.count(Subscription.id_suscripcion)).where(
            Subscription.id_plan_saas == plan_id
        )
        return int(self.db.scalar(statement) or 0)

    def list_plan_features(self, plan_id: int) -> list[tuple[PlanFeature, SaasFeature]]:
        """Obtiene las funcionalidades configuradas para un plan con sus metadatos."""
        statement = (
            select(PlanFeature, SaasFeature)
            .join(SaasFeature, SaasFeature.id_funcionalidad_saas == PlanFeature.id_funcionalidad_saas)
            .where(PlanFeature.id_plan_saas == plan_id)
            .order_by(SaasFeature.nombre.asc())
        )
        rows = self.db.execute(statement).all()
        return [(row[0], row[1]) for row in rows]

    def get_feature_by_id(self, feature_id: int) -> SaasFeature | None:
        """Consulta una funcionalidad por su identificador primario."""
        statement = select(SaasFeature).where(SaasFeature.id_funcionalidad_saas == feature_id)
        return self.db.scalar(statement)

    def get_feature_by_code(self, code: str) -> SaasFeature | None:
        """Consulta una funcionalidad por su código único."""
        statement = select(SaasFeature).where(func.upper(SaasFeature.codigo) == code.strip().upper())
        return self.db.scalar(statement)

    def list_features(self, *, state: bool | None = None) -> list[SaasFeature]:
        """Obtiene todas las funcionalidades registradas en el catálogo SaaS."""
        statement = select(SaasFeature)
        if state is not None:
            statement = statement.where(SaasFeature.estado.is_(state))
        statement = statement.order_by(SaasFeature.nombre.asc())
        return list(self.db.scalars(statement).all())

    def create_feature(
        self,
        *,
        codigo: str,
        nombre: str,
        descripcion: str | None = None,
        estado: bool = True,
    ) -> SaasFeature:
        """Registra una nueva funcionalidad en el catálogo SaaS."""
        feature = SaasFeature(
            codigo=codigo.strip().upper(),
            nombre=nombre.strip(),
            descripcion=descripcion.strip() if descripcion else None,
            estado=estado,
        )
        self.db.add(feature)
        self.db.flush()
        return feature

    def set_plan_feature(
        self,
        *,
        plan_id: int,
        feature_id: int,
        enabled: bool,
        limit: int | None,
    ) -> PlanFeature:
        """Inserta o actualiza la asignación de una funcionalidad a un plan con su límite."""
        statement = select(PlanFeature).where(
            PlanFeature.id_plan_saas == plan_id,
            PlanFeature.id_funcionalidad_saas == feature_id,
        )
        plan_feature = self.db.scalar(statement)
        if plan_feature is None:
            plan_feature = PlanFeature(
                id_plan_saas=plan_id,
                id_funcionalidad_saas=feature_id,
                habilitada=enabled,
                limite=limit,
            )
            self.db.add(plan_feature)
        else:
            plan_feature.habilitada = enabled
            plan_feature.limite = limit
        self.db.flush()
        return plan_feature

    def delete_plan_features(self, plan_id: int) -> None:
        """Elimina las asociaciones de funcionalidades de un plan."""
        statement = select(PlanFeature).where(PlanFeature.id_plan_saas == plan_id)
        for item in self.db.scalars(statement).all():
            self.db.delete(item)
        self.db.flush()

