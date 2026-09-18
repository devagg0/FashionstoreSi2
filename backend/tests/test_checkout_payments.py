"""Checkout TEST y QR digital: SQLite local, HTTP/Stripe siempre mockeados."""
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import select
from stripe.checkout import Session as CheckoutSession

from app.core.database import get_db
from app.models.payment import Payment
from app.models.inventory_movement import InventoryMovement
from app.routers import payments as routes
from app.schemas.payments import ManualConfirmationRequest
from app.services.payments import PaymentError, PaymentsService
from app.services.stripe_service import StripeConnectionError, StripeService
from tests import test_payments as payment_tests
from tests.test_staff_sales import asgi_request
from tests.test_stripe_service import configuration


class CheckoutPaymentTests(TestCase):
    setUp = payment_tests.PaymentTransactionTests.setUp
    tearDown = payment_tests.PaymentTransactionTests.tearDown
    sale = payment_tests.PaymentTransactionTests.sale
    inventory = payment_tests.PaymentTransactionTests.inventory
    start = payment_tests.PaymentTransactionTests.start
    digital = payment_tests.PaymentTransactionTests.digital
    reserved = payment_tests.PaymentTransactionTests.reserved
    intent = payment_tests.PaymentTransactionTests.intent
    assert_pending_stock = payment_tests.PaymentTransactionTests.assert_pending_stock

    def session(self, *, paid=False, **overrides):
        payment = self.db.scalar(select(Payment))
        values = dict(id="cs_test_fake_checkout", object="checkout.session", livemode=False,
                      mode="payment", client_reference_id="1", amount_total=2020, currency="bob",
                      metadata=dict(id_venta="1", id_pago=str(payment.id_pago), clave_idempotencia=str(payment.clave_idempotencia)),
                      status="complete" if paid else "open", payment_status="paid" if paid else "unpaid",
                      payment_intent=self.intent("succeeded") if paid else None,
                      url=None if paid else "https://checkout.stripe.com/c/pay/cs_test_fake_checkout")
        values.update(overrides)
        return CheckoutSession.construct_from(values, "fake-unit-key")

    def checkout(self):
        data = self.start("TARJETA")
        self.gateway.create_checkout_session.side_effect = lambda **kwargs: self.session()
        return self.service.checkout_session(self.user, data.id_pago)

    def test_start_card_only_persists_pending_no_remote_intent(self):
        payment = self.start("TARJETA")
        self.assertIsNone(payment.referencia_externa)
        self.assertEqual(self.gateway.mock_calls, [])
        self.assert_pending_stock()

    def test_qr_digital_approved_releases_exact_hold_and_completes_movement(self):
        self.digital()
        payment = self.start("QR")
        with patch("app.services.payments.settings.QR_SIMULATION_RESULT", "APROBADO"):
            result = self.service.confirm_qr(self.user, payment.id_pago)
            replay = self.service.confirm_qr(self.user, payment.id_pago)
        self.assertEqual(result.estado, "APROBADO")
        self.assertEqual(replay.estado, "APROBADO")
        self.assertEqual((result.proveedor, result.entorno), ("MANUAL", "LOCAL"))
        self.assertEqual(self.sale().estado, "COMPLETADA")
        self.assertIsNotNone(self.sale().fecha_completada)
        self.assertFalse(self.sale().stock_comprometido)
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 3))
        self.assertEqual(self.db.scalar(select(InventoryMovement)).estado, "CONFIRMADO")
        self.assertEqual(self.gateway.mock_calls, [])

    def test_qr_digital_rejected_preserves_stock_and_allows_new_key(self):
        self.digital()
        payment = self.start("QR")
        with patch("app.services.payments.settings.QR_SIMULATION_RESULT", "RECHAZADO"):
            result = self.service.confirm_qr(self.user, payment.id_pago)
        self.assertEqual(result.estado, "RECHAZADO")
        self.assert_pending_stock()
        self.assertTrue(self.sale().stock_comprometido)
        self.assertIsNone(self.db.scalar(select(InventoryMovement)))
        next_payment = self.start("QR", key=uuid4())
        self.assertNotEqual(next_payment.id_pago, payment.id_pago)

    def test_client_cannot_send_manual_approval_for_digital_qr(self):
        self.digital()
        payment = self.start("QR")
        with self.assertRaises(PaymentError) as caught:
            self.service.confirm_manual(self.user, payment.id_pago, ManualConfirmationRequest(resultado="APROBADO"))
        self.assertEqual(caught.exception.status_code, 403)
        self.assert_pending_stock()

    def test_qr_wrong_owner_or_card_payment_denied(self):
        self.digital()
        payment = self.start("QR")
        with self.assertRaises(PaymentError):
            self.service.confirm_qr(NS(id_usuario=99, rol="CLIENTE"), payment.id_pago)
        self.assert_pending_stock()

    def test_qr_presencial_still_supported(self):
        data = self.start("QR")
        with patch("app.services.payments.settings.QR_SIMULATION_RESULT", "APROBADO"):
            result = self.service.confirm_qr(self.user, data.id_pago)
        self.assertEqual(result.estado, "APROBADO")
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 5))

    def test_checkout_created_and_reference_persisted_without_charge(self):
        result = self.checkout()
        self.assertEqual(result.session_id, "cs_test_fake_checkout")
        self.assertEqual(result.url, "https://checkout.stripe.com/c/pay/cs_test_fake_checkout")
        self.assertEqual(self.db.get(Payment, result.payment.id_pago).referencia_externa, result.session_id)
        self.assertEqual(result.payment.estado, "PENDIENTE")
        self.assert_pending_stock()

    def test_server_return_urls_digital_and_presencial(self):
        for digital in (False, True):
            with self.subTest(digital=digital):
                if digital:
                    self.digital()
                payment = self.db.scalar(select(Payment)) or self.db.get(Payment, self.start("TARJETA").id_pago)
                with patch("app.services.payments.settings.STRIPE_CHECKOUT_RETURN_BASE_URL", "https://fashion.example"):
                    success, cancel = self.service._return_urls(self.sale(), payment)
                path = "/compra/1/pago" if digital else "/staff/ventas/1/pago"
                self.assertEqual(success, f"https://fashion.example{path}?payment_id={payment.id_pago}&checkout=success&session_id={{CHECKOUT_SESSION_ID}}")
                self.assertEqual(cancel, f"https://fashion.example{path}?payment_id={payment.id_pago}&checkout=cancel")

    def test_checkout_only_paid_complete_session_approves_digital(self):
        self.digital()
        result = self.checkout()
        self.gateway.retrieve_checkout_session.return_value = self.session(paid=True)
        approved = self.service.stripe_sync(self.user, result.payment.id_pago)
        self.assertEqual(approved.estado, "APROBADO")
        self.assertEqual(self.sale().estado, "COMPLETADA")
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 3))
        self.assertEqual(approved.referencia_externa, "cs_test_fake_checkout")

    def test_checkout_unpaid_or_no_payment_required_does_not_complete(self):
        result = self.checkout()
        for state in (dict(), dict(status="complete"), dict(status="complete", payment_status="no_payment_required")):
            self.gateway.retrieve_checkout_session.return_value = self.session(**state)
            self.assertEqual(self.service.stripe_sync(self.user, result.payment.id_pago).estado, "PENDIENTE")
            self.assert_pending_stock()

    def test_checkout_bad_amount_currency_metadata_mode_live_id_rejected(self):
        result = self.checkout()
        for changes in (dict(amount_total=1), dict(currency="usd"), dict(metadata={}),
                        dict(metadata={"id_pago": "999"}), dict(mode="subscription"),
                        dict(livemode=True), dict(id="cs_live_fake"), dict(id="cs_test_other"),
                        dict(client_reference_id="99"), dict(livemode=None), dict(status="open")):
            with self.subTest(changes=changes):
                self.gateway.retrieve_checkout_session.return_value = self.session(paid=True, **changes)
                with self.assertRaises(PaymentError) as caught:
                    self.service.stripe_sync(self.user, result.payment.id_pago)
                self.assertEqual(caught.exception.status_code, 409)
                self.assert_pending_stock()

    def test_paid_session_requires_matching_succeeded_test_intent(self):
        result = self.checkout()
        for intent in (None, self.intent("processing"), self.intent("succeeded", livemode=True),
                       self.intent("succeeded", amount_received=1), self.intent("succeeded", metadata={}),
                       self.intent("succeeded", currency="usd")):
            with self.subTest(intent_type=type(intent).__name__):
                self.gateway.retrieve_checkout_session.return_value = self.session(paid=True, payment_intent=intent)
                with self.assertRaises(PaymentError):
                    self.service.stripe_sync(self.user, result.payment.id_pago)
                self.assert_pending_stock()

    def test_idempotent_session_reuse_does_not_create_second_checkout(self):
        first = self.checkout()
        self.gateway.retrieve_checkout_session.return_value = self.session()
        second = self.service.checkout_session(self.user, first.payment.id_pago)
        self.assertEqual(first.session_id, second.session_id)
        self.gateway.create_checkout_session.assert_called_once()
        self.assert_pending_stock()

    def test_double_sync_no_second_stock_discount_or_remote_charge(self):
        result = self.checkout()
        self.gateway.retrieve_checkout_session.return_value = self.session(paid=True)
        first = self.service.stripe_sync(self.user, result.payment.id_pago)
        second = self.service.stripe_sync(self.user, result.payment.id_pago)
        self.assertEqual((first.estado, second.estado), ("APROBADO", "APROBADO"))
        self.assertEqual(self.inventory().stock_actual, 18)
        self.gateway.retrieve_checkout_session.assert_called_once()
        self.gateway.confirm_test_payment_intent.assert_not_called()
        with self.assertRaises(PaymentError):
            self.start("TARJETA", key=uuid4())

    def test_checkout_already_paid_cannot_create_again(self):
        result = self.checkout()
        self.gateway.retrieve_checkout_session.return_value = self.session(paid=True)
        self.service.stripe_sync(self.user, result.payment.id_pago)
        with self.assertRaises(PaymentError):
            self.service.checkout_session(self.user, result.payment.id_pago)
        self.gateway.create_checkout_session.assert_called_once()

    def test_checkout_unknown_result_blocks_new_attempt_and_uses_same_key(self):
        payment = self.start("TARJETA")
        self.gateway.create_checkout_session.side_effect = StripeConnectionError("uncertain")
        with self.assertRaises(PaymentError):
            self.service.checkout_session(self.user, payment.id_pago)
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "PENDIENTE")
        with self.assertRaises(PaymentError):
            self.start("TARJETA", key=uuid4())
        self.gateway.create_checkout_session.side_effect = lambda **kwargs: self.session()
        result = self.service.checkout_session(self.user, payment.id_pago)
        self.assertEqual(result.payment.id_pago, payment.id_pago)
        keys = [call.kwargs["key"] for call in self.gateway.create_checkout_session.call_args_list]
        self.assertEqual(keys, [self.key, self.key])

    def test_checkout_reference_commit_failure_retries_same_session_key(self):
        payment = self.start("TARJETA")
        self.gateway.create_checkout_session.side_effect = lambda **kwargs: self.session()
        with patch.object(self.db, "commit", side_effect=RuntimeError("failure")):
            with self.assertRaises(PaymentError):
                self.service.checkout_session(self.user, payment.id_pago)
        self.assertIsNone(self.db.get(Payment, payment.id_pago).referencia_externa)
        result = self.service.checkout_session(self.user, payment.id_pago)
        self.assertEqual(result.session_id, "cs_test_fake_checkout")
        self.assertEqual([call.kwargs["key"] for call in self.gateway.create_checkout_session.call_args_list], [self.key, self.key])

    def test_checkout_paid_local_commit_failure_reconciles_without_double_discount(self):
        self.digital()
        result = self.checkout()
        self.gateway.retrieve_checkout_session.return_value = self.session(paid=True)
        with patch.object(self.db, "commit", side_effect=RuntimeError("failure")):
            with self.assertRaises(PaymentError):
                self.service.stripe_sync(self.user, result.payment.id_pago)
        self.assert_pending_stock()
        self.assertIsNone(self.db.scalar(select(InventoryMovement)))
        approved = self.service.stripe_sync(self.user, result.payment.id_pago)
        self.assertEqual(approved.estado, "APROBADO")
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 3))

    def test_checkout_only_accepts_card_and_test_payment(self):
        payment = self.start("QR")
        with self.assertRaises(PaymentError):
            self.service.checkout_session(self.user, payment.id_pago)
        self.assertEqual(self.gateway.mock_calls, [])

    def test_expired_session_is_terminal_without_discounting_stock(self):
        result = self.checkout()
        self.gateway.retrieve_checkout_session.return_value = self.session(status="expired", url=None)
        self.assertEqual(self.service.stripe_sync(self.user, result.payment.id_pago).estado, "EXPIRADO")
        self.assert_pending_stock()

    def test_expired_digital_sale_closes_unpaid_session_before_terminal(self):
        self.digital()
        result = self.checkout()
        self.sale().fecha_expiracion_pago = PaymentsService.now() - timedelta(seconds=1)
        self.db.commit()
        self.gateway.retrieve_checkout_session.return_value = self.session()
        self.gateway.expire_checkout_session.return_value = self.session(status="expired", url=None)
        self.assertEqual(self.service.stripe_sync(self.user, result.payment.id_pago).estado, "EXPIRADO")
        self.gateway.expire_checkout_session.assert_called_once()
        self.assert_pending_stock()

    def test_bad_checkout_url_rejected(self):
        payment = self.start("TARJETA")
        for url in ("http://checkout.stripe.com/pay", "https://example.com/pay", "https://checkout.stripe.com@evil.example/pay"):
            self.gateway.create_checkout_session.return_value = self.session(url=url)
            with self.assertRaises(PaymentError):
                self.service.checkout_session(self.user, payment.id_pago)
            self.assertIsNone(self.db.get(Payment, payment.id_pago).referencia_externa)

    def test_checkout_legacy_intent_closed_before_new_session(self):
        payment = self.start("TARJETA")
        self.db.get(Payment, payment.id_pago).referencia_externa = "pi_fake_test"
        self.db.commit()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        self.gateway.cancel_payment_intent.return_value = self.intent("canceled")
        self.gateway.create_checkout_session.side_effect = lambda **kwargs: self.session()
        result = self.service.checkout_session(self.user, payment.id_pago)
        self.assertEqual(result.session_id, "cs_test_fake_checkout")
        methods = [call[0] for call in self.gateway.mock_calls]
        self.assertLess(methods.index("cancel_payment_intent"), methods.index("create_checkout_session"))

    def test_legacy_already_paid_or_processing_cannot_open_second_checkout(self):
        payment = self.start("TARJETA")
        self.db.get(Payment, payment.id_pago).referencia_externa = "pi_fake_test"
        self.db.commit()
        for state in ("succeeded", "processing", "requires_action", "requires_capture"):
            self.gateway.retrieve_payment_intent.return_value = self.intent(state)
            with self.assertRaises(PaymentError):
                self.service.checkout_session(self.user, payment.id_pago)
        self.gateway.create_checkout_session.assert_not_called()

    def test_public_checkout_response_and_authoritative_sync(self):
        self.digital()
        payment = self.start("TARJETA")
        self.gateway.create_checkout_session.side_effect = lambda **kwargs: self.session()
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[routes.require_payment_user] = lambda: self.user
        with patch.object(routes, "PaymentsService", return_value=self.service):
            status, body = asgi_request(app, "POST", f"/api/payments/{payment.id_pago}/stripe/checkout-session", {})
            self.assertEqual(status, 200)
            self.assertEqual(body["data"]["session_id"], "cs_test_fake_checkout")
            self.assertTrue(body["data"]["url"].startswith("https://checkout.stripe.com/"))
            self.assertEqual(body["data"]["payment"]["estado"], "PENDIENTE")
            self.gateway.retrieve_checkout_session.return_value = self.session(
                status="complete", payment_status="paid", payment_intent=self.intent("succeeded"))
            status, body = asgi_request(app, "POST", f"/api/payments/{payment.id_pago}/stripe/sync", {})
            self.assertEqual(status, 200)
            self.assertEqual(body["data"]["estado"], "APROBADO")
            self.assertEqual(body["data"]["estado_venta"], "COMPLETADA")

    def test_public_endpoints_forbid_client_approval_urls_and_fixture_route(self):
        self.digital()
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[routes.require_payment_user] = lambda: self.user
        for route in ("qr/confirm", "stripe/checkout-session", "stripe/sync"):
            for payload in ({"estado": "APROBADO"}, {"resultado": "APROBADO"},
                            {"success_url": "https://evil.example"}, {"session_id": "cs_test_other"}):
                status, _ = asgi_request(app, "POST", f"/api/payments/1/{route}", payload)
                self.assertEqual(status, 422)
        status, _ = asgi_request(app, "POST", "/api/payments/1/stripe/confirm-test", {"payment_method": "pm_card_visa"})
        self.assertEqual(status, 404)


