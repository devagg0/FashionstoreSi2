"""Pruebas unitarias específicas para PK07 / CU06: Gestionar suscripciones empresariales."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from dateutil.relativedelta import relativedelta

from app.PK07.CU06_GestionarSuscripciones.schemas import CreateCheckoutRequest
from app.PK07.CU06_GestionarSuscripciones.service import (
    InvalidPlanChangeError,
    PaymentNotCompletedError,
    SaasSubscriptionService,
    StripeValidationError,
    SubscriptionAlreadyActiveError,
    TenantMismatchError,
)

NOW = datetime(2026, 10, 31, 12, 0, 0)


def create_dummy_plan(**overrides):
    values = {
        "id_plan_saas": 2,
        "codigo": "BASICO",
        "nombre": "Plan Básico",
        "descripcion": "Ideal para negocios emergentes",
        "precio": Decimal("199.00"),
        "moneda": "BOB",
        "periodo_meses": 3,
        "estado": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def create_dummy_company(**overrides):
    values = {
        "id_empresa": 1,
        "codigo": "fashionstore-inicial",
        "nombre": "FashionStore Inicial",
        "estado": "ACTIVA",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def create_dummy_subscription(**overrides):
    values = {
        "id_suscripcion": 10,
        "id_empresa": 1,
        "id_plan_saas": 2,
        "estado": "ACTIVA",
        "fecha_inicio": NOW,
        "fecha_fin_periodo": NOW + relativedelta(months=3),
        "fecha_fin_prueba": None,
        "fecha_cancelacion": None,
        "renovacion_automatica": False,
        "proveedor": "STRIPE",
        "referencia_externa": "cs_test_initial_001",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class SaasSubscriptionServiceTests(TestCase):
    """8 pruebas locales específicas para CU06 con mocks de Stripe."""

    def setUp(self):
        self.db = MagicMock()
        self.stripe_mock = MagicMock()
        self.service = SaasSubscriptionService(self.db, stripe_service=self.stripe_mock)
        # Mock repository methods
        self.repo = self.service.repository
        self.repo.create_subscription = MagicMock()
        self.repo.record_operation = MagicMock()

    def test_1_create_checkout_session_card_and_qr(self):
        """1. Inicia sesión Stripe Checkout para tarjeta y QR con importe seguro y metadatos verificados."""
        company = create_dummy_company()
        plan = create_dummy_plan()

        self.repo.get_company_by_id = MagicMock(return_value=company)
        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=None)
        self.repo.record_operation = MagicMock(return_value=None)

        fake_session = {
            "id": "cs_test_card_123",
            "url": "https://checkout.stripe.com/c/pay/cs_test_card_123",
        }
        self.stripe_mock.create_saas_checkout_session.return_value = fake_session

        # A) Pago con tarjeta
        req_card = CreateCheckoutRequest(id_plan_saas=2, tipo_operacion="CONTRATACION")
        res_card = self.service.create_checkout_session(company_id=1, payload=req_card, payment_method="TARJETA")

        self.assertEqual(res_card.id_sesion, "cs_test_card_123")
        self.assertEqual(res_card.metodo_pago, "TARJETA")
        self.assertIsNone(res_card.qr_data)
        self.assertEqual(res_card.monto, Decimal("199.00"))

        # B) Pago con QR (abre el mismo Stripe Checkout)
        fake_session_qr = {
            "id": "cs_test_qr_456",
            "url": "https://checkout.stripe.com/c/pay/cs_test_qr_456",
        }
        self.stripe_mock.create_saas_checkout_session.return_value = fake_session_qr

        req_qr = CreateCheckoutRequest(id_plan_saas=2, tipo_operacion="CONTRATACION")
        res_qr = self.service.create_checkout_session(company_id=1, payload=req_qr, payment_method="QR")

        self.assertEqual(res_qr.id_sesion, "cs_test_qr_456")
        self.assertEqual(res_qr.metodo_pago, "QR")
        self.assertEqual(res_qr.qr_data, fake_session_qr["url"])

        # Verificar llamada a Stripe con importe en centavos extraído del plan
        self.stripe_mock.create_saas_checkout_session.assert_called_with(
            amount=19900,
            currency="bob",
            company_id=1,
            company_name="FashionStore Inicial",
            plan_id=2,
            plan_name="Plan Básico",
            plan_code="BASICO",
            operation="CONTRATACION",
            tracking_id=self.stripe_mock.create_saas_checkout_session.call_args.kwargs["tracking_id"],
            success_url=self.stripe_mock.create_saas_checkout_session.call_args.kwargs["success_url"],
            cancel_url=self.stripe_mock.create_saas_checkout_session.call_args.kwargs["cancel_url"],
        )

    def test_2_verify_payment_success_activates_subscription(self):
        """2. Concilia pago pagado en Stripe TEST y activa la suscripción calculando el vencimiento según meses del plan."""
        plan = create_dummy_plan()
        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_subscription_by_reference = MagicMock(return_value=None)
        self.repo.get_operation_by_session = MagicMock(return_value=None)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=None)

        created_sub = create_dummy_subscription(id_suscripcion=101, referencia_externa="cs_test_paid_777")
        self.repo.create_subscription = MagicMock(return_value=created_sub)

        stripe_session = {
            "id": "cs_test_paid_777",
            "livemode": False,
            "payment_status": "paid",
            "amount_total": 19900,
            "currency": "bob",
            "metadata": {
                "empresa_id": "1",
                "plan_id": "2",
                "operacion": "CONTRATACION",
            },
            "payment_intent": "pi_test_001",
        }
        self.stripe_mock.retrieve_checkout_session.return_value = stripe_session

        res = self.service.verify_and_sync_payment("cs_test_paid_777", authenticated_company_id=1)

        self.assertTrue(res.success)
        self.assertEqual(res.id_suscripcion, 101)
        self.assertEqual(res.estado, "ACTIVA")
        self.assertEqual(res.tipo_operacion, "CONTRATACION")
        self.repo.create_subscription.assert_called_once()
        self.db.commit.assert_called_once()

    def test_3_verify_payment_unpaid_or_livemode_fails(self):
        """3. Rechaza activación si el pago no está completado en Stripe o si se intenta operar en livemode."""
        plan = create_dummy_plan()
        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_subscription_by_reference = MagicMock(return_value=None)
        self.repo.get_operation_by_session = MagicMock(return_value=None)

        # Caso A: Sesión no pagada (unpaid)
        unpaid_session = {
            "id": "cs_test_unpaid",
            "livemode": False,
            "payment_status": "unpaid",
            "metadata": {"empresa_id": "1", "plan_id": "2"},
        }
        self.stripe_mock.retrieve_checkout_session.return_value = unpaid_session

        with self.assertRaises(PaymentNotCompletedError):
            self.service.verify_and_sync_payment("cs_test_unpaid", authenticated_company_id=1)

        # Caso B: livemode = True (prohibido)
        live_session = {
            "id": "cs_live_session",
            "livemode": True,
            "payment_status": "paid",
            "metadata": {"empresa_id": "1", "plan_id": "2"},
        }
        self.stripe_mock.retrieve_checkout_session.return_value = live_session

        with self.assertRaises(StripeValidationError):
            self.service.verify_and_sync_payment("cs_live_session", authenticated_company_id=1)

        # Asegurar que nunca se crea una suscripción ante pago fallido o inválido
        self.repo.create_subscription.assert_not_called()
        self.db.commit.assert_not_called()

    def test_4_renew_subscription_extends_period_without_losing_days(self):
        """4. Renovación pagada extiende la vigencia sumando los meses del plan a la fecha de vencimiento actual."""
        plan = create_dummy_plan(periodo_meses=3)
        # Suscripción activa que vence en el futuro (ej. dentro de 30 días)
        current_expiry = NOW + relativedelta(days=30)
        current_sub = create_dummy_subscription(fecha_fin_periodo=current_expiry, estado="ACTIVA")

        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_subscription_by_reference = MagicMock(return_value=None)
        self.repo.get_operation_by_session = MagicMock(return_value=None)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=current_sub)

        stripe_session = {
            "id": "cs_test_renew_888",
            "livemode": False,
            "payment_status": "paid",
            "amount_total": 19900,
            "currency": "bob",
            "metadata": {
                "empresa_id": "1",
                "plan_id": "2",
                "operacion": "RENOVACION",
            },
        }
        self.stripe_mock.retrieve_checkout_session.return_value = stripe_session

        res = self.service.verify_and_sync_payment("cs_test_renew_888", authenticated_company_id=1)

        self.assertTrue(res.success)
        self.assertEqual(res.tipo_operacion, "RENOVACION")
        # Fecha de fin extendida exactamente 3 meses sobre current_expiry (sin perder los 30 días restantes)
        expected_new_expiry = current_expiry + relativedelta(months=3)
        self.assertEqual(current_sub.fecha_fin_periodo, expected_new_expiry)
        self.assertEqual(current_sub.referencia_externa, "cs_test_renew_888")
        self.db.commit.assert_called_once()

    def test_5_active_subscription_blocks_all_operations_while_valid(self):
        """1. Con plan ACTIVO y período vigente: bloquea CONTRATACION, RENOVACION y CAMBIO_PLAN."""
        company = create_dummy_company()
        current_plan = create_dummy_plan(id_plan_saas=2, codigo="BASICO")
        pro_plan = create_dummy_plan(id_plan_saas=3, codigo="PROFESIONAL")
        current_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + relativedelta(months=2)
        active_sub = create_dummy_subscription(id_plan_saas=2, fecha_fin_periodo=current_expiry, estado="ACTIVA")

        self.repo.get_company_by_id = MagicMock(return_value=company)
        self.repo.get_plan_by_id = MagicMock(side_effect=lambda pid: pro_plan if pid == 3 else current_plan)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=active_sub)

        # A) Bloqueo de CONTRATACION
        req_contract = CreateCheckoutRequest(id_plan_saas=3, tipo_operacion="CONTRATACION")
        with self.assertRaises(SubscriptionAlreadyActiveError) as ctx_c:
            self.service.create_checkout_session(company_id=1, payload=req_contract)
        self.assertIn("disponible al finalizar tu suscripción actual", str(ctx_c.exception).lower())

        # B) Bloqueo de RENOVACION anticipada
        req_renew = CreateCheckoutRequest(id_plan_saas=2, tipo_operacion="RENOVACION")
        with self.assertRaises(InvalidPlanChangeError) as ctx_r:
            self.service.create_checkout_session(company_id=1, payload=req_renew)
        self.assertIn("No es posible renovar anticipadamente", str(ctx_r.exception))
        self.assertIn("disponible al finalizar tu suscripción actual", str(ctx_r.exception).lower())

        # C) Bloqueo de CAMBIO_PLAN
        req_change = CreateCheckoutRequest(id_plan_saas=3, tipo_operacion="CAMBIO_PLAN")
        with self.assertRaises(InvalidPlanChangeError) as ctx_ch:
            self.service.create_checkout_session(company_id=1, payload=req_change)
        self.assertIn("No es posible cambiar de plan", str(ctx_ch.exception))
        self.assertIn("disponible al finalizar tu suscripción actual", str(ctx_ch.exception).lower())

    def test_5_b_expired_period_allows_renewal_or_new_plan(self):
        """2. Al vencer el período: permite renovar el mismo plan o contratar otro mediante Stripe TEST."""
        company = create_dummy_company()
        past_expiry = datetime.now(timezone.utc).replace(tzinfo=None) - relativedelta(days=5)
        expired_sub = create_dummy_subscription(id_plan_saas=2, fecha_fin_periodo=past_expiry, estado="EXPIRADA")
        plan_basico = create_dummy_plan(id_plan_saas=2, codigo="BASICO", periodo_meses=3)
        plan_pro = create_dummy_plan(id_plan_saas=3, codigo="PROFESIONAL", periodo_meses=6)

        self.repo.get_company_by_id = MagicMock(return_value=company)
        self.repo.get_plan_by_id = MagicMock(side_effect=lambda pid: plan_pro if pid == 3 else plan_basico)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=None)
        self.repo.list_subscriptions_by_company = MagicMock(return_value=[expired_sub])
        self.repo.record_operation = MagicMock(return_value=None)
        self.stripe_mock.create_saas_checkout_session.return_value = {
            "id": "cs_test_session_ok",
            "url": "https://checkout.stripe.com/pay/cs_test_session_ok",
        }

        # A) Renovar plan tras vencer período: PERMITIDO
        req_renew = CreateCheckoutRequest(id_plan_saas=2, tipo_operacion="RENOVACION")
        res_renew = self.service.create_checkout_session(company_id=1, payload=req_renew)
        self.assertEqual(res_renew.id_sesion, "cs_test_session_ok")

        # B) Contratar plan diferente tras vencer período: PERMITIDO
        req_pro = CreateCheckoutRequest(id_plan_saas=3, tipo_operacion="CONTRATACION")
        res_pro = self.service.create_checkout_session(company_id=1, payload=req_pro)
        self.assertEqual(res_pro.id_sesion, "cs_test_session_ok")
        self.assertEqual(res_pro.id_plan_saas, 3)

    def test_5_c_verify_payment_blocks_incompatible_preserving_confirmed_payment(self):
        """3. Bloquea verificación de operaciones incompatibles con vigencia activa, preservando el pago confirmado."""
        current_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + relativedelta(months=2)
        active_sub = create_dummy_subscription(
            id_suscripcion=10,
            id_plan_saas=2,
            fecha_fin_periodo=current_expiry,
            estado="ACTIVA",
            referencia_externa="cs_test_active_sub",
        )
        plan = create_dummy_plan(id_plan_saas=2)
        op_pending = SimpleNamespace(
            id_operacion=99,
            id_sesion_checkout="cs_test_incompatible_paid",
            estado="PENDIENTE",
            id_pago_externo=None,
            updated_at=None,
        )

        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_subscription_by_reference = MagicMock(return_value=None)
        self.repo.get_operation_by_session = MagicMock(return_value=op_pending)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=active_sub)

        stripe_session = {
            "id": "cs_test_incompatible_paid",
            "livemode": False,
            "payment_status": "paid",
            "amount_total": 19900,
            "currency": "bob",
            "metadata": {"empresa_id": "1", "plan_id": "2", "operacion": "RENOVACION"},
            "payment_intent": {"id": "pi_confirmed_safe_123"},
        }
        self.stripe_mock.retrieve_checkout_session.return_value = stripe_session

        with self.assertRaises(SubscriptionAlreadyActiveError) as ctx_err:
            self.service.verify_and_sync_payment("cs_test_incompatible_paid", authenticated_company_id=1)

        # La activación se bloquea reportando vigencia
        self.assertIn("La empresa cuenta con una suscripción vigente", str(ctx_err.exception))
        # Pero el pago confirmado pi_confirmed_safe_123 queda preservado en op_pending sin perderse
        self.assertEqual(op_pending.id_pago_externo, "pi_confirmed_safe_123")
        self.db.commit.assert_called_once()
        self.repo.create_subscription.assert_not_called()

    def test_6_verification_is_idempotent(self):
        """6. Re-verificar una sesión ya aplicada responde exitosamente sin duplicar registros ni volver a extender."""
        plan = create_dummy_plan()
        existing_sub = create_dummy_subscription(id_suscripcion=50, referencia_externa="cs_test_already_processed")

        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        # El repositorio ya encuentra la suscripción vinculada a esa sesión
        self.repo.get_subscription_by_reference = MagicMock(return_value=existing_sub)

        stripe_session = {
            "id": "cs_test_already_processed",
            "livemode": False,
            "payment_status": "paid",
            "amount_total": 19900,
            "currency": "bob",
            "metadata": {
                "empresa_id": "1",
                "plan_id": "2",
                "operacion": "CONTRATACION",
            },
        }
        self.stripe_mock.retrieve_checkout_session.return_value = stripe_session

        res = self.service.verify_and_sync_payment("cs_test_already_processed", authenticated_company_id=1)

        self.assertTrue(res.success)
        self.assertEqual(res.id_suscripcion, 50)
        self.assertIn("previamente", res.message)
        # No se vuelve a llamar create_subscription
        self.repo.create_subscription.assert_not_called()

    def test_7_multitenant_isolation(self):
        """7. Impide que un usuario de la empresa A verifique o acceda a pagos de la empresa B."""
        stripe_session = {
            "id": "cs_test_company_2",
            "livemode": False,
            "payment_status": "paid",
            "amount_total": 19900,
            "currency": "bob",
            "metadata": {
                "empresa_id": "2",  # Pertenece a empresa 2
                "plan_id": "2",
                "operacion": "CONTRATACION",
            },
        }
        self.stripe_mock.retrieve_checkout_session.return_value = stripe_session

        # Usuario autenticado pertenece a empresa 1
        with self.assertRaises(TenantMismatchError):
            self.service.verify_and_sync_payment(
                "cs_test_company_2",
                authenticated_company_id=1,
                is_superadmin=False,
            )

    def test_8_superadmin_manage_subscription_status(self):
        """8. SUPERADMIN puede suspender, reactivar y cancelar suscripciones cumpliendo restricciones de integridad."""
        sub = create_dummy_subscription(id_suscripcion=10, estado="ACTIVA", fecha_cancelacion=None)
        company = create_dummy_company()
        plan = create_dummy_plan()

        self.repo.get_subscription_by_id = MagicMock(return_value=sub)
        self.repo.get_company_by_id = MagicMock(return_value=company)
        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.list_plan_features = MagicMock(return_value=[])
        self.repo.get_scheduled_plan_change = MagicMock(return_value=None)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=sub)

        # A) Suspender administrativamente
        detail_susp = self.service.admin_update_subscription_status(10, new_status="SUSPENDIDA")
        self.assertEqual(sub.estado, "SUSPENDIDA")
        self.assertEqual(detail_susp.estado, "SUSPENDIDA")

        # B) Reactivar administrativamente
        detail_act = self.service.admin_update_subscription_status(10, new_status="ACTIVA")
        self.assertEqual(sub.estado, "ACTIVA")
        self.assertEqual(detail_act.estado, "ACTIVA")

        # C) Cancelar administrativamente (debe setear fecha_cancelacion para satisfacer ck_suscripcion_cancelacion)
        detail_canc = self.service.admin_update_subscription_status(10, new_status="CANCELADA")
        self.assertEqual(sub.estado, "CANCELADA")
        self.assertIsNotNone(sub.fecha_cancelacion)
        self.assertFalse(sub.renovacion_automatica)
        self.assertEqual(detail_canc.estado, "CANCELADA")
        self.assertEqual(self.db.commit.call_count, 3)

    def test_9_reconcile_pending_operations_activates_if_stripe_paid(self):
        """9. Recupera operación PENDIENTE existente y activa la suscripción al confirmar que Stripe está pagada."""
        company = create_dummy_company(id_empresa=2, nombre="Moda Oriente")
        plan = create_dummy_plan(id_plan_saas=2, codigo="BASICO", precio=Decimal("199.00"))
        pending_op = SimpleNamespace(
            id_operacion=1,
            id_empresa=2,
            id_plan_saas=2,
            estado="PENDIENTE",
            id_sesion_checkout="cs_test_pending_recovered",
            tipo_operacion="CONTRATACION",
            id_suscripcion=None,
            id_pago_externo=None,
        )

        self.repo.get_company_by_id = MagicMock(return_value=company)
        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_pending_operations_by_company = MagicMock(return_value=[pending_op])
        self.repo.get_subscription_by_reference = MagicMock(return_value=None)
        self.repo.get_operation_by_session = MagicMock(return_value=pending_op)
        self.repo.list_plan_features = MagicMock(return_value=[])
        self.repo.get_scheduled_plan_change = MagicMock(return_value=None)

        created_sub = create_dummy_subscription(
            id_suscripcion=201,
            id_empresa=2,
            id_plan_saas=2,
            referencia_externa="cs_test_pending_recovered",
        )
        self.repo.create_subscription = MagicMock(return_value=created_sub)

        # Primero no hay suscripción, pero tras la reconciliación sí la hay
        self.repo.get_active_subscription_by_company = MagicMock(side_effect=[None, created_sub, created_sub])

        # Stripe confirma que la sesión está efectivamente pagada (paid) en modo TEST
        stripe_session = {
            "id": "cs_test_pending_recovered",
            "livemode": False,
            "payment_status": "paid",
            "amount_total": 19900,
            "currency": "bob",
            "metadata": {
                "empresa_id": "2",
                "plan_id": "2",
                "operacion": "CONTRATACION",
            },
            "payment_intent": {"id": "pi_test_intent_recovered"},
        }
        self.stripe_mock.retrieve_checkout_session.return_value = stripe_session

        res = self.service.get_current_subscription(company_id=2)

        self.assertTrue(res.tiene_suscripcion_activa)
        self.assertEqual(res.data.id_suscripcion, 201)
        self.assertEqual(res.data.plan_codigo, "BASICO")
        self.assertEqual(pending_op.estado, "COMPLETADA")
        self.assertEqual(pending_op.id_suscripcion, 201)
        self.assertEqual(pending_op.id_pago_externo, "pi_test_intent_recovered")
        self.repo.create_subscription.assert_called_once()

    def test_10_reconcile_pending_operations_leaves_unpaid_operation_pending(self):
        """10. Si Stripe no confirma el pago (unpaid), la operación permanece PENDIENTE y no activa suscripción."""
        company = create_dummy_company(id_empresa=2)
        plan = create_dummy_plan()
        pending_op = SimpleNamespace(
            id_operacion=1,
            id_empresa=2,
            id_plan_saas=2,
            estado="PENDIENTE",
            id_sesion_checkout="cs_test_unpaid_session",
            tipo_operacion="CONTRATACION",
            id_suscripcion=None,
        )

        self.repo.get_company_by_id = MagicMock(return_value=company)
        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_pending_operations_by_company = MagicMock(return_value=[pending_op])
        self.repo.get_subscription_by_reference = MagicMock(return_value=None)
        self.repo.get_operation_by_session = MagicMock(return_value=pending_op)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=None)

        # Stripe indica que NO está pagada
        stripe_session = {
            "id": "cs_test_unpaid_session",
            "livemode": False,
            "payment_status": "unpaid",
            "metadata": {"empresa_id": "2", "plan_id": "2"},
        }
        self.stripe_mock.retrieve_checkout_session.return_value = stripe_session

        res = self.service.get_current_subscription(company_id=2)

        self.assertFalse(res.tiene_suscripcion_activa)
        self.assertIsNone(res.data)
        # La operación NUNCA se marca como COMPLETADA si no está pagada
        self.assertEqual(pending_op.estado, "PENDIENTE")
        self.assertIsNone(pending_op.id_suscripcion)
        self.repo.create_subscription.assert_not_called()

    def test_11_duplicate_contraction_blocked_when_active(self):
        """11. Bloquea contratación duplicada tanto en creación de checkout como en verificación si ya hay suscripción activa."""
        company = create_dummy_company()
        plan = create_dummy_plan()
        active_sub = create_dummy_subscription(
            estado="ACTIVA",
            fecha_fin_periodo=NOW + relativedelta(days=60),
            referencia_externa="cs_test_other_active",
        )

        self.repo.get_company_by_id = MagicMock(return_value=company)
        self.repo.get_plan_by_id = MagicMock(return_value=plan)
        self.repo.get_active_subscription_by_company = MagicMock(return_value=active_sub)

        # Intento de crear sesión de contratación teniendo suscripción activa
        req = CreateCheckoutRequest(id_plan_saas=2, tipo_operacion="CONTRATACION")
        with self.assertRaises(SubscriptionAlreadyActiveError):
            self.service.create_checkout_session(company_id=1, payload=req)

