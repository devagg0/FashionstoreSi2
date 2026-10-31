"""Capa de acceso a datos para PK07 / CU06: Gestionar suscripciones empresariales."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, inspect, select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.plan_feature import PlanFeature
from app.models.saas_feature import SaasFeature
from app.models.saas_plan import SaasPlan
from app.models.subscription import Subscription
from app.models.subscription_operation import SubscriptionOperation


class SaasSubscriptionRepository:
    """Encapsula consultas y persistencia sobre suscripciones, operaciones y planes SaaS."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._has_operations_table_cache: bool | None = None

    def _has_operations_table(self) -> bool:
        """Determina si la tabla t_operacion_suscripcion existe en la base de datos conectada."""
        if self._has_operations_table_cache is None:
            try:
                bind = self.db.get_bind()
                self._has_operations_table_cache = inspect(bind).has_table("t_operacion_suscripcion")
            except Exception:
                self._has_operations_table_cache = False
        return self._has_operations_table_cache

    def list_commercial_plans(self) -> list[SaasPlan]:
        """Obtiene planes comerciales activos ordenados por precio ascendente."""
        stmt = (
            select(SaasPlan)
            .where(SaasPlan.estado == True)
            .order_by(SaasPlan.precio.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_plan_by_id(self, plan_id: int) -> SaasPlan | None:
        """Obtiene un plan SaaS por ID primario."""
        return self.db.get(SaasPlan, plan_id)

    def get_plan_by_code(self, code: str) -> SaasPlan | None:
        """Obtiene un plan SaaS por su código único."""
        stmt = select(SaasPlan).where(SaasPlan.codigo == code)
        return self.db.scalars(stmt).first()

    def list_plan_features(self, plan_id: int) -> list[tuple[PlanFeature, SaasFeature]]:
        """Obtiene las funcionalidades y límites configurados para un plan."""
        stmt = (
            select(PlanFeature, SaasFeature)
            .join(SaasFeature, SaasFeature.id_funcionalidad_saas == PlanFeature.id_funcionalidad_saas)
            .where(PlanFeature.id_plan_saas == plan_id)
            .order_by(SaasFeature.nombre.asc())
        )
        return list(self.db.execute(stmt).all())

    def get_company_by_id(self, company_id: int) -> Company | None:
        """Obtiene una empresa por su ID primario."""
        return self.db.get(Company, company_id)

    def get_active_subscription_by_company(
        self,
        company_id: int,
        *,
        for_update: bool = False,
    ) -> Subscription | None:
        """
        Retorna la suscripción vigente (PRUEBA, ACTIVA o SUSPENDIDA) de la empresa.
        Aplica bloqueo for_update opcional para control de concurrencia.
        """
        stmt = (
            select(Subscription)
            .where(
                Subscription.id_empresa == company_id,
                Subscription.estado.in_(["PRUEBA", "ACTIVA", "SUSPENDIDA"]),
            )
            .order_by(Subscription.id_suscripcion.desc())
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalars(stmt).first()

    def get_subscription_by_id(
        self,
        subscription_id: int,
        *,
        for_update: bool = False,
    ) -> Subscription | None:
        """Obtiene una suscripción por su ID primario con bloqueo opcional."""
        if for_update:
            stmt = select(Subscription).where(Subscription.id_suscripcion == subscription_id).with_for_update()
            return self.db.scalars(stmt).first()
        return self.db.get(Subscription, subscription_id)

    def get_subscription_by_reference(
        self,
        provider: str,
        reference: str,
    ) -> Subscription | None:
        """Busca suscripción por proveedor y referencia externa (e.g. ID de sesión Stripe)."""
        stmt = select(Subscription).where(
            Subscription.proveedor == provider,
            Subscription.referencia_externa == reference,
        )
        return self.db.scalars(stmt).first()

    def list_subscriptions_by_company(self, company_id: int) -> list[Subscription]:
        """Retorna el historial completo de suscripciones de una empresa."""
        stmt = (
            select(Subscription)
            .where(Subscription.id_empresa == company_id)
            .order_by(desc(Subscription.created_at), desc(Subscription.id_suscripcion))
        )
        return list(self.db.scalars(stmt).all())

    def list_all_subscriptions(
        self,
        *,
        company_id: int | None = None,
        status: str | None = None,
        plan_id: int | None = None,
    ) -> list[Subscription]:
        """Listado administrativo para SUPERADMIN con filtros opcionales."""
        stmt = select(Subscription)
        if company_id is not None:
            stmt = stmt.where(Subscription.id_empresa == company_id)
        if status is not None:
            stmt = stmt.where(Subscription.estado == status)
        if plan_id is not None:
            stmt = stmt.where(Subscription.id_plan_saas == plan_id)
        stmt = stmt.order_by(desc(Subscription.created_at), desc(Subscription.id_suscripcion))
        return list(self.db.scalars(stmt).all())

    def create_subscription(
        self,
        *,
        company_id: int,
        plan_id: int,
        start_date: datetime,
        end_date: datetime,
        status: str = "ACTIVA",
        provider: str | None = "STRIPE",
        external_reference: str | None = None,
        auto_renew: bool = False,
    ) -> Subscription:
        """Crea un nuevo registro de suscripción en t_suscripcion."""
        sub = Subscription(
            id_empresa=company_id,
            id_plan_saas=plan_id,
            estado=status,
            fecha_inicio=start_date,
            fecha_fin_periodo=end_date,
            renovacion_automatica=auto_renew,
            proveedor=provider,
            referencia_externa=external_reference,
        )
        self.db.add(sub)
        self.db.flush()
        return sub

    def record_operation(
        self,
        *,
        company_id: int,
        plan_id: int,
        operation_type: str,
        payment_method: str = "TARJETA",
        amount: Decimal,
        currency: str = "BOB",
        provider: str = "STRIPE",
        checkout_session_id: str | None = None,
        status: str = "PENDIENTE",
        subscription_id: int | None = None,
        scheduled_date: datetime | None = None,
    ) -> SubscriptionOperation | None:
        """Registra una operación de pago o cambio en t_operacion_suscripcion si la tabla existe."""
        if not self._has_operations_table():
            return None
        try:
            op = SubscriptionOperation(
                id_empresa=company_id,
                id_plan_saas=plan_id,
                id_suscripcion=subscription_id,
                tipo_operacion=operation_type,
                estado=status,
                metodo_pago=payment_method,
                monto=amount,
                moneda=currency,
                proveedor=provider,
                id_sesion_checkout=checkout_session_id,
                fecha_ejecucion_programada=scheduled_date,
            )
            self.db.add(op)
            self.db.flush()
            return op
        except Exception:
            return None

    def get_operation_by_session(self, session_id: str) -> SubscriptionOperation | None:
        """Busca una operación por su ID de sesión Checkout de Stripe."""
        if not self._has_operations_table():
            return None
        try:
            stmt = select(SubscriptionOperation).where(
                SubscriptionOperation.id_sesion_checkout == session_id
            )
            return self.db.scalars(stmt).first()
        except Exception:
            return None

    def get_scheduled_plan_change(self, company_id: int) -> SubscriptionOperation | None:
        """Retorna la operación de cambio de plan programada vigente para una empresa."""
        if not self._has_operations_table():
            return None
        try:
            stmt = (
                select(SubscriptionOperation)
                .where(
                    SubscriptionOperation.id_empresa == company_id,
                    SubscriptionOperation.tipo_operacion == "CAMBIO_PLAN",
                    SubscriptionOperation.estado == "PROGRAMADA",
                )
                .order_by(SubscriptionOperation.id_operacion.desc())
            )
            return self.db.scalars(stmt).first()
        except Exception:
            return None

    def get_pending_operations_by_company(self, company_id: int) -> list[SubscriptionOperation]:
        """Retorna operaciones en estado PENDIENTE que cuentan con sesión Stripe para una empresa."""
        if not self._has_operations_table():
            return []
        try:
            stmt = (
                select(SubscriptionOperation)
                .where(
                    SubscriptionOperation.id_empresa == company_id,
                    SubscriptionOperation.estado == "PENDIENTE",
                    SubscriptionOperation.id_sesion_checkout.isnot(None),
                )
                .order_by(SubscriptionOperation.id_operacion.asc())
            )
            return list(self.db.scalars(stmt).all())
        except Exception:
            return []