class CheckoutAdapterAndConfigTests(TestCase):
    @patch("app.services.stripe_service.StripeClient")
    def test_sdk_checkout_exact_amount_urls_metadata_and_idempotency(self, factory):
        gateway = StripeService(configuration())
        key = uuid4()
        gateway.create_checkout_session(amount=2020, currency="BOB", sale_id=1, payment_id=2,
                                        key=key, success_url="https://fashion.example/success", cancel_url="https://fashion.example/cancel")
        kwargs = factory.return_value.v1.checkout.sessions.create.call_args.kwargs
        params = kwargs["params"]
        self.assertEqual(params["mode"], "payment")
        self.assertEqual(params["payment_method_types"], ["card"])
        self.assertEqual(params["line_items"][0]["price_data"]["unit_amount"], 2020)
        self.assertEqual(params["line_items"][0]["price_data"]["currency"], "bob")
        self.assertEqual(params["success_url"], "https://fashion.example/success")
        self.assertEqual(params["cancel_url"], "https://fashion.example/cancel")
        self.assertEqual(params["metadata"], params["payment_intent_data"]["metadata"])
        self.assertEqual(params["metadata"]["id_pago"], "2")
        self.assertEqual(kwargs["options"]["idempotency_key"], f"fashionstore-cu22-checkout-{key}")

    @patch("app.services.stripe_service.StripeClient")
    def test_sdk_retrieve_expands_payment_intent(self, factory):
        StripeService(configuration()).retrieve_checkout_session("cs_test_fake")
        factory.return_value.v1.checkout.sessions.retrieve.assert_called_once_with(
            "cs_test_fake", params={"expand": ["payment_intent"]})

    def test_return_origin_rejects_insecure_nonlocal_or_credentials(self):
        for origin in ("http://fashion.example", "https://user:password@fashion.example", "https://fashion.example?x=1",
                       "https://fashion.example/#fragment", "https://fashion.example/other", "javascript:fake", "https://fashion.example:bad"):
            with self.subTest(origin=origin), self.assertRaises(ValidationError):
                configuration(STRIPE_CHECKOUT_RETURN_BASE_URL=origin)
        self.assertEqual(configuration(STRIPE_CHECKOUT_RETURN_BASE_URL="https://fashion.example/").STRIPE_CHECKOUT_RETURN_BASE_URL,
                         "https://fashion.example")

    def test_qr_simulation_result_is_server_configuration(self):
        self.assertEqual(configuration(QR_SIMULATION_RESULT="RECHAZADO").QR_SIMULATION_RESULT, "RECHAZADO")
        with self.assertRaises(ValidationError):
            configuration(QR_SIMULATION_RESULT="free-form")
