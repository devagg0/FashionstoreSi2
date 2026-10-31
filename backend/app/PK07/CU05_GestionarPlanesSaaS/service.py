"""Lógica de negocio y orquestación para PK07 / CU05: Gestionar planes SaaS."""

from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.saas_plan import SaasPlan
from app.PK07.CU05_GestionarPlanesSaaS.repository import SaasPlanRepository
from app.PK07.CU05_GestionarPlanesSaaS.schemas import (
    ConfigurePlanFeaturesRequest,
    CreateSaasPlanRequest,
    PlanFeatureDetailData,
    PlanFeatureItemRequest,
    SaasFeatureData,
    SaasPlanDetailData,
    UpdateSaasPlanRequest,
    UpdateSaasPlanStatusRequest,
)

# Catálogo estándar de funcionalidades requeridas por FashionStore
DEFAULT_FEATURES: list[dict[str, str]] = [
    {
        "codigo": "SUCURSALES",
        "nombre": "Gestión de Sucursales",
        "descripcion": "Límite parametrizable de sucursales operativas asignadas a la empresa",
    },
    {
        "codigo": "PRODUCTOS",
        "nombre": "Catálogo y Productos",
        "descripcion": "Administración de categorías, tallas, colores, productos y variantes",
    },
    {
        "codigo": "VENTAS",
        "nombre": "Punto de Venta y Facturación",
        "descripcion": "Gestión de ventas, pagos, recibos de caja y devoluciones",
    },
    {
        "codigo": "RESERVAS",
        "nombre": "Gestión de Reservas",
        "descripcion": "Reserva de prendas y productos con control de disponibilidad",
    },
    {
        "codigo": "OFFLINE",
        "nombre": "Operación Offline",
        "descripcion": "Soporte para operar sin conexión y sincronización bidireccional",
    },
    {
        "codigo": "REPORTES_CONVENCIONALES",
        "nombre": "Reportes Convencionales",
        "descripcion": "Reportes financieros, reportes de ventas, reservas e inventarios",
    },
    {
        "codigo": "REPORTES_IA",
        "nombre": "Reportes Generativos con IA",
        "descripcion": "Generación de análisis predictivo, recomendaciones y reportes asistidos por IA",
    },
]


def _official_features(*, sucursales: int, ia: bool) -> dict[str, dict]:
    """Funcionalidades oficiales: solo varían el límite de sucursales y la IA generativa."""
    base = {
        code: {"habilitada": True, "limite": None}
        for code in ("PRODUCTOS", "VENTAS", "RESERVAS", "OFFLINE", "REPORTES_CONVENCIONALES")
    }
    return {
        "SUCURSALES": {"habilitada": True, "limite": sucursales},
        **base,
        "REPORTES_IA": {"habilitada": ia, "limite": None},
    }


# Planes comerciales oficiales (segundo parcial). Son datos de siembra inicial:
# una vez persistidos, duración, precio y límites se gestionan desde los endpoints CU05.
DEFAULT_COMMERCIAL_PLANS: list[dict] = [
    {
        "codigo": "BASICO",
        "nombre": "Plan Básico",
        "descripcion": "Ideal para negocios emergentes con hasta 2 sucursales",
        "precio": Decimal("199.00"),
        "moneda": "BOB",
        "periodo_meses": 3,
        "funcionalidades": _official_features(sucursales=2, ia=False),
    },
    {
        "codigo": "PROFESIONAL",
        "nombre": "Plan Profesional",
        "descripcion": "Para empresas en expansión con hasta 10 sucursales y reportes generativos con IA",
        "precio": Decimal("499.00"),
        "moneda": "BOB",
        "periodo_meses": 6,
        "funcionalidades": _official_features(sucursales=10, ia=True),
    },
]


class PlanNotFoundError(Exception):
    """El plan SaaS solicitado no existe."""


class PlanCodeAlreadyExistsError(Exception):
    """Ya existe un plan SaaS con el código especificado."""


class PlanHasActiveSubscriptionsError(Exception):
    """El plan cuenta con suscripciones vigentes o históricas que impiden la acción solicitada."""


class PlanActiveConditionsProtectedError(Exception):
    """No se pueden alterar silenciosamente las condiciones de un plan con suscripciones activas vigentes."""


class FeatureNotFoundError(Exception):
    """La funcionalidad solicitada no existe en el catálogo SaaS."""


class InvalidPlanLimitError(Exception):
    """El límite especificado para la funcionalidad no es válido."""


class PlanPersistenceError(Exception):
    """Ocurrió un error inesperado al persistir la información del plan SaaS."""


