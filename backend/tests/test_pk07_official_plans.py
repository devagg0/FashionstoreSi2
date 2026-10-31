"""Pruebas locales (sin BD) de los planes comerciales oficiales del segundo parcial."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from app.PK07.CU05_GestionarPlanesSaaS.schemas import UpdateSaasPlanStatusRequest
from app.PK07.CU05_GestionarPlanesSaaS.service import (
    PlanHasActiveSubscriptionsError,
    SaasPlanService,
)

NOW = datetime(2026, 10, 31, 12, 0, 0)


class OfficialPlansTests(TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.service = SaasPlanService(self.db)
        repo = self.service.repository
        repo.get_feature_by_code = MagicMock(
            side_effect=lambda code: SimpleNamespace(id_funcionalidad_saas=hash(code) % 1000, codigo=code)
        )
        repo.create_feature = MagicMock()
        repo.set_plan_feature = MagicMock()

    def test_1_seed_defines_official_duration_limits_and_features(self):
        """BASICO 3 meses/2 sucursales/sin IA; PROFESIONAL 6 meses/10 sucursales/con IA; comunes en ambos."""
        created = {}

        def create_plan(**kw):
            plan = SimpleNamespace(id_plan_saas=len(created) + 2, **kw)
            created[kw["codigo"]] = plan
            return plan

        repo = self.service.repository
        repo.get_plan_by_code = MagicMock(return_value=None)
        repo.create_plan = MagicMock(side_effect=create_plan)

        self.service.ensure_default_catalog()

        self.assertEqual(set(created), {"BASICO", "PROFESIONAL"})  # solo los 2 planes oficiales
        self.assertEqual(created["BASICO"].periodo_meses, 3)
        self.assertEqual(created["PROFESIONAL"].periodo_meses, 6)
        self.assertEqual(created["BASICO"].precio, Decimal("199.00"))
        self.assertEqual(created["PROFESIONAL"].precio, Decimal("499.00"))

        by_plan: dict[int, dict] = {}
        for call in repo.set_plan_feature.call_args_list:
            by_plan.setdefault(call.kwargs["plan_id"], {})[call.kwargs["feature_id"]] = call.kwargs
        # 7 funcionalidades por plan; sucursales 2/10 e IA solo en PROFESIONAL
        for plan_id, expected_branches, expected_ai in ((2, 2, False), (3, 10, True)):
            cfgs = by_plan[plan_id]
            self.assertEqual(len(cfgs), 7)
            self.assertEqual(sorted(c["limit"] for c in cfgs.values() if c["limit"] is not None), [expected_branches])
            self.assertEqual(sum(1 for c in cfgs.values() if c["enabled"]), 6 + (1 if expected_ai else 0))

    def test_2_seed_is_idempotent_and_does_not_touch_existing_plans(self):
        """Con planes ya existentes (3/6 meses en Supabase) no se crea, duplica ni altera nada."""
        existing = SimpleNamespace(id_plan_saas=2, codigo="BASICO", periodo_meses=3)
        repo = self.service.repository
        repo.get_plan_by_code = MagicMock(return_value=existing)
        repo.create_plan = MagicMock()

        self.service.ensure_default_catalog()
        self.service.ensure_default_catalog()

        repo.create_plan.assert_not_called()
        repo.set_plan_feature.assert_not_called()
        self.assertEqual(existing.periodo_meses, 3)

    def test_3_plan_with_active_subscription_cannot_be_deactivated(self):
        """Un plan con suscripción vigente no se desactiva silenciosamente."""
        plan = SimpleNamespace(id_plan_saas=2, codigo="BASICO", estado=True)
        repo = self.service.repository
        repo.get_plan_by_id = MagicMock(return_value=plan)
        repo.count_active_subscriptions = MagicMock(return_value=1)

        with self.assertRaises(PlanHasActiveSubscriptionsError):
            self.service.update_plan_status(2, UpdateSaasPlanStatusRequest(estado=False))

        self.assertTrue(plan.estado)
        self.db.commit.assert_not_called()


