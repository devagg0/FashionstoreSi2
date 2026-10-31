"""Pruebas unitarias y de integración para PK07 / CU05: Gestionar planes SaaS."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.PK07.CU05_GestionarPlanesSaaS.repository import SaasPlanRepository
from app.PK07.CU05_GestionarPlanesSaaS.router import router
from app.PK07.CU05_GestionarPlanesSaaS.schemas import (
    ConfigurePlanFeaturesRequest,
    CreateSaasPlanRequest,
    PlanFeatureItemRequest,
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
    SaasPlanService,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 10, 30, 12, 0, 0)


def dummy_plan(**overrides):
    values = {
        "id_plan_saas": 1,
        "codigo": "BASICO",
        "nombre": "Plan Básico",
        "descripcion": "Ideal para pequeños negocios",
        "precio": Decimal("199.00"),
        "moneda": "BOB",
        "periodo_meses": 1,
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def dummy_feature(**overrides):
    values = {
        "id_funcionalidad_saas": 1,
        "codigo": "SUCURSALES",
        "nombre": "Gestión de Sucursales",
        "descripcion": "Límite parametrizable de sucursales",
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def dummy_plan_feature(**overrides):
    values = {
        "id_plan_saas": 1,
        "id_funcionalidad_saas": 1,
        "habilitada": True,
        "limite": 2,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SaasPlanServiceTests(TestCase):
    """Pruebas del servicio y reglas de negocio de planes SaaS."""

    def setUp(self):
        self.db = MagicMock()
        self.service = SaasPlanService(self.db)

    def test_ensure_default_catalog_creates_basico_and_profesional(self):
        """1. Garantiza existencia de planes BÁSICO (máx 2 sucursales) y PROFESIONAL (máx 10) con sus funcionalidades."""
        self.service.repository.get_feature_by_code = MagicMock(return_value=None)
        self.service.repository.create_feature = MagicMock(side_effect=lambda **kw: dummy_feature(**kw))
        self.service.repository.get_plan_by_code = MagicMock(return_value=None)
        created_plans = []
        self.service.repository.create_plan = MagicMock(
            side_effect=lambda **kw: created_plans.append(dummy_plan(**kw)) or created_plans[-1]
        )
        self.service.repository.set_plan_feature = MagicMock()

        self.service.ensure_default_catalog()

        self.assertEqual(len(created_plans), 2)
        codes = [p.codigo for p in created_plans]
        self.assertIn("BASICO", codes)
        self.assertIn("PROFESIONAL", codes)

        # Verificamos que se asignaron las funcionalidades con límites requeridos
        calls = self.service.repository.set_plan_feature.call_args_list
        limits_applied = [c.kwargs.get("limit") for c in calls if c.kwargs.get("limit") is not None]
        self.assertIn(2, limits_applied)   # Básico máx 2 sucursales
        self.assertIn(10, limits_applied)  # Profesional máx 10 sucursales
        self.db.commit.assert_called()

    def test_list_plans_with_search_and_state_filter(self):
        """2. Listado de planes con filtros de búsqueda y estado."""
        p1 = dummy_plan(id_plan_saas=1, codigo="BASICO")
        p2 = dummy_plan(id_plan_saas=2, codigo="PROFESIONAL")
        self.service.repository.list_plans = MagicMock(return_value=[p1, p2])
        self.service.repository.list_plan_features = MagicMock(return_value=[])
        self.service.repository.count_active_subscriptions = MagicMock(return_value=3)

        plans = self.service.list_plans(search="PRO", state=True)

        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0].codigo, "BASICO")
        self.assertEqual(plans[0].suscripciones_activas, 3)
        self.service.repository.list_plans.assert_called_once_with(search="PRO", state=True)

    def test_create_saas_plan_success(self):
        """3. Creación exitosa de plan con código único, límites y funcionalidades configurables."""
        self.service.repository.get_plan_by_code = MagicMock(return_value=None)
        new_plan = dummy_plan(id_plan_saas=5, codigo="ENTERPRISE", nombre="Plan Enterprise")
        self.service.repository.create_plan = MagicMock(return_value=new_plan)
        self.service.repository.get_feature_by_code = MagicMock(return_value=dummy_feature(id_funcionalidad_saas=10))
        self.service.repository.set_plan_feature = MagicMock()
        self.service.repository.list_plan_features = MagicMock(
            return_value=[(dummy_plan_feature(limite=50), dummy_feature(codigo="SUCURSALES"))]
        )
        self.service.repository.count_active_subscriptions = MagicMock(return_value=0)

        payload = CreateSaasPlanRequest(
            codigo="enterprise",
            nombre="Plan Enterprise",
            descripcion="Plan corporativo a gran escala",
            precio=Decimal("999.00"),
            periodo_meses=12,
            funcionalidades=[
                PlanFeatureItemRequest(codigo="SUCURSALES", habilitada=True, limite=50),
            ],
        )

        res = self.service.create_plan(payload)

        self.assertEqual(res.codigo, "ENTERPRISE")
        self.assertEqual(res.id_plan_saas, 5)
        self.service.repository.create_plan.assert_called_once()
        self.service.repository.set_plan_feature.assert_called_once()
        self.db.commit.assert_called_once()

    def test_create_plan_rejects_duplicate_code(self):
        """4. Rechaza creación de plan si el código ya existe en el sistema."""
        self.service.repository.get_plan_by_code = MagicMock(return_value=dummy_plan())

        payload = CreateSaasPlanRequest(
            codigo="BASICO",
            nombre="Otro Plan",
            precio=Decimal("150.00"),
        )

        with self.assertRaises(PlanCodeAlreadyExistsError):
            self.service.create_plan(payload)

    def test_create_plan_validates_non_negative_price_and_limits(self):
        """5. Valida que el precio no sea negativo y los límites sean no negativos."""
        # Precio negativo
        with self.assertRaises(ValueError):
            CreateSaasPlanRequest(
                codigo="INVALID_PRECIO",
                nombre="Invalido",
                precio=Decimal("-10.00"),
            )

        # Límite negativo
        with self.assertRaises(ValueError):
            PlanFeatureItemRequest(
                codigo="SUCURSALES",
                limite=-5,
            )

    def test_update_plan_protects_active_subscriptions(self):
        """6. Impide alterar silenciosamente precio o período de planes con suscriptores vigentes."""
        plan = dummy_plan(id_plan_saas=1, precio=Decimal("199.00"), periodo_meses=1)
        self.service.repository.get_plan_by_id = MagicMock(return_value=plan)
        self.service.repository.count_active_subscriptions = MagicMock(return_value=5)  # 5 activas

        # Intentar modificar el precio
        payload_price = UpdateSaasPlanRequest(precio=Decimal("249.00"))
        with self.assertRaises(PlanActiveConditionsProtectedError):
            self.service.update_plan(1, payload_price)

        # Intentar modificar el período
        payload_period = UpdateSaasPlanRequest(periodo_meses=3)
        with self.assertRaises(PlanActiveConditionsProtectedError):
            self.service.update_plan(1, payload_period)

    def test_deactivate_plan_protects_active_subscriptions(self):
        """7. Impide desactivar un plan que tiene suscripciones activas vigentes."""
        plan = dummy_plan(id_plan_saas=1, estado=True)
        self.service.repository.get_plan_by_id = MagicMock(return_value=plan)
        self.service.repository.count_active_subscriptions = MagicMock(return_value=2)

        payload = UpdateSaasPlanStatusRequest(estado=False)
        with self.assertRaises(PlanHasActiveSubscriptionsError):
            self.service.update_plan_status(1, payload)

    def test_delete_plan_rejects_if_subscriptions_exist(self):
        """8. Protege contra eliminación de planes con suscripciones vinculadas."""
        plan = dummy_plan(id_plan_saas=1)
        self.service.repository.get_plan_by_id = MagicMock(return_value=plan)
        self.service.repository.count_total_subscriptions = MagicMock(return_value=4)

        with self.assertRaises(PlanHasActiveSubscriptionsError):
            self.service.delete_plan(1)

    def test_delete_plan_success_when_no_subscriptions(self):
        """9. Permite eliminar un plan si no cuenta con suscripciones vinculadas."""
        plan = dummy_plan(id_plan_saas=3)
        self.service.repository.get_plan_by_id = MagicMock(return_value=plan)
        self.service.repository.count_total_subscriptions = MagicMock(return_value=0)
        self.service.repository.delete_plan_features = MagicMock()
        self.service.repository.delete_plan = MagicMock()

        self.service.delete_plan(3)

        self.service.repository.delete_plan_features.assert_called_once_with(3)
        self.service.repository.delete_plan.assert_called_once_with(plan)
        self.db.commit.assert_called_once()


class SaasPlanRouterTests(TestCase):
    """Pruebas de autorización SUPERADMIN y respuestas HTTP de la API."""

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

        self.superadmin = AuthenticatedUserData(
            id_usuario=1,
            nombre="Super",
            apellido="Admin",
            correo="superadmin@fashionstore.com",
            telefono="77777777",
            rol="SUPERADMIN",
            estado=True,
            id_empresa=None,
        )

    def test_endpoints_require_superadmin_role(self):
        """10. Valida que los endpoints de planes rechazan roles no SUPERADMIN con 403 y sin token con 401."""
        # Sin token
        resp_no_token = self.client.get("/api/saas/planes")
        self.assertEqual(resp_no_token.status_code, 401)

        # Con usuario no SUPERADMIN (ADMINISTRADOR de empresa)
        normal_admin = self.superadmin.model_copy(update={"rol": "ADMINISTRADOR", "id_empresa": 2})
        with patch("app.PK07.CU01_RegistrarEmpresa.router.AuthService") as mock_auth_cls:
            mock_auth = mock_auth_cls.return_value
            mock_auth.get_current_user.return_value = normal_admin

            resp_forbidden = self.client.get(
                "/api/saas/planes",
                headers={"Authorization": "Bearer admin-token"},
            )
            self.assertEqual(resp_forbidden.status_code, 403)
            self.assertIn("Se requiere el rol SUPERADMIN", resp_forbidden.json()["message"])

