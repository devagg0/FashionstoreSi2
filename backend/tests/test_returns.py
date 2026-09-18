"""CU24: DB local transaccional y Stripe simulado, sin tocar Supabase."""
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4
from unittest import TestCase
from unittest.mock import MagicMock, patch
from datetime import timedelta
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from app.models.returns import Return, ReturnDetail, Refund
from app.models.payment import Payment
from app.models.inventory_movement import InventoryMovement
from app.repositories.returns import ReturnsRepository
from app.schemas.returns import CancellationRequest, ReturnRequest, ReviewRequest, ProcessRequest
from app.services.returns import ReturnsService
from app.services.payments import PaymentError
from app.services.stripe_service import StripeConnectionError, StripeService
from app.core.database import get_db
from app.routers import returns as routes
from app.routers.client_reservations import require_client
from tests import test_payments as payment_fixtures
from tests.test_staff_sales import asgi_request
from tests.test_stripe_service import configuration

class ReturnTests(TestCase):
    def setUp(self):
        self.fixture = payment_fixtures.PaymentTransactionTests()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.db.autoflush = False
        for model in (Return, ReturnDetail, Refund):
            model.__table__.create(self.fixture.engine)
        self.client = NS(id_usuario=12, rol="CLIENTE")
        self.staff = self.fixture.user
        self.gateway = MagicMock()
        self.service = ReturnsService(self.db, self.gateway)
        self.service.staff.get_employee = self.fixture.service.staff.get_employee
        self.service.staff.branches = self.fixture.service.staff.branches

    def tearDown(self):
        self.fixture.tearDown()

    def complete(self, stripe=False):
        payment = self.fixture.start("EFECTIVO")
        self.fixture.approve(payment.id_pago)
        if stripe:
            p = self.db.get(Payment, payment.id_pago)
            p.medio, p.proveedor, p.entorno = "TARJETA", "STRIPE", "TEST"
            p.referencia_externa = "pi_test"
            self.db.commit()
            self.gateway.retrieve_payment_intent.return_value = dict(
                id="pi_test", livemode=False, status="succeeded", amount_received=2020, latest_charge="ch_test",
                currency="bob", metadata={"id_venta": "1", "id_pago": str(p.id_pago),
                "clave_idempotencia": str(p.clave_idempotencia)})
            self.gateway.create_refund.return_value = dict(id="re_test", charge="ch_test",
                payment_intent="pi_test", amount=1010, currency="bob", status="succeeded")
            self.gateway.retrieve_charge.return_value = dict(id="ch_test", livemode=False,
                payment_intent="pi_test", paid=True, captured=True, amount=2020, currency="bob", amount_refunded=0)
            self.gateway.list_refunds.return_value = []
        return payment

    def request(self, quantity=1, key=None):
        return self.service.request(self.client, 1,
            ReturnRequest(motivo="Producto", lineas=[dict(id_detalle_venta=1, cantidad=quantity)]), key or uuid4())

    def approve(self, row, quantity=1, amount="10.10"):
        return self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="APROBADA",
            lineas=[dict(id_variante_producto=3, cantidad_reintegrar=quantity, importe_restitucion=amount)]))

    def process(self, row, manual=True):
        return self.service.process(self.staff, row["id_devolucion"],
            ProcessRequest(referencia_manual="REC-1" if manual else None))

    def test_pending_cancellation_releases_hold_without_entry(self):
        self.fixture.digital()
        row = self.service.request(self.client, 1, CancellationRequest(motivo="Cancelar"), uuid4(), True)
        self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="APROBADA"))
        result = self.process(row, False)
        self.assertEqual(result["estado"], "PROCESADA")
        self.assertEqual(self.fixture.sale().estado, "ANULADA")
        self.assertEqual((self.fixture.inventory().stock_actual, self.fixture.inventory().stock_reservado), (20, 3))
        self.assertEqual(self.db.scalars(select(InventoryMovement)).all(), [])
        self.process(row, False)
        self.assertEqual(self.fixture.inventory().stock_reservado, 3)

    def test_partial_manual_return_and_double_process(self):
        self.complete()
        row = self.request()
        self.approve(row)
        result = self.process(row)
        self.assertEqual(result["estado"], "PROCESADA")
        self.assertEqual(result["reembolsos"][0]["monto"], Decimal("10.10"))
        self.assertEqual(self.fixture.inventory().stock_actual, 19)
        self.process(row)
        self.assertEqual(self.fixture.inventory().stock_actual, 19)
        self.assertEqual(len(self.db.scalars(select(Refund)).all()), 1)

    def test_cancellation_closes_stripe_intent_before_annulling(self):
        payment = self.fixture.start("TARJETA")
        p = self.db.get(Payment, payment.id_pago)
        p.referencia_externa = "pi_test"
        self.db.commit()
        intent = dict(id="pi_test", livemode=False, amount=2020, currency="bob",
            metadata={"id_venta": "1", "id_pago": str(p.id_pago), "clave_idempotencia": str(p.clave_idempotencia)},
            status="requires_payment_method")
        self.gateway.retrieve_payment_intent.return_value = intent
        self.gateway.cancel_payment_intent.return_value = {**intent, "status": "canceled"}
        row = self.service.request(self.client, 1, CancellationRequest(motivo="X"), uuid4(), True)
        self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="APROBADA"))
        self.process(row, False)
        self.gateway.cancel_payment_intent.assert_called_once()
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "CANCELADO")

    def test_cancellation_uncertain_stripe_keeps_sale_and_stock(self):
        payment = self.fixture.start("TARJETA")
        p = self.db.get(Payment, payment.id_pago)
        p.referencia_externa = "pi_test"
        self.db.commit()
        self.gateway.retrieve_payment_intent.side_effect = StripeConnectionError("uncertain")
        row = self.service.request(self.client, 1, CancellationRequest(motivo="X"), uuid4(), True)
        self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="APROBADA"))
        with self.assertRaises(PaymentError):
            self.process(row, False)
        self.assertEqual(self.fixture.sale().estado, "PENDIENTE")
        self.assertEqual(self.fixture.inventory().stock_actual, 20)
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "PENDIENTE")

    def test_stripe_failed_refund_is_not_recreated(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        self.gateway.create_refund.return_value["status"] = "failed"
        result = self.process(row, False)
        self.assertEqual(result["reembolsos"][0]["estado"], "RECHAZADO")
        with self.assertRaises(PaymentError):
            self.process(row, False)
        self.gateway.create_refund.assert_called_once()
        self.assertEqual(self.fixture.inventory().stock_actual, 18)

    def test_qr_manual_refund(self):
        payment = self.fixture.start("QR")
        self.fixture.approve(payment.id_pago)
        row = self.request()
        self.approve(row)
        result = self.process(row)
        self.assertEqual(result["reembolsos"][0]["estado"], "APROBADO")
        self.assertEqual(self.db.get(Payment, payment.id_pago).medio, "QR")

    def test_cancel_approved_payment_prepares_full_manual_refund(self):
        payment = self.fixture.start("EFECTIVO")
        p = self.db.get(Payment, payment.id_pago)
        p.estado = "APROBADO"
        p.fecha_aprobacion = self.service.now()
        self.db.commit()
        row = self.service.request(self.client, 1, CancellationRequest(motivo="X"), uuid4(), True)
        result = self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="APROBADA"))
        self.assertEqual(result["reembolsos"][0]["monto"], Decimal("20.20"))
        self.process(row)
        self.assertEqual(self.fixture.sale().estado, "ANULADA")
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "REEMBOLSADO")
        self.assertEqual(self.fixture.inventory().stock_actual, 20)

    def test_cancellation_closes_pending_manual_payment(self):
        payment = self.fixture.start("QR")
        row = self.service.request(self.client, 1, CancellationRequest(motivo="X"), uuid4(), True)
        self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="APROBADA"))
        self.process(row, False)
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "CANCELADO")
        self.assertEqual(self.db.get(InventoryMovement, 1).estado, "ANULADO")

    def test_inventory_error_prevents_remote_refund(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        self.db.delete(self.fixture.inventory())
        self.db.commit()
        with self.assertRaises(PaymentError):
            self.process(row, False)
        self.gateway.create_refund.assert_not_called()
        self.assertEqual(self.db.scalar(select(Refund)).estado, "PENDIENTE")

    def test_identical_active_partial_request_rejected(self):
        self.complete()
        self.request()
        with self.assertRaises(PaymentError) as caught:
            self.request()
        self.assertEqual(caught.exception.status_code, 409)

    def test_sequential_partial_returns_total_exactly(self):
        payment = self.complete()
        row = self.request()
        self.approve(row)
        self.process(row)
        row2 = self.request()
        self.approve(row2)
        self.service.process(self.staff, row2["id_devolucion"], ProcessRequest(referencia_manual="REC-2"))
        self.assertEqual(self.fixture.inventory().stock_actual, 20)
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "REEMBOLSADO")

    def test_total_return(self):
        payment = self.complete()
        row = self.request(2)
        self.approve(row, 2, "20.20")
        self.process(row)
        self.assertEqual(self.fixture.inventory().stock_actual, 20)
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "REEMBOLSADO")
        with self.assertRaises(PaymentError):
            self.request()

    def test_invalid_quantities_and_foreign_line(self):
        for quantity in (0, -1, True):
            with self.assertRaises(ValidationError):
                ReturnRequest(motivo="X", lineas=[dict(id_detalle_venta=1, cantidad=quantity)])
        self.complete()
        with self.assertRaises(PaymentError):
            self.request(3)
        with self.assertRaises(PaymentError):
            self.service.request(self.client, 1, ReturnRequest(motivo="X",
                lineas=[dict(id_detalle_venta=99, cantidad=1)]), uuid4())

    def test_other_owner_and_client_review(self):
        self.complete()
        row = self.request()
        other = NS(id_usuario=99, rol="CLIENTE")
        for operation in (lambda: self.service.get_return(other, row["id_devolucion"]),
                          lambda: self.service.request(other, 1, CancellationRequest(motivo="X"), uuid4(), True),
                          lambda: self.service.review(self.client, row["id_devolucion"], ReviewRequest(resultado="RECHAZADA"))):
            with self.assertRaises(PaymentError):
                operation()

    def test_duplicate_and_idempotency_payload(self):
        self.complete()
        key = uuid4()
        row = self.request(2, key)
        self.assertEqual(self.request(2, key)["id_devolucion"], row["id_devolucion"])
        with self.assertRaises(PaymentError):
            self.request(2)
        with self.assertRaises(PaymentError):
            self.request(1, key)

    def test_reject_releases_return_quantity(self):
        self.complete()
        row = self.request(2)
        result = self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="RECHAZADA"))
        self.assertEqual(result["estado"], "RECHAZADA")
        self.request(2)
        with self.assertRaises(PaymentError):
            self.process(row)

    def test_over_refund_and_reintegrate_blocked(self):
        self.complete()
        row = self.request()
        for quantity, amount in ((2, "10.10"), (1, "11.00")):
            with self.assertRaises(PaymentError):
                self.approve(row, quantity, amount)
        self.assertEqual(self.db.get(Return, row["id_devolucion"]).estado, "SOLICITADA")

    def test_manual_receipt_required_and_zero_reintegrate(self):
        self.complete()
        row = self.request()
        self.approve(row, 0)
        with self.assertRaises(PaymentError):
            self.process(row, False)
        self.process(row)
        self.assertEqual(self.fixture.inventory().stock_actual, 18)
        self.assertIsNone(self.db.get(Return, row["id_devolucion"]).id_movimiento_inventario)

    def test_stripe_refund_test_and_double_refund(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        self.process(row, False)
        self.process(row, False)
        self.gateway.create_refund.assert_called_once()
        self.assertEqual(self.fixture.inventory().stock_actual, 19)

    def test_stripe_timeout_persists_same_refund_key(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        self.gateway.create_refund.side_effect = StripeConnectionError("uncertain")
        with self.assertRaises(PaymentError):
            self.process(row, False)
        refund = self.db.scalar(select(Refund))
        key = refund.clave_idempotencia
        self.assertEqual(refund.estado, "PENDIENTE")
        self.assertEqual(self.fixture.inventory().stock_actual, 18)
        self.gateway.create_refund.side_effect = None
        self.process(row, False)
        self.assertEqual([c.kwargs["key"] for c in self.gateway.create_refund.call_args_list], [key, key])

    def test_rollback_after_stripe_success_reuses_persisted_key(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        with patch.object(self.db, "commit", side_effect=RuntimeError("failure")):
            with self.assertRaises(PaymentError):
                self.process(row, False)
        self.assertEqual(self.fixture.inventory().stock_actual, 18)
        self.assertEqual(self.db.get(Return, row["id_devolucion"]).estado, "APROBADA")
        self.process(row, False)
        keys = [c.kwargs["key"] for c in self.gateway.create_refund.call_args_list]
        self.assertEqual(keys[0], keys[1])

    def test_stripe_pending_then_sync_by_reference(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        self.gateway.create_refund.return_value["status"] = "pending"
        result = self.process(row, False)
        self.assertEqual(result["estado"], "APROBADA")
        self.assertEqual(self.fixture.inventory().stock_actual, 18)
        self.gateway.retrieve_refund.return_value = {**self.gateway.create_refund.return_value, "status": "succeeded"}
        self.process(row, False)
        self.gateway.create_refund.assert_called_once()
        self.assertEqual(self.fixture.inventory().stock_actual, 19)

    def test_stripe_live_or_wrong_amount_rolls_back(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        for changes in (dict(amount=999), dict(currency="usd"), dict(payment_intent="pi_other")):
            original = dict(self.gateway.create_refund.return_value)
            self.gateway.create_refund.return_value.update(changes)
            with self.assertRaises(PaymentError):
                self.process(row, False)
            self.gateway.create_refund.return_value = original
            self.assertEqual(self.fixture.inventory().stock_actual, 18)

    def test_stale_stripe_refund_not_recreated(self):
        self.complete(True)
        row = self.request()
        self.approve(row)
        self.db.scalar(select(Refund)).created_at -= timedelta(hours=24)
        self.db.commit()
        with self.assertRaises(PaymentError):
            self.process(row, False)
        self.gateway.create_refund.assert_not_called()

    def test_cancellation_duplicate_and_completed_blocked(self):
        payload = CancellationRequest(motivo="X")
        self.service.request(self.client, 1, payload, uuid4(), True)
        with self.assertRaises(PaymentError):
            self.service.request(self.client, 1, payload, uuid4(), True)
        self.complete()
        with self.assertRaises(PaymentError):
            self.service.request(self.client, 1, payload, uuid4(), True)

    def test_branch_and_self_resolution_security(self):
        self.complete()
        row = self.request()
        self.service.staff.branches.return_value = []
        with self.assertRaises(PaymentError):
            self.approve(row)
        self.service.staff.branches.return_value = [dict(id_sucursal=2, id_empleado_sucursal=8)]
        own_staff = NS(id_usuario=12, rol="CAJERO")
        with self.assertRaises(PaymentError):
            self.service.review(own_staff, row["id_devolucion"], ReviewRequest(resultado="RECHAZADA"))

    def test_api_and_authentication(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: self.db
        for method, path, payload in (("POST", "/api/client/purchases/1/cancellation", {"motivo": "X"}),
                ("GET", "/api/client/returns/1", None), ("GET", "/api/staff/returns", None),
                ("POST", "/api/staff/returns/1/review", {"resultado": "RECHAZADA"}),
                ("POST", "/api/staff/returns/1/process", {})):
            status, _ = asgi_request(app, method, path, payload, [(b"idempotency-key", str(uuid4()).encode())])
            self.assertEqual(status, 401)
        app.dependency_overrides[require_client] = lambda: self.client
        app.dependency_overrides[routes.require_returns_staff] = lambda: self.staff
        with patch.object(routes, "ReturnsService", return_value=self.service):
            status, result = asgi_request(app, "POST", "/api/client/purchases/1/cancellation",
                {"motivo": "X"}, [(b"idempotency-key", str(uuid4()).encode())])
            self.assertEqual(status, 201)
            rid = result["data"]["id_devolucion"]
            status, _ = asgi_request(app, "POST", f"/api/staff/returns/{rid}/review", {"resultado": "APROBADA"})
            self.assertEqual(status, 200)
            status, result = asgi_request(app, "POST", f"/api/staff/returns/{rid}/process", {})
            self.assertEqual(status, 200)
            self.assertEqual(result["data"]["estado"], "PROCESADA")

    def test_reconcile_total_remote_success_after_local_failure_once(self):
        payment = self.complete(True)
        row = self.request(2); self.approve(row, 2, "20.20")
        remote = dict(id="re_existing", charge="ch_test", payment_intent="pi_test", amount=2020,
            currency="bob", status="succeeded", created=1700000000)
        self.gateway.list_refunds.return_value = [remote]
        self.gateway.retrieve_charge.return_value["amount_refunded"] = 2020
        result = self.process(row, False)
        self.assertEqual(result["estado"], "PROCESADA")
        self.assertEqual(result["reembolsos"][0]["referencia_externa"], "re_existing")
        self.assertEqual(result["reembolsos"][0]["estado"], "APROBADO")
        self.assertEqual(self.fixture.inventory().stock_actual, 20)
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "REEMBOLSADO")
        movements = len(self.db.scalars(select(InventoryMovement)).all())
        self.process(row, False)
        self.assertEqual(self.fixture.inventory().stock_actual, 20)
        self.assertEqual(len(self.db.scalars(select(InventoryMovement)).all()), movements)
        self.gateway.create_refund.assert_not_called()

    def test_reconcile_partial_refund_by_metadata_after_local_rollback(self):
        self.complete(True); row = self.request(); self.approve(row)
        local = self.db.scalar(select(Refund))
        remote = dict(id="re_partial", charge="ch_test", payment_intent="pi_test", amount=1010,
            currency="bob", status="succeeded", metadata={"id_reembolso": str(local.id_reembolso),
            "clave_idempotencia": str(local.clave_idempotencia)})
        self.gateway.list_refunds.return_value = [remote]
        self.gateway.retrieve_charge.return_value["amount_refunded"] = 1010
        with patch.object(self.db, "commit", side_effect=RuntimeError("local failure")):
            with self.assertRaises(PaymentError): self.process(row, False)
        self.assertEqual(self.fixture.inventory().stock_actual, 18)
        self.assertEqual(self.db.scalar(select(Refund)).estado, "PENDIENTE")
        self.process(row, False)
        self.assertEqual(self.fixture.inventory().stock_actual, 19)
        self.gateway.create_refund.assert_not_called()

    def test_later_stripe_partial_return_accepts_accounted_refund(self):
        self.complete(True); row = self.request(); self.approve(row); self.process(row, False)
        first = dict(self.gateway.create_refund.return_value)
        self.gateway.list_refunds.return_value = [first]
        self.gateway.retrieve_charge.return_value["amount_refunded"] = 1010
        row2 = self.request(); self.approve(row2)
        self.gateway.create_refund.return_value = {**first, "id": "re_second"}
        self.process(row2, False)
        self.assertEqual(self.fixture.inventory().stock_actual, 20)
        self.assertEqual(self.gateway.create_refund.call_count, 2)

    def test_ambiguous_existing_refund_never_creates_new_one(self):
        self.complete(True); row = self.request(); self.approve(row)
        self.gateway.list_refunds.return_value = [dict(id="re_other", charge="ch_test",
            payment_intent="pi_test", amount=1010, currency="bob", status="succeeded")]
        self.gateway.retrieve_charge.return_value["amount_refunded"] = 1010
        with self.assertRaises(PaymentError): self.process(row, False)
        self.gateway.create_refund.assert_not_called()

    def test_charge_live_response_blocks_refund(self):
        self.complete(True); row = self.request(); self.approve(row)
        self.gateway.retrieve_charge.return_value["livemode"] = True
        with self.assertRaises(PaymentError): self.process(row, False)
        self.gateway.create_refund.assert_not_called()

    def test_original_payment_exposed_without_stripe_reference(self):
        payment = self.complete(True)
        row = self.request()
        data = self.service.get_return(self.staff, row["id_devolucion"], True)
        self.assertEqual(data["pago"]["id_pago"], payment.id_pago)
        self.assertEqual(data["pago"]["medio"], "TARJETA")
        self.assertEqual(data["pago"]["proveedor"], "STRIPE")
        self.assertEqual(data["pago"]["entorno"], "TEST")
        self.assertEqual(set(data["pago"]), {"id_pago", "medio", "proveedor", "entorno", "estado", "monto", "moneda"})

    def test_real_stripe_sdk_objects_checkout_intent_and_refund(self):
        from stripe import PaymentIntent, Refund as StripeRefund
        from stripe.checkout import Session as CheckoutSession
        payment = self.complete(True)
        p = self.db.get(Payment, payment.id_pago)
        p.referencia_externa = "cs_test_original"
        self.db.commit()
        self.gateway.retrieve_payment_intent.return_value = PaymentIntent.construct_from(
            self.gateway.retrieve_payment_intent.return_value, "sk_test_fixture")
        self.gateway.retrieve_checkout_session.return_value = CheckoutSession.construct_from(dict(
            id="cs_test_original", livemode=False, mode="payment", object="checkout.session",
            client_reference_id="1", amount_total=2020, currency="bob", status="complete", payment_status="paid",
            metadata={"id_venta": "1", "id_pago": str(p.id_pago), "clave_idempotencia": str(p.clave_idempotencia)},
            payment_intent=self.gateway.retrieve_payment_intent.return_value.to_dict()), "sk_test_fixture")
        self.gateway.create_refund.return_value = StripeRefund.construct_from(
            self.gateway.create_refund.return_value, "sk_test_fixture")
        row = self.request(); self.approve(row)
        result = self.process(row, False)
        self.assertEqual(result["estado"], "PROCESADA")
        self.assertEqual(self.gateway.create_refund.call_args.kwargs["payment_intent"], "pi_test")

    def test_missing_approved_payment_is_controlled(self):
        self.complete()
        row = self.request(); self.approve(row)
        p = self.db.scalar(select(Payment)); p.estado = "RECHAZADO"; self.db.commit()
        with self.assertRaises(PaymentError) as caught:
            self.process(row)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("No existe pago aprobado", str(caught.exception))
        self.assertEqual(self.db.get(Return, row["id_devolucion"]).estado, "APROBADA")

    def test_manual_reference_cannot_switch_stripe_payment(self):
        self.complete(True)
        row = self.request(); self.approve(row)
        with self.assertRaises(PaymentError) as caught:
            self.process(row, True)
        self.assertEqual(caught.exception.status_code, 422)
        self.gateway.create_refund.assert_not_called()
        self.assertEqual(self.db.scalar(select(Payment)).medio, "TARJETA")

    def test_manual_original_payment_metadata(self):
        for method in ("QR", "EFECTIVO"):
            if method == "QR":
                self.complete()
            p = self.db.scalar(select(Payment)); p.medio = method; self.db.commit()
            row = self.request()
            data = self.service.get_return(self.staff, row["id_devolucion"], True)
            self.assertEqual(data["pago"]["medio"], method)
            self.assertEqual(data["pago"]["proveedor"], "MANUAL")
            self.service.review(self.staff, row["id_devolucion"], ReviewRequest(resultado="RECHAZADA"))


class ReturnContractTests(TestCase):
    def test_process_does_not_accept_frontend_payment_override(self):
        for field in ("medio", "proveedor", "entorno", "id_pago"):
            with self.assertRaises(ValidationError):
                ProcessRequest(**{field: "QR"})

    def test_for_update(self):
        db = MagicMock()
        ReturnsRepository(db).lock(1)
        self.assertIn("FOR UPDATE", str(db.scalar.call_args.args[0].compile(dialect=postgresql.dialect())))

    @patch("app.services.stripe_service.StripeClient")
    def test_stripe_adapter_key(self, factory):
        gateway = StripeService(configuration())
        key = uuid4()
        gateway.create_refund(payment_intent="pi_test", amount=1010, key=key)
        kwargs = factory.return_value.v1.refunds.create.call_args.kwargs
        self.assertEqual(kwargs["params"]["amount"], 1010)
        self.assertEqual(kwargs["options"]["idempotency_key"], f"fashionstore-cu24-refund-{key}")