class SaasPlanService:
    """Orquesta las operaciones y reglas de negocio sobre planes SaaS y sus funcionalidades."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = SaasPlanRepository(db)

    def ensure_default_catalog(self) -> None:
        """Garantiza la existencia del catálogo base de funcionalidades y los planes BÁSICO y PROFESIONAL."""
        try:
            # 1. Asegurar catálogo de funcionalidades
            feature_map = {}
            for item in DEFAULT_FEATURES:
                feat = self.repository.get_feature_by_code(item["codigo"])
                if feat is None:
                    feat = self.repository.create_feature(
                        codigo=item["codigo"],
                        nombre=item["nombre"],
                        descripcion=item["descripcion"],
                        estado=True,
                    )
                feature_map[item["codigo"]] = feat

            # 2. Asegurar planes comerciales oficiales (BÁSICO y PROFESIONAL).
            #    Solo se crean si no existen: nunca se alteran planes ya persistidos.
            for spec in DEFAULT_COMMERCIAL_PLANS:
                if self.repository.get_plan_by_code(spec["codigo"]) is not None:
                    continue
                plan = self.repository.create_plan(
                    codigo=spec["codigo"],
                    nombre=spec["nombre"],
                    descripcion=spec["descripcion"],
                    precio=spec["precio"],
                    moneda=spec["moneda"],
                    periodo_meses=spec["periodo_meses"],
                    estado=True,
                )
                self._apply_features_to_plan(
                    plan.id_plan_saas,
                    [
                        {
                            "codigo": code,
                            "habilitada": cfg["habilitada"],
                            "limite": cfg["limite"],
                        }
                        for code, cfg in spec["funcionalidades"].items()
                    ],
                    feature_map,
                )

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _apply_features_to_plan(
        self,
        plan_id: int,
        feature_configs: list[dict],
        feature_map: dict,
    ) -> None:
        """Aplica configuraciones de funcionalidades y límites a un plan dado."""
        for cfg in feature_configs:
            code = cfg["codigo"]
            feat = feature_map.get(code) or self.repository.get_feature_by_code(code)
            if feat:
                self.repository.set_plan_feature(
                    plan_id=plan_id,
                    feature_id=feat.id_funcionalidad_saas,
                    enabled=cfg.get("habilitada", True),
                    limit=cfg.get("limite"),
                )

    def list_plans(
        self,
        *,
        search: str | None = None,
        state: bool | None = None,
    ) -> list[SaasPlanDetailData]:
        """Retorna todos los planes SaaS que coinciden con los criterios de búsqueda."""
        plans = self.repository.list_plans(search=search, state=state)
        return [self._to_plan_detail(p) for p in plans]

    def get_plan(self, plan_id: int) -> SaasPlanDetailData:
        """Obtiene el detalle completo de un plan por su ID primario."""
        plan = self.repository.get_plan_by_id(plan_id)
        if plan is None:
            raise PlanNotFoundError
        return self._to_plan_detail(plan)

    def create_plan(self, payload: CreateSaasPlanRequest) -> SaasPlanDetailData:
        """Crea un nuevo plan SaaS asegurando código único y configurando funcionalidades opcionales."""
        try:
            # 1. Validar unicidad del código
            if self.repository.get_plan_by_code(payload.codigo) is not None:
                raise PlanCodeAlreadyExistsError

            # 2. Crear plan
            plan = self.repository.create_plan(
                codigo=payload.codigo,
                nombre=payload.nombre,
                descripcion=payload.descripcion,
                precio=payload.precio,
                moneda=payload.moneda,
                periodo_meses=payload.periodo_meses,
                estado=payload.estado,
            )

            # 3. Asignar funcionalidades si se proporcionaron
            if payload.funcionalidades:
                self._configure_features_internal(plan.id_plan_saas, payload.funcionalidades)

            result = self._to_plan_detail(plan)
            self.db.commit()
            return result
        except (PlanCodeAlreadyExistsError, FeatureNotFoundError, InvalidPlanLimitError):
            self.db.rollback()
            raise
        except IntegrityError as error:
            self.db.rollback()
            if "uq_plan_saas_codigo" in str(error):
                raise PlanCodeAlreadyExistsError from error
            raise PlanPersistenceError from error
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise PlanPersistenceError from error

    def update_plan(self, plan_id: int, payload: UpdateSaasPlanRequest) -> SaasPlanDetailData:
        """Actualiza atributos del plan. Protege precio y período si existen suscripciones activas vigentes."""
        try:
            plan = self.repository.get_plan_by_id(plan_id, for_update=True)
            if plan is None:
                raise PlanNotFoundError

            active_subs = self.repository.count_active_subscriptions(plan_id)
            if active_subs > 0:
                # Proteger contra alteraciones de precio o período sobre planes con suscriptores vigentes
                if payload.precio is not None and payload.precio != plan.precio:
                    raise PlanActiveConditionsProtectedError(
                        "No se puede alterar el precio de un plan con suscripciones activas vigentes"
                    )
                if payload.periodo_meses is not None and payload.periodo_meses != plan.periodo_meses:
                    raise PlanActiveConditionsProtectedError(
                        "No se puede alterar el período facturable de un plan con suscripciones activas vigentes"
                    )

            plan = self.repository.update_plan(
                plan,
                nombre=payload.nombre,
                descripcion=payload.descripcion,
                precio=payload.precio,
                periodo_meses=payload.periodo_meses,
            )

            result = self._to_plan_detail(plan)
            self.db.commit()
            return result
        except (PlanNotFoundError, PlanActiveConditionsProtectedError):
            self.db.rollback()
            raise
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise PlanPersistenceError from error

    def update_plan_status(self, plan_id: int, payload: UpdateSaasPlanStatusRequest) -> SaasPlanDetailData:
        """Activa o desactiva un plan. Impide desactivar si cuenta con suscripciones activas vigentes."""
        try:
            plan = self.repository.get_plan_by_id(plan_id, for_update=True)
            if plan is None:
                raise PlanNotFoundError

            if not payload.estado:
                active_subs = self.repository.count_active_subscriptions(plan_id)
                if active_subs > 0:
                    raise PlanHasActiveSubscriptionsError(
                        f"No se puede desactivar el plan porque cuenta con {active_subs} suscripción(es) activa(s) vigente(s)"
                    )

            plan = self.repository.set_plan_state(plan, state=payload.estado)
            result = self._to_plan_detail(plan)
            self.db.commit()
            return result
        except (PlanNotFoundError, PlanHasActiveSubscriptionsError):
            self.db.rollback()
            raise
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise PlanPersistenceError from error

    def delete_plan(self, plan_id: int) -> None:
        """Elimina un plan solo si no tiene suscripciones asociadas (ni activas ni históricas)."""
        try:
            plan = self.repository.get_plan_by_id(plan_id, for_update=True)
            if plan is None:
                raise PlanNotFoundError

            total_subs = self.repository.count_total_subscriptions(plan_id)
            if total_subs > 0:
                raise PlanHasActiveSubscriptionsError(
                    f"No se puede eliminar el plan porque cuenta con {total_subs} suscripción(es) asociada(s)"
                )

            self.repository.delete_plan_features(plan_id)
            self.repository.delete_plan(plan)
            self.db.commit()
        except (PlanNotFoundError, PlanHasActiveSubscriptionsError):
            self.db.rollback()
            raise
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise PlanPersistenceError from error

    def configure_plan_features(
        self,
        plan_id: int,
        payload: ConfigurePlanFeaturesRequest,
    ) -> SaasPlanDetailData:
        """Establece las funcionalidades y límites del plan."""
        try:
            plan = self.repository.get_plan_by_id(plan_id, for_update=True)
            if plan is None:
                raise PlanNotFoundError

            self._configure_features_internal(plan_id, payload.funcionalidades)
            result = self._to_plan_detail(plan)
            self.db.commit()
            return result
        except (PlanNotFoundError, FeatureNotFoundError, InvalidPlanLimitError):
            self.db.rollback()
            raise
        except (SQLAlchemyError, Exception) as error:
            self.db.rollback()
            raise PlanPersistenceError from error

    def _configure_features_internal(
        self,
        plan_id: int,
        items: list[PlanFeatureItemRequest],
    ) -> None:
        """Valida y persiste cada funcionalidad y límite asociado al plan."""
        for item in items:
            feature = None
            if item.id_funcionalidad_saas:
                feature = self.repository.get_feature_by_id(item.id_funcionalidad_saas)
            elif item.codigo:
                feature = self.repository.get_feature_by_code(item.codigo)

            if feature is None:
                ident = item.codigo or item.id_funcionalidad_saas
                raise FeatureNotFoundError(f"La funcionalidad '{ident}' no existe en el catálogo")

            if item.limite is not None and item.limite < 0:
                raise InvalidPlanLimitError("El límite de una funcionalidad no puede ser negativo")

            self.repository.set_plan_feature(
                plan_id=plan_id,
                feature_id=feature.id_funcionalidad_saas,
                enabled=item.habilitada,
                limit=item.limite,
            )

    def list_features(self, *, state: bool | None = None) -> list[SaasFeatureData]:
        """Obtiene la lista de funcionalidades disponibles en el catálogo SaaS."""
        features = self.repository.list_features(state=state)
        return [
            SaasFeatureData(
                id_funcionalidad_saas=f.id_funcionalidad_saas,
                codigo=f.codigo,
                nombre=f.nombre,
                descripcion=f.descripcion,
                estado=f.estado,
                created_at=f.created_at,
                updated_at=f.updated_at,
            )
            for f in features
        ]

    def _to_plan_detail(self, plan: SaasPlan) -> SaasPlanDetailData:
        """Compone la representación detallada de un plan incluyendo sus funcionalidades y límites."""
        feature_rows = self.repository.list_plan_features(plan.id_plan_saas)
        features = [
            PlanFeatureDetailData(
                id_funcionalidad_saas=feature.id_funcionalidad_saas,
                codigo=feature.codigo,
                nombre=feature.nombre,
                descripcion=feature.descripcion,
                habilitada=pf.habilitada,
                limite=pf.limite,
            )
            for pf, feature in feature_rows
        ]
        active_subs = self.repository.count_active_subscriptions(plan.id_plan_saas)

        return SaasPlanDetailData(
            id_plan_saas=plan.id_plan_saas,
            codigo=plan.codigo,
            nombre=plan.nombre,
            descripcion=plan.descripcion,
            precio=plan.precio,
            moneda=plan.moneda,
            periodo_meses=plan.periodo_meses,
            estado=plan.estado,
            suscripciones_activas=active_subs,
            funcionalidades=features,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )
