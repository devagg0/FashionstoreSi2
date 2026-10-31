"""Pruebas unitarias con mocks para PK07 - CU07: Consultar plan, límites y funcionalidades habilitadas."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from fastapi.responses import JSONResponse

from app.PK07.CU07_ConsultarPlanLimites.router import _resolve_company_for_user
from app.PK07.CU07_ConsultarPlanLimites.service import (
    BranchLimitExceededError,
    FeatureNotEnabledError,
    NoActiveSubscriptionError,
    SaasPlanLimitsService,
)
from app.schemas.auth import AuthenticatedUserData

NOW = datetime(2026, 10, 31, 12, 0, 0)


def dummy_company(id_empresa: int = 1, codigo: str = "moda-oriente", nombre: str = "Moda Oriente", estado: str = "ACTIVA"):
    return SimpleNamespace(id_empresa=id_empresa, codigo=codigo, nombre=nombre, estado=estado)


def dummy_plan(
    id_plan_saas: int,
    codigo: str,
    nombre: str,
    precio: Decimal,
    periodo_meses: int,
    moneda: str = "BOB",
):
    return SimpleNamespace(
        id_plan_saas=id_plan_saas,
        codigo=codigo,
        nombre=nombre,
        descripcion=f"Plan {nombre}",
        precio=precio,
        moneda=moneda,
        periodo_meses=periodo_meses,
        estado=True,
    )


def dummy_sub(
    id_suscripcion: int = 1,
    id_empresa: int = 1,
    id_plan_saas: int = 2,
    estado: str = "ACTIVA",
    fecha_inicio: datetime | None = None,
    fecha_fin_periodo: datetime | None = None,
):
    return SimpleNamespace(
        id_suscripcion=id_suscripcion,
        id_empresa=id_empresa,
        id_plan_saas=id_plan_saas,
        estado=estado,
        fecha_inicio=fecha_inicio or datetime(2026, 10, 1, 0, 0, 0),
        fecha_fin_periodo=fecha_fin_periodo or datetime(2027, 1, 1, 0, 0, 0),
        fecha_fin_prueba=None,
        renovacion_automatica=False,
        proveedor="STRIPE",
        referencia_externa="cs_test_mock",
    )


def dummy_feature(id_feat: int, codigo: str, nombre: str):
    return SimpleNamespace(id_funcionalidad_saas=id_feat, codigo=codigo, nombre=nombre, descripcion=f"Desc {codigo}", estado=True)


def dummy_plan_feature(id_plan: int, id_feat: int, habilitada: bool, limite: int | None = None):
    return SimpleNamespace(id_plan_saas=id_plan, id_funcionalidad_saas=id_feat, habilitada=habilitada, limite=limite)


class TestCU07ConsultPlanLimits(TestCase):
    """Suite de 8 pruebas unitarias con mocks para CU07."""

    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_repo = MagicMock()
        self.service = SaasPlanLimitsService(self.mock_db, repository=self.mock_repo)

    def test_1_company_without_subscription_blocks_commercial_and_allows_consultation(self):
        """Empresa sin suscripción: consulta retorna inactiva y valida bloqueo de operaciones comerciales."""
        company = dummy_company(id_empresa=1)
        self.mock_repo.get_company_by_id.return_value = company
        self.mock_repo.get_active_subscription.return_value = None
        self.mock_repo.get_latest_subscription.return_value = None
        self.mock_repo.count_company_branches.side_effect = lambda cid, active_only: 0
        self.mock_repo.list_all_active_features.return_value = [
            dummy_feature(1, "PRODUCTOS", "Catálogo"),
            dummy_feature(2, "VENTAS", "Ventas"),
            dummy_feature(3, "SUCURSALES", "Sucursales"),
        ]

        # 1. Consulta de plan vigente
        response = self.service.get_company_plan_limits(company_id=1, now=NOW)
        self.assertFalse(response.tiene_suscripcion_activa)
        self.assertIsNone(response.plan)
        self.assertIsNone(response.suscripcion)
        self.assertFalse(response.consumo_sucursales.puede_crear_sucursal)
        self.assertFalse(response.permisos["PRODUCTOS"])
        self.assertFalse(response.permisos["VENTAS"])

        # 2. Validación de suscripción y operaciones comerciales bloqueadas
        with self.assertRaises(NoActiveSubscriptionError):
            self.service.validate_active_subscription(company_id=1, now=NOW)

        with self.assertRaises(NoActiveSubscriptionError):
            self.service.validate_feature_enabled(company_id=1, feature_code="VENTAS", now=NOW)

        with self.assertRaises(NoActiveSubscriptionError):
            self.service.validate_branch_creation_limit(company_id=1, now=NOW)

    def test_2_basico_plan_dynamic_limits_and_features(self):
        """Plan BÁSICO (199 BOB, 3 meses): 2 sucursales, sin IA, operaciones básicas habilitadas."""
        company = dummy_company(id_empresa=2, nombre="Empresa Básico")
        sub = dummy_sub(id_suscripcion=10, id_empresa=2, id_plan_saas=2, estado="ACTIVA")
        plan = dummy_plan(id_plan_saas=2, codigo="BASICO", nombre="Plan Básico", precio=Decimal("199.00"), periodo_meses=3)

        feat_suc = dummy_feature(1, "SUCURSALES", "Sucursales")
        feat_prod = dummy_feature(2, "PRODUCTOS", "Productos")
        feat_ia = dummy_feature(3, "REPORTES_IA", "Reportes IA")

        pf_suc = dummy_plan_feature(id_plan=2, id_feat=1, habilitada=True, limite=2)
        pf_prod = dummy_plan_feature(id_plan=2, id_feat=2, habilitada=True, limite=None)
        pf_ia = dummy_plan_feature(id_plan=2, id_feat=3, habilitada=False, limite=None)

        self.mock_repo.get_company_by_id.return_value = company
        self.mock_repo.get_active_subscription.return_value = sub
        self.mock_repo.get_plan_by_id.return_value = plan
        self.mock_repo.list_plan_features.return_value = [
            (pf_suc, feat_suc),
            (pf_prod, feat_prod),
            (pf_ia, feat_ia),
        ]
        self.mock_repo.list_all_active_features.return_value = [feat_suc, feat_prod, feat_ia]
        self.mock_repo.count_company_branches.side_effect = lambda cid, active_only: 1 if active_only else 1

        response = self.service.get_company_plan_limits(company_id=2, now=NOW)
        self.assertTrue(response.tiene_suscripcion_activa)
        self.assertEqual(response.plan.codigo, "BASICO")
        self.assertEqual(response.consumo_sucursales.limite_sucursales, 2)
        self.assertFalse(response.tiene_ia)
        self.assertTrue(response.permisos["PRODUCTOS"])
        self.assertFalse(response.permisos["REPORTES_IA"])

        # Validación exitosa de funcionalidad habilitada
        active_sub = self.service.validate_feature_enabled(company_id=2, feature_code="PRODUCTOS", now=NOW)
        self.assertEqual(active_sub.id_suscripcion, 10)

    def test_3_profesional_plan_dynamic_limits_and_features(self):
        """Plan PROFESIONAL (499 BOB, 6 meses): 10 sucursales, REPORTES_IA habilitado."""
        company = dummy_company(id_empresa=3, nombre="Empresa Pro")
        sub = dummy_sub(id_suscripcion=20, id_empresa=3, id_plan_saas=3, estado="ACTIVA")
        plan = dummy_plan(id_plan_saas=3, codigo="PROFESIONAL", nombre="Plan Profesional", precio=Decimal("499.00"), periodo_meses=6)

        feat_suc = dummy_feature(1, "SUCURSALES", "Sucursales")
        feat_ia = dummy_feature(2, "REPORTES_IA", "Reportes IA")

        pf_suc = dummy_plan_feature(id_plan=3, id_feat=1, habilitada=True, limite=10)
        pf_ia = dummy_plan_feature(id_plan=3, id_feat=2, habilitada=True, limite=None)

        self.mock_repo.get_company_by_id.return_value = company
        self.mock_repo.get_active_subscription.return_value = sub
        self.mock_repo.get_plan_by_id.return_value = plan
        self.mock_repo.list_plan_features.return_value = [(pf_suc, feat_suc), (pf_ia, feat_ia)]
        self.mock_repo.list_all_active_features.return_value = [feat_suc, feat_ia]
        self.mock_repo.count_company_branches.side_effect = lambda cid, active_only: 3 if active_only else 3

        response = self.service.get_company_plan_limits(company_id=3, now=NOW)
        self.assertTrue(response.tiene_suscripcion_activa)
        self.assertEqual(response.plan.codigo, "PROFESIONAL")
        self.assertEqual(response.consumo_sucursales.limite_sucursales, 10)
        self.assertTrue(response.tiene_ia)
        self.assertTrue(response.permisos["REPORTES_IA"])

        # Validación de REPORTES_IA exitosa
        self.service.validate_feature_enabled(company_id=3, feature_code="REPORTES_IA", now=NOW)

    def test_4_branch_limit_enforcement_at_capacity(self):
        """Bloqueo transaccional de creación de sucursal cuando se alcanza el límite del plan."""
        company = dummy_company(id_empresa=2)
        sub = dummy_sub(id_suscripcion=10, id_empresa=2, id_plan_saas=2)
        plan = dummy_plan(id_plan_saas=2, codigo="BASICO", nombre="Plan Básico", precio=Decimal("199.00"), periodo_meses=3)
        feat_suc = dummy_feature(1, "SUCURSALES", "Sucursales")
        pf_suc = dummy_plan_feature(id_plan=2, id_feat=1, habilitada=True, limite=2)

        self.mock_repo.get_company_by_id.return_value = company
        self.mock_repo.get_active_subscription.return_value = sub
        self.mock_repo.get_plan_by_id.return_value = plan
        self.mock_repo.list_plan_features.return_value = [(pf_suc, feat_suc)]
        self.mock_repo.list_all_active_features.return_value = [feat_suc]
        # Ya tiene 2 sucursales activas (capacidad al 100%)
        self.mock_repo.count_company_branches.side_effect = lambda cid, active_only: 2 if active_only else 2
        self.mock_repo.list_company_branches.return_value = []

        with self.assertRaises(BranchLimitExceededError) as ctx:
            self.service.validate_branch_creation_limit(company_id=2, now=NOW)
        self.assertIn("alcanzado el límite máximo de 2 sucursales activas", str(ctx.exception))

        # Consumo de sucursales refleja límite alcanzado
        consumption = self.service.get_company_branch_consumption(company_id=2, now=NOW)
        self.assertTrue(consumption.consumo.limite_alcanzado)
        self.assertFalse(consumption.consumo.puede_crear_sucursal)
        self.assertEqual(consumption.consumo.disponibles_para_crear, 0)

    def test_5_branch_reactivation_blocked_when_limit_reached(self):
        """Bloqueo al intentar reactivar una sucursal inactiva si las activas ya igualan el límite."""
        company = dummy_company(id_empresa=2)
        sub = dummy_sub(id_suscripcion=10, id_empresa=2, id_plan_saas=2)
        feat_suc = dummy_feature(1, "SUCURSALES", "Sucursales")
        pf_suc = dummy_plan_feature(id_plan=2, id_feat=1, habilitada=True, limite=2)

        self.mock_repo.get_company_by_id.return_value = company
        self.mock_repo.get_active_subscription.return_value = sub
        self.mock_repo.list_plan_features.return_value = [(pf_suc, feat_suc)]
        self.mock_repo.list_all_active_features.return_value = [feat_suc]
        # 2 activas y 1 inactiva (total 3)
        self.mock_repo.count_company_branches.side_effect = lambda cid, active_only: 2 if active_only else 3

        with self.assertRaises(BranchLimitExceededError):
            self.service.validate_branch_creation_limit(company_id=2, now=NOW)

    def test_6_branch_creation_allowed_within_limits(self):
        """Permite crear sucursal cuando el total de activas es inferior al límite parametrizado."""
        company = dummy_company(id_empresa=3)
        sub = dummy_sub(id_suscripcion=20, id_empresa=3, id_plan_saas=3)
        plan = dummy_plan(id_plan_saas=3, codigo="PROFESIONAL", nombre="Plan Profesional", precio=Decimal("499.00"), periodo_meses=6)
        feat_suc = dummy_feature(1, "SUCURSALES", "Sucursales")
        pf_suc = dummy_plan_feature(id_plan=3, id_feat=1, habilitada=True, limite=10)

        self.mock_repo.get_company_by_id.return_value = company
        self.mock_repo.get_active_subscription.return_value = sub
        self.mock_repo.get_plan_by_id.return_value = plan
        self.mock_repo.list_plan_features.return_value = [(pf_suc, feat_suc)]
        self.mock_repo.list_all_active_features.return_value = [feat_suc]
        # 3 activas de 10 permitidas
        self.mock_repo.count_company_branches.side_effect = lambda cid, active_only: 3 if active_only else 3
        self.mock_repo.list_company_branches.return_value = []

        # No debe lanzar excepción
        self.service.validate_branch_creation_limit(company_id=3, now=NOW)

        consumption = self.service.get_company_branch_consumption(company_id=3, now=NOW)
        self.assertFalse(consumption.consumo.limite_alcanzado)
        self.assertTrue(consumption.consumo.puede_crear_sucursal)
        self.assertEqual(consumption.consumo.disponibles_para_crear, 7)

    def test_7_ai_reports_access_control(self):
        """Restringe REPORTES_IA si el plan no incluye la funcionalidad (Básico sin IA)."""
        company = dummy_company(id_empresa=2)
        sub = dummy_sub(id_suscripcion=10, id_empresa=2, id_plan_saas=2)
        feat_ia = dummy_feature(3, "REPORTES_IA", "Reportes IA")
        pf_ia = dummy_plan_feature(id_plan=2, id_feat=3, habilitada=False, limite=None)

        self.mock_repo.get_company_by_id.return_value = company
        self.mock_repo.get_active_subscription.return_value = sub
        self.mock_repo.list_plan_features.return_value = [(pf_ia, feat_ia)]
        self.mock_repo.list_all_active_features.return_value = [feat_ia]

        with self.assertRaises(FeatureNotEnabledError) as ctx:
            self.service.validate_feature_enabled(company_id=2, feature_code="REPORTES_IA", now=NOW)
        self.assertIn("REPORTES_IA", str(ctx.exception))

    def test_8_tenant_isolation_and_role_permissions(self):
        """Aislamiento tenant: ADMINISTRADOR solo su empresa; SUPERADMIN consulta global; roles no autorizados denegados."""
        admin_user = AuthenticatedUserData(id_usuario=1, correo="admin@moda.bo", nombre="Admin", apellido="Moda", rol="ADMINISTRADOR", id_empresa=2)
        superadmin_user = AuthenticatedUserData(id_usuario=99, correo="root@saas.com", nombre="Super", apellido="Admin", rol="SUPERADMIN", id_empresa=None)
        client_user = AuthenticatedUserData(id_usuario=5, correo="cliente@gmail.com", nombre="Cliente", apellido="Uno", rol="CLIENTE", id_empresa=2)

        # 1. Administrador consulta su propio tenant -> permitido
        res_ok = _resolve_company_for_user(admin_user, requested_company_id=None)
        self.assertEqual(res_ok, 2)
        res_explicit_ok = _resolve_company_for_user(admin_user, requested_company_id=2)
        self.assertEqual(res_explicit_ok, 2)

        # 2. Administrador intenta cruzar a otro tenant -> 403 Forbidden
        res_forbidden = _resolve_company_for_user(admin_user, requested_company_id=3)
        self.assertIsInstance(res_forbidden, JSONResponse)
        self.assertEqual(res_forbidden.status_code, 403)

        # 3. Superadmin especifica tenant válido -> permitido
        res_sa = _resolve_company_for_user(superadmin_user, requested_company_id=3)
        self.assertEqual(res_sa, 3)

        # 4. Superadmin sin tenant -> 400 Bad Request
        res_sa_none = _resolve_company_for_user(superadmin_user, requested_company_id=None)
        self.assertIsInstance(res_sa_none, JSONResponse)
        self.assertEqual(res_sa_none.status_code, 400)

        # 5. Rol no administrativo (CLIENTE) -> 403 Forbidden
        res_client = _resolve_company_for_user(client_user, requested_company_id=2)
        self.assertIsInstance(res_client, JSONResponse)
        self.assertEqual(res_client.status_code, 403)
