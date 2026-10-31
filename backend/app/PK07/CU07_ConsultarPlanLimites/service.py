"""Lógica de negocio y orquestación para PK07 / CU07: Consultar plan, límites y funcionalidades habilitadas."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.PK07.CU07_ConsultarPlanLimites.repository import SaasPlanLimitsRepository
from app.PK07.CU07_ConsultarPlanLimites.schemas import (
    BranchConsumptionSummary,
    CompanyBranchConsumptionResponse,
    CompanyBranchDetailItem,
    CompanyPlanLimitsResponse,
    FeatureItemData,
    PlanSummaryData,
    SubscriptionSummaryData,
)


class PlanLimitsError(Exception):
    """Excepción base para validaciones de plan, límites y funcionalidades SaaS."""


class CompanyNotFoundError(PlanLimitsError):
    """La empresa solicitada no existe."""


class NoActiveSubscriptionError(PlanLimitsError):
    """La empresa no cuenta con una suscripción SaaS activa vigente."""


class FeatureNotEnabledError(PlanLimitsError):
    """La funcionalidad requerida no está habilitada en el plan contratado."""


class BranchLimitExceededError(PlanLimitsError):
    """Se ha alcanzado el límite máximo de sucursales activas permitido por el plan SaaS."""


class SaasPlanLimitsService:
    """Orquesta las consultas de vigencia de planes, límites parametrizados y control de consumo."""

    def __init__(self, db: Session, repository: SaasPlanLimitsRepository | None = None) -> None:
        self.db = db
        self.repository = repository or SaasPlanLimitsRepository(db)

    def get_company_plan_limits(
        self,
        company_id: int,
        *,
        now: datetime | None = None,
    ) -> CompanyPlanLimitsResponse:
        """Obtiene de manera dinámica el plan vigente, las funcionalidades y el estado de sucursales."""
        company = self.repository.get_company_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError(f"Empresa con id {company_id} no encontrada")

        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        active_sub = self.repository.get_active_subscription(company_id, now=current_time)

        # Contar sucursales reales de la empresa
        activas = self.repository.count_company_branches(company_id, active_only=True)
        totales = self.repository.count_company_branches(company_id, active_only=False)
        inactivas = max(0, totales - activas)

        if active_sub is not None:
            tiene_suscripcion_activa = True
            dias_restantes = max(0, (active_sub.fecha_fin_periodo - current_time).days)

            sub_summary = SubscriptionSummaryData(
                id_suscripcion=active_sub.id_suscripcion,
                estado=active_sub.estado,
                fecha_inicio=active_sub.fecha_inicio,
                fecha_fin_periodo=active_sub.fecha_fin_periodo,
                dias_restantes=dias_restantes,
                renovacion_automatica=active_sub.renovacion_automatica,
                proveedor=active_sub.proveedor,
            )

            plan = self.repository.get_plan_by_id(active_sub.id_plan_saas)
            if plan is not None:
                plan_summary = PlanSummaryData(
                    id_plan_saas=plan.id_plan_saas,
                    codigo=plan.codigo,
                    nombre=plan.nombre,
                    descripcion=plan.descripcion,
                    precio=plan.precio,
                    moneda=plan.moneda,
                    periodo_meses=plan.periodo_meses,
                )
            else:
                plan_summary = None

            # Leer funcionalidades dinámicamente desde la BD
            plan_features = self.repository.list_plan_features(active_sub.id_plan_saas)
            features_list: list[FeatureItemData] = []
            permisos: dict[str, bool] = {}
            limite_sucursales: int | None = None
            tiene_ia = False

            for pf, sf in plan_features:
                features_list.append(
                    FeatureItemData(
                        codigo=sf.codigo,
                        nombre=sf.nombre,
                        descripcion=sf.descripcion,
                        habilitada=pf.habilitada,
                        limite=pf.limite,
                    )
                )
                permisos[sf.codigo] = pf.habilitada
                if sf.codigo == "SUCURSALES" and pf.habilitada:
                    limite_sucursales = pf.limite
                if sf.codigo == "REPORTES_IA" and pf.habilitada:
                    tiene_ia = True

            # Si alguna funcionalidad del catálogo general no está asociada al plan, queda deshabilitada
            all_features = self.repository.list_all_active_features()
            for sf in all_features:
                if sf.codigo not in permisos:
                    permisos[sf.codigo] = False

        else:
            # Sin suscripción activa: verificar si tuvo alguna suscripción previa (expirada, etc.)
            tiene_suscripcion_activa = False
            latest_sub = self.repository.get_latest_subscription(company_id)
            if latest_sub is not None:
                dias_restantes = 0
                sub_summary = SubscriptionSummaryData(
                    id_suscripcion=latest_sub.id_suscripcion,
                    estado=latest_sub.estado,
                    fecha_inicio=latest_sub.fecha_inicio,
                    fecha_fin_periodo=latest_sub.fecha_fin_periodo,
                    dias_restantes=dias_restantes,
                    renovacion_automatica=latest_sub.renovacion_automatica,
                    proveedor=latest_sub.proveedor,
                )
                plan = self.repository.get_plan_by_id(latest_sub.id_plan_saas)
                plan_summary = (
                    PlanSummaryData(
                        id_plan_saas=plan.id_plan_saas,
                        codigo=plan.codigo,
                        nombre=plan.nombre,
                        descripcion=plan.descripcion,
                        precio=plan.precio,
                        moneda=plan.moneda,
                        periodo_meses=plan.periodo_meses,
                    )
                    if plan
                    else None
                )
            else:
                sub_summary = None
                plan_summary = None

            features_list = []
            all_features = self.repository.list_all_active_features()
            permisos = {sf.codigo: False for sf in all_features}
            limite_sucursales = None
            tiene_ia = False

        # Cálculo de métricas de sucursales
        if limite_sucursales is not None:
            disponibles = max(0, limite_sucursales - activas)
            limite_alcanzado = activas >= limite_sucursales
        else:
            disponibles = None
            limite_alcanzado = False

        puede_crear_sucursal = tiene_suscripcion_activa and permisos.get("SUCURSALES", False) and not limite_alcanzado

        consumo = BranchConsumptionSummary(
            limite_sucursales=limite_sucursales,
            sucursales_activas=activas,
            sucursales_inactivas=inactivas,
            sucursales_totales=totales,
            disponibles_para_crear=disponibles,
            limite_alcanzado=limite_alcanzado,
            puede_crear_sucursal=puede_crear_sucursal,
        )

        return CompanyPlanLimitsResponse(
            success=True,
            id_empresa=company.id_empresa,
            empresa_codigo=company.codigo,
            empresa_nombre=company.nombre,
            tiene_suscripcion_activa=tiene_suscripcion_activa,
            suscripcion=sub_summary,
            plan=plan_summary,
            consumo_sucursales=consumo,
            funcionalidades=features_list,
            permisos=permisos,
            tiene_ia=tiene_ia,
            puede_crear_sucursal=puede_crear_sucursal,
        )

    def get_company_branch_consumption(
        self,
        company_id: int,
        *,
        now: datetime | None = None,
    ) -> CompanyBranchConsumptionResponse:
        """Retorna el reporte detallado de consumo y sucursales existentes para la empresa."""
        limits_resp = self.get_company_plan_limits(company_id, now=now)
        branches = self.repository.list_company_branches(company_id)

        branch_items: list[CompanyBranchDetailItem] = []
        for b in branches:
            branch_items.append(
                CompanyBranchDetailItem(
                    id_sucursal=b.id_sucursal,
                    nombre=b.nombre,
                    direccion=b.direccion,
                    telefono=b.telefono,
                    estado=b.estado,
                    id_ciudad=b.id_ciudad,
                    ciudad_nombre=None,
                )
            )

        return CompanyBranchConsumptionResponse(
            success=True,
            id_empresa=limits_resp.id_empresa,
            empresa_codigo=limits_resp.empresa_codigo,
            empresa_nombre=limits_resp.empresa_nombre,
            consumo=limits_resp.consumo_sucursales,
            sucursales=branch_items,
        )

    # -------------------------------------------------------------------------
    # Métodos de validación transaccional para protección de CU comerciales
    # -------------------------------------------------------------------------

    def validate_active_subscription(
        self,
        company_id: int,
        *,
        now: datetime | None = None,
    ):
        """Verifica que la empresa cuente con una suscripción activa y vigente."""
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        sub = self.repository.get_active_subscription(company_id, now=current_time)
        if sub is None:
            raise NoActiveSubscriptionError(
                "La empresa no cuenta con una suscripción SaaS activa vigente. "
                "Debe contratar o renovar un plan comercial para acceder a esta operación."
            )
        return sub

    def validate_feature_enabled(
        self,
        company_id: int,
        feature_code: str,
        *,
        now: datetime | None = None,
    ) -> None:
        """Verifica que la funcionalidad esté expresamente habilitada en el plan activo de la empresa."""
        sub = self.validate_active_subscription(company_id, now=now)
        plan_features = self.repository.list_plan_features(sub.id_plan_saas)

        feature_found = False
        is_enabled = False
        for pf, sf in plan_features:
            if sf.codigo == feature_code:
                feature_found = True
                is_enabled = pf.habilitada
                break

        if not feature_found or not is_enabled:
            raise FeatureNotEnabledError(
                f"El plan SaaS contratado no incluye la funcionalidad '{feature_code}'."
            )
        return sub

    def validate_branch_creation_limit(
        self,
        company_id: int,
        *,
        is_reactivation: bool = False,
        now: datetime | None = None,
    ) -> None:
        """Verifica que la empresa tenga suscripción vigente, la función SUCURSALES y cupo disponible."""
        # 1. Validar suscripción activa y función SUCURSALES
        self.validate_feature_enabled(company_id, "SUCURSALES", now=now)

        # 2. Consultar límite parametrizado del plan
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        sub = self.repository.get_active_subscription(company_id, now=current_time)
        if sub is None:
            raise NoActiveSubscriptionError(
                "La empresa no cuenta con una suscripción SaaS activa vigente."
            )

        plan_features = self.repository.list_plan_features(sub.id_plan_saas)
        limite_sucursales: int | None = None
        for pf, sf in plan_features:
            if sf.codigo == "SUCURSALES" and pf.habilitada:
                limite_sucursales = pf.limite
                break

        # 3. Si tiene límite numérico, verificar que no se sobrepase
        if limite_sucursales is not None:
            active_count = self.repository.count_company_branches(company_id, active_only=True)
            if active_count >= limite_sucursales:
                action = "reactivar" if is_reactivation else "crear"
                raise BranchLimitExceededError(
                    f"No es posible {action} la sucursal. Se ha alcanzado el límite máximo de "
                    f"{limite_sucursales} sucursales activas permitido por su plan SaaS."
                )
