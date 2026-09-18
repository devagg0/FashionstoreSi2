"""CU22: transacciones reales en SQLite local; Stripe siempre mockeado."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from stripe import CardError, PaymentIntent, StripeError

import app.models
from app.core.database import get_db
from app.models.branch_inventory import BranchInventory
from app.models.client import Client
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.reservation_detail import ReservationDetail
from app.models.sale import Sale
from app.models.sale_detail import SaleDetail
from app.models.inventory_movement import InventoryMovement
from app.models.inventory_movement_detail import InventoryMovementDetail
from app.repositories.payments import PaymentsRepository
from app.routers import payments as routes
from app.schemas.payments import EmptyPaymentRequest, ManualConfirmationRequest, PaymentStartRequest
from app.services.auth_service import InactiveAccountError, InvalidAccessTokenError
from app.services.payments import PaymentError, PaymentsService
from app.services.stripe_service import StripeConnectionError, StripeService
from tests.test_staff_sales import asgi_request
from tests.test_stripe_service import configuration


class LegacyFixturePaymentsService(PaymentsService):
    """Antiguo flujo de fixtures: disponible exclusivamente en tests mockeados."""
    def _legacy_intent_sync(self, user, payment_id, confirmation=None):
        """Conciliacion de PI anteriores; confirmation solo para tests internos."""
        # Recuperar o materializar la referencia y confirmarla localmente antes
        # de cualquier cobro TEST. Un rollback posterior conserva esa referencia.
        self._transaction(lambda: self._stripe_context_ensure(user, payment_id))
        def operation():
            sale, payment = self._context(user, payment_id)
            if payment.estado != "PENDIENTE":
                return self._data(sale, payment)
            self._pending(sale)
            self._assert_current_payment(sale, payment)
            intent = self.stripe.retrieve_payment_intent(payment.referencia_externa)
            self._validate_intent(sale, payment, intent)
            if confirmation is not None and intent["status"] in {"requires_payment_method", "requires_confirmation"}:
                self._pending(sale, new_charge=True)
                self._stock_context(sale)  # Mantener bloqueos hasta completar el commit.
                if "last_payment_error" not in intent or intent["last_payment_error"] is None:
                    intent = self.stripe.confirm_test_payment_intent(
                        payment.referencia_externa, confirmation.payment_method, payment.clave_idempotencia)
                    return self._apply_intent(sale, payment, intent, attempted=True)
            return self._apply_intent(sale, payment, intent)
        return self._transaction(operation)

    def _stripe_context_ensure(self, user, payment_id):
        sale, payment = self._context(user, payment_id)
        if payment.proveedor != "STRIPE" or payment.entorno != "TEST":
            raise PaymentError(422, "El pago no pertenece a Stripe TEST")
        return self._ensure_intent(user, payment_id)


class FixtureStripeService(StripeService):
    """Adaptador de fixtures exclusivamente para regresion automatizada."""
    def confirm_test_payment_intent(self, reference, payment_method, key):
        if payment_method not in {"pm_card_visa", "pm_card_chargeDeclined"}:
            raise ValueError("Solo se admiten metodos de prueba controlados")
        try:
            return self._client.v1.payment_intents.confirm(
                reference, params={"payment_method": payment_method},
                options={"idempotency_key": f"fashionstore-cu22-confirm-{key}"},
            )
        except CardError:
            # No propagar mensajes ni datos de tarjeta. Consultar estado autoritativo.
            return self.retrieve_payment_intent(reference)
        except StripeError:
            raise StripeConnectionError("Resultado Stripe TEST incierto; consulte el mismo pago") from None



class PaymentTransactionTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        for model in (Client, Reservation, ReservationDetail, Sale, SaleDetail,
                      BranchInventory, InventoryMovement, InventoryMovementDetail, Payment):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.user = NS(id_usuario=11, rol="CAJERO")
        self.key = uuid4()
        self.gateway = MagicMock()
        self.service = LegacyFixturePaymentsService(self.db, stripe_service=self.gateway)
        self.service.staff.get_employee = MagicMock(return_value=NS(id_empleado=5))
        self.service.staff.branches = MagicMock(return_value=[dict(id_sucursal=2, id_empleado_sucursal=8)])
        now = PaymentsService.now() - timedelta(minutes=1)
        self.db.add(Client(id_cliente=7, id_usuario=12))
        self.db.add(Sale(
            id_venta=1, numero_venta="VTA-TEST", id_sucursal=2, id_empleado=5,
            id_cliente=7, id_reserva=None, canal="PRESENCIAL", moneda="BOB",
            estado="PENDIENTE", subtotal=Decimal("20.20"), descuento_total=0,
            total=Decimal("20.20"), stock_comprometido=False,
            fecha_venta=now, created_at=now, updated_at=now,
        ))
        self.db.add(SaleDetail(id_venta=1, id_variante_producto=3, cantidad=2,
                              precio_unitario=Decimal("10.10"), descuento_unitario=0,
                              subtotal_linea=Decimal("20.20")))
        self.db.add(BranchInventory(id_sucursal=2, id_variante_producto=3,
                                    stock_actual=20, stock_reservado=5, stock_minimo=0))
        self.db.add(InventoryMovement(id_movimiento_inventario=1, id_venta=1,
                                     id_sucursal_origen=2, id_sucursal_destino=None,
                                     id_empleado_sucursal=8, tipo_movimiento="VENTA", estado="PENDIENTE"))
        self.db.add(InventoryMovementDetail(id_movimiento_inventario=1, id_variante_producto=3, cantidad=2))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def sale(self):
        return self.db.get(Sale, 1)

    def inventory(self):
        return self.db.scalar(select(BranchInventory))

    def start(self, method="EFECTIVO", key=None):
        return self.service.start(self.user, 1, PaymentStartRequest(medio=method), key or self.key)

    def approve(self, payment_id):
        return self.service.confirm_manual(self.user, payment_id, ManualConfirmationRequest(resultado="APROBADO"))

    def intent(self, status="requires_payment_method", **overrides):
        payment = self.db.scalar(select(Payment))
        values = dict(id="pi_fake_test", object="payment_intent", livemode=False,
                      amount=2020, amount_received=2020 if status == "succeeded" else 0,
                      currency="bob", status=status, last_payment_error=None,
                      metadata=dict(id_venta="1", id_pago=str(payment.id_pago),
                                    clave_idempotencia=str(payment.clave_idempotencia)))
        values.update(overrides)
        return PaymentIntent.construct_from(values, "fake-unit-key")

    def start_card(self):
        self.gateway.create_payment_intent.side_effect = lambda **kw: self.intent()
        return self.start_legacy_card()

    def start_legacy_card(self):
        # Fixtures solo para regresion de pagos PI antiguos, fuera de la API.
        data = self.start("TARJETA")
        return self.service._transaction(lambda: self.service._ensure_intent(self.user, data.id_pago))

    def stripe_confirm(self, payment_id, method="pm_card_visa"):
        return self.service._legacy_intent_sync(self.user, payment_id, NS(payment_method=method))

    def digital(self):
        self.user = NS(id_usuario=12, rol="CLIENTE")
        sale = self.sale()
        sale.canal = "DIGITAL"
        sale.id_empleado = None
        sale.stock_comprometido = True
        sale.fecha_expiracion_pago = PaymentsService.now() + timedelta(minutes=30)
        self.db.delete(self.db.get(InventoryMovementDetail, 1))
        self.db.delete(self.db.get(InventoryMovement, 1))
        self.db.commit()

    def reserved(self):
        now = PaymentsService.now()
        self.db.add(Reservation(id_reserva=9, id_cliente=7, id_sucursal=2, codigo="RES-TEST",
                                estado="ATENDIDA", fecha_atencion_programada=now,
                                fecha_expiracion=now + timedelta(days=1)))
        self.db.add(ReservationDetail(id_reserva=9, id_variante_producto=3, cantidad=4, precio_unitario=Decimal("10.10")))
        self.sale().id_reserva = 9
        # CU20 ya libero 2 de las 4 reservadas: quedan 2 propias + 3 ajenas.
        self.db.commit()

    def assert_pending_stock(self):
        self.assertEqual(self.sale().estado, "PENDIENTE")
        self.assertIsNone(self.sale().fecha_completada)
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (20, 5))

    def test_cash_approved_without_reservation(self):
        result = self.approve(self.start().id_pago)
        self.assertEqual((result.estado, result.proveedor, result.entorno), ("APROBADO", "MANUAL", "LOCAL"))
        self.assertEqual(self.sale().estado, "COMPLETADA")
        self.assertIsNotNone(self.sale().fecha_completada)
        self.assertFalse(self.sale().stock_comprometido)
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 5))
        self.assertEqual(self.db.get(InventoryMovement, 1).estado, "CONFIRMADO")
        self.assertEqual(self.gateway.mock_calls, [])

    def test_qr_approved_controlled_manual(self):
        result = self.approve(self.start("QR").id_pago)
        self.assertEqual((result.estado, result.medio), ("APROBADO", "QR"))
        self.assertEqual(self.inventory().stock_actual, 18)

    def test_presencial_reservation_releases_only_remaining_purchase(self):
        self.reserved()
        self.approve(self.start().id_pago)
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 3))
        self.assertEqual(self.db.get(Reservation, 9).estado, "ATENDIDA")

    def test_manual_rejected_sale_pending_and_retry_new_key(self):
        payment = self.start()
        result = self.service.confirm_manual(self.user, payment.id_pago, ManualConfirmationRequest(resultado="RECHAZADO"))
        self.assertEqual(result.estado, "RECHAZADO")
        self.assert_pending_stock()
        next_payment = self.start(key=uuid4())
        self.assertNotEqual(next_payment.id_pago, payment.id_pago)
        self.approve(next_payment.id_pago)

    def test_paid_sale_new_payment_rejected(self):
        self.approve(self.start().id_pago)
        with self.assertRaises(PaymentError) as caught:
            self.start(key=uuid4())
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.inventory().stock_actual, 18)

    def test_annulled_sale_cannot_be_paid(self):
        self.sale().estado = "ANULADA"
        self.db.commit()
        with self.assertRaises(PaymentError):
            self.start()
        self.assertEqual(self.db.scalars(select(Payment)).all(), [])

    def test_double_start_same_key_returns_same_payment(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first.id_pago, second.id_pago)
        self.assertEqual(len(self.db.scalars(select(Payment)).all()), 1)
        self.assert_pending_stock()

    def test_double_start_different_key_blocked(self):
        self.start()
        with self.assertRaises(PaymentError):
            self.start(key=uuid4())
        self.assert_pending_stock()

    def test_key_cannot_change_method(self):
        self.start()
        with self.assertRaises(PaymentError):
            self.start("QR")

    def test_double_confirmation_and_start_replay_no_second_discount(self):
        payment = self.start()
        self.approve(payment.id_pago)
        self.approve(payment.id_pago)
        self.assertEqual(self.start().estado, "APROBADO")
        self.assertEqual(self.inventory().stock_actual, 18)

    def test_conflicting_manual_result_rejected(self):
        payment = self.start()
        self.approve(payment.id_pago)
        with self.assertRaises(PaymentError):
            self.service.confirm_manual(self.user, payment.id_pago, ManualConfirmationRequest(resultado="RECHAZADO"))

    def test_stock_no_reservation_cannot_consume_other_holds(self):
        self.inventory().stock_actual = 6
        self.db.commit()
        with self.assertRaises(PaymentError):
            self.start()
        self.assertEqual(self.db.scalars(select(Payment)).all(), [])

    def test_insufficient_stock_at_confirmation_preserves_pending(self):
        payment = self.start()
        self.inventory().stock_actual = 6
        self.db.commit()
        with self.assertRaises(PaymentError):
            self.approve(payment.id_pago)
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "PENDIENTE")
        self.assertEqual(self.sale().estado, "PENDIENTE")

    def test_manual_commit_failure_rolls_back_all(self):
        payment = self.start()
        with patch.object(self.db, "commit", side_effect=RuntimeError("commit failure")):
            with self.assertRaises(PaymentError):
                self.approve(payment.id_pago)
        self.assert_pending_stock()
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "PENDIENTE")
        self.assertEqual(self.db.get(InventoryMovement, 1).estado, "PENDIENTE")

    def test_movement_mismatch_rejected(self):
        self.db.get(InventoryMovementDetail, 1).cantidad = 1
        self.db.commit()
        with self.assertRaises(PaymentError):
            self.start()

    def test_wrong_cashier_branch_denied(self):
        self.service.staff.branches.return_value = [dict(id_sucursal=99)]
        with self.assertRaises(PaymentError) as caught:
            self.start()
        self.assertEqual(caught.exception.status_code, 403)

    def test_inactive_assignment_denied(self):
        self.service.staff.branches.return_value = []
        with self.assertRaises(PaymentError):
            self.start()

    def test_client_cannot_access_presencial(self):
        self.user = NS(id_usuario=12, rol="CLIENTE")
        with self.assertRaises(PaymentError):
            self.start()

    def test_wrong_role_denied(self):
        self.user.rol = "ADMINISTRADOR"
        with self.assertRaises(PaymentError):
            self.start()

    def test_payment_intent_created_no_stock_change(self):
        result = self.start_card()
        self.assertEqual((result.estado, result.proveedor, result.entorno, result.referencia_externa),
                         ("PENDIENTE", "STRIPE", "TEST", "pi_fake_test"))
        self.gateway.create_payment_intent.assert_called_once_with(
            amount=2020, currency="BOB", sale_id=1, payment_id=result.id_pago, key=self.key)
        self.assert_pending_stock()

    def test_card_approved_no_reservation(self):
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        self.gateway.confirm_test_payment_intent.return_value = self.intent("succeeded")
        result = self.stripe_confirm(payment.id_pago)
        self.assertEqual(result.estado, "APROBADO")
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 5))

    def test_card_rejected_closed_before_new_attempt(self):
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        self.gateway.confirm_test_payment_intent.return_value = self.intent(last_payment_error={"code": "card_declined"})
        self.gateway.cancel_payment_intent.return_value = self.intent("canceled")
        result = self.stripe_confirm(payment.id_pago, "pm_card_chargeDeclined")
        self.assertEqual(result.estado, "RECHAZADO")
        self.gateway.cancel_payment_intent.assert_called_once()
        self.assert_pending_stock()
        self.start(key=uuid4())

    def test_card_cancel_failure_keeps_active_pending(self):
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        self.gateway.confirm_test_payment_intent.return_value = self.intent(last_payment_error={"code": "card_declined"})
        self.gateway.cancel_payment_intent.side_effect = StripeConnectionError("uncertain")
        with self.assertRaises(PaymentError):
            self.stripe_confirm(payment.id_pago, "pm_card_chargeDeclined")
        self.assertEqual(self.db.get(Payment, payment.id_pago).estado, "PENDIENTE")
        with self.assertRaises(PaymentError):
            self.start(key=uuid4())
        self.assert_pending_stock()

    def test_stripe_creation_timeout_persists_attempt_and_reuses_key(self):
        self.gateway.create_payment_intent.side_effect = StripeConnectionError("uncertain")
        with self.assertRaises(PaymentError) as caught:
            self.start_legacy_card()
        self.assertEqual(caught.exception.status_code, 503)
        payment = self.db.scalar(select(Payment))
        self.assertEqual(payment.estado, "PENDIENTE")
        self.gateway.create_payment_intent.side_effect = lambda **kw: self.intent()
        result = self.start_legacy_card()
        self.assertEqual(result.id_pago, payment.id_pago)
        keys = [c.kwargs["key"] for c in self.gateway.create_payment_intent.call_args_list]
        self.assertEqual(keys, [self.key, self.key])

    def test_stale_uncertain_creation_not_recreated(self):
        self.gateway.create_payment_intent.side_effect = StripeConnectionError("uncertain")
        with self.assertRaises(PaymentError):
            self.start_legacy_card()
        self.db.scalar(select(Payment)).created_at -= timedelta(hours=24)
        self.db.commit()
        with self.assertRaises(PaymentError) as caught:
            self.start_legacy_card()
        self.assertEqual(caught.exception.status_code, 409)
        self.gateway.create_payment_intent.assert_called_once()

    def test_stripe_confirmation_timeout_reconciles_without_second_charge(self):
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        self.gateway.confirm_test_payment_intent.side_effect = StripeConnectionError("uncertain")
        with self.assertRaises(PaymentError):
            self.stripe_confirm(payment.id_pago)
        self.assert_pending_stock()
        self.gateway.retrieve_payment_intent.return_value = self.intent("succeeded")
        result = self.service.stripe_sync(self.user, payment.id_pago)
        self.assertEqual(result.estado, "APROBADO")
        self.stripe_confirm(payment.id_pago)
        self.gateway.confirm_test_payment_intent.assert_called_once()
        self.assertEqual(self.inventory().stock_actual, 18)

    def test_stripe_approved_local_rollback_reconciles(self):
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        self.gateway.confirm_test_payment_intent.return_value = self.intent("succeeded")
        commit = self.db.commit
        calls = []

        def fail_final_commit():
            calls.append(True)
            if len(calls) == 2:
                raise RuntimeError("local commit failure after Stripe success")
            return commit()

        with patch.object(self.db, "commit", side_effect=fail_final_commit):
            with self.assertRaises(PaymentError):
                self.stripe_confirm(payment.id_pago)
        self.assert_pending_stock()
        self.assertEqual(self.db.get(Payment, payment.id_pago).referencia_externa, "pi_fake_test")
        self.gateway.retrieve_payment_intent.return_value = self.intent("succeeded")
        result = self.service.stripe_sync(self.user, payment.id_pago)
        self.assertEqual(result.estado, "APROBADO")
        self.gateway.confirm_test_payment_intent.assert_called_once()

    def test_stripe_live_response_blocked(self):
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent("succeeded", livemode=True)
        with self.assertRaises(PaymentError):
            self.service.stripe_sync(self.user, payment.id_pago)
        self.assert_pending_stock()

    def test_stripe_amount_currency_reference_metadata_must_match(self):
        payment = self.start_card()
        for changes in (dict(amount=1), dict(currency="usd"), dict(id="pi_other"),
                        dict(metadata={"id_pago": "99"}), dict(amount_received=1)):
            with self.subTest(changes=changes):
                self.gateway.retrieve_payment_intent.return_value = self.intent("succeeded", **changes)
                with self.assertRaises(PaymentError):
                    self.service.stripe_sync(self.user, payment.id_pago)
                self.assert_pending_stock()

    def test_processing_or_requires_action_does_not_complete(self):
        payment = self.start_card()
        for status in ("processing", "requires_action", "requires_capture"):
            self.gateway.retrieve_payment_intent.return_value = self.intent(status)
            self.assertEqual(self.service.stripe_sync(self.user, payment.id_pago).estado, "PENDIENTE")
            self.assert_pending_stock()

    def test_stripe_cancelled_sale_pending(self):
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent("canceled")
        self.assertEqual(self.service.stripe_sync(self.user, payment.id_pago).estado, "CANCELADO")
        self.assert_pending_stock()

    def test_card_cannot_be_approved_manually(self):
        payment = self.start_card()
        with self.assertRaises(PaymentError):
            self.approve(payment.id_pago)
        self.assert_pending_stock()

    def test_manual_payment_cannot_use_stripe(self):
        payment = self.start()
        with self.assertRaises(PaymentError):
            self.service.stripe_sync(self.user, payment.id_pago)

    def test_digital_approval_releases_exact_committed_stock(self):
        self.digital()
        payment = self.start_card()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        self.gateway.confirm_test_payment_intent.return_value = self.intent("succeeded")
        self.stripe_confirm(payment.id_pago)
        self.assertEqual((self.inventory().stock_actual, self.inventory().stock_reservado), (18, 3))
        self.assertFalse(self.sale().stock_comprometido)
        movement = self.db.scalar(select(InventoryMovement))
        self.assertEqual((movement.estado, movement.tipo_movimiento, movement.id_empleado_sucursal),
                         ("CONFIRMADO", "VENTA", None))
        self.stripe_confirm(payment.id_pago)
        self.assertEqual(len(self.db.scalars(select(InventoryMovement)).all()), 1)

    def test_digital_cash_rejected(self):
        self.digital()
        for method in ("EFECTIVO",):
            with self.subTest(method=method), self.assertRaises(PaymentError):
                self.start(method)
        self.assertEqual(self.db.scalars(select(Payment)).all(), [])

    def test_digital_other_owner_denied(self):
        self.digital()
        self.user.id_usuario = 99
        with self.assertRaises(PaymentError) as caught:
            self.start("TARJETA")
        self.assertEqual(caught.exception.status_code, 403)

    def test_expired_digital_cannot_start_or_confirm_new_charge(self):
        self.digital()
        payment = self.start_card()
        self.sale().fecha_expiracion_pago = PaymentsService.now() - timedelta(seconds=1)
        self.db.commit()
        self.gateway.retrieve_payment_intent.return_value = self.intent()
        with self.assertRaises(PaymentError):
            self.stripe_confirm(payment.id_pago)
        self.gateway.confirm_test_payment_intent.assert_not_called()

    def test_already_approved_remote_after_expiration_can_reconcile(self):
        self.digital()
        payment = self.start_card()
        self.sale().fecha_expiracion_pago = PaymentsService.now() - timedelta(seconds=1)
        self.db.commit()
        self.gateway.retrieve_payment_intent.return_value = self.intent("succeeded")
        self.assertEqual(self.service.stripe_sync(self.user, payment.id_pago).estado, "APROBADO")

    def test_query_owned_payment_does_not_call_stripe(self):
        payment = self.start()
        self.assertEqual(self.service.get(self.user, payment.id_pago).id_pago, payment.id_pago)
        self.assertEqual(self.gateway.mock_calls, [])

    def test_partial_unique_index_blocks_second_pending(self):
        payment = self.start()
        values = {name: getattr(self.db.get(Payment, payment.id_pago), name)
                  for name in ("id_venta", "medio", "proveedor", "entorno", "estado", "monto", "moneda")}
        self.db.add(Payment(**values, clave_idempotencia=uuid4()))
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()

    def test_previous_approved_payment_blocks_stripe_before_charge(self):
        payment = self.start_card()
        self.db.add(Payment(id_venta=1, medio="EFECTIVO", proveedor="MANUAL", entorno="LOCAL",
                            estado="APROBADO", monto=Decimal("20.20"), moneda="BOB",
                            clave_idempotencia=uuid4(), fecha_aprobacion=PaymentsService.now()))
        self.db.commit()
        self.gateway.reset_mock()
        with self.assertRaises(PaymentError) as caught:
            self.stripe_confirm(payment.id_pago)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.gateway.mock_calls, [])
        self.assert_pending_stock()

    def test_key_cannot_be_reused_for_another_sale(self):
        self.start()
        self.db.add(Sale(id_venta=2, numero_venta="VTA-OTHER", id_sucursal=2, id_empleado=5,
                         canal="PRESENCIAL", moneda="BOB", estado="PENDIENTE",
                         subtotal=10, descuento_total=0, total=10, stock_comprometido=False))
        self.db.commit()
        with self.assertRaises(PaymentError) as caught:
            self.service.start(self.user, 2, PaymentStartRequest(medio="EFECTIVO"), self.key)
        self.assertEqual(caught.exception.status_code, 409)

    @patch("app.routers.payments.PaymentsService")
    def test_api_manual_start_confirm_get_and_replay(self, service_factory):
        service_factory.return_value = self.service
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[routes.require_payment_user] = lambda: self.user
        status, result = asgi_request(app, "POST", "/api/sales/1/payments", {"medio": "QR"},
                                      [(b"idempotency-key", str(self.key).encode())])
        self.assertEqual(status, 200)
        payment_id = result["data"]["id_pago"]
        self.assertEqual(result["data"]["estado"], "PENDIENTE")
        for _ in range(2):
            status, result = asgi_request(app, "POST", f"/api/payments/{payment_id}/manual/confirm",
                                          {"resultado": "APROBADO"})
            self.assertEqual(status, 200)
            self.assertEqual(result["data"]["estado_venta"], "COMPLETADA")
        status, result = asgi_request(app, "GET", f"/api/payments/{payment_id}")
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["estado"], "APROBADO")
        self.assertEqual(self.inventory().stock_actual, 18)


class PaymentContractTests(TestCase):
    def test_payloads_cannot_override_amount_status_provider_or_card_data(self):
        for extra in (dict(monto=1), dict(estado="APROBADO"), dict(proveedor="STRIPE"),
                      dict(card_number="fake"), dict(moneda="USD")):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                PaymentStartRequest(medio="TARJETA", **extra)
        with self.assertRaises(ValidationError):
            EmptyPaymentRequest(payment_method="pm_arbitrary")

    def test_postgresql_sale_payment_movement_locks(self):
        db = MagicMock()
        repository = PaymentsRepository(db)
        for operation in (lambda: repository.lock_sale(1), lambda: repository.lock_payment(1),
                          lambda: repository.lock_movement(1)):
            operation()
            sql = str(db.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
            self.assertIn("FOR UPDATE", sql)

    def test_routes_require_authentication(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        for method, path, payload in (
            ("POST", "/api/sales/1/payments", {"medio": "EFECTIVO"}),
            ("GET", "/api/payments/1", None),
            ("POST", "/api/payments/1/manual/confirm", {"resultado": "APROBADO"}),
            ("POST", "/api/payments/1/stripe/checkout-session", {}),
            ("POST", "/api/payments/1/qr/confirm", {}),
            ("POST", "/api/payments/1/stripe/sync", None),
        ):
            with self.subTest(path=path):
                status, _ = asgi_request(app, method, path, payload,
                                        [(b"idempotency-key", str(uuid4()).encode())])
                self.assertEqual(status, 401)

    def test_auth_roles_invalid_token_and_inactive(self):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake-token")
        with patch.object(routes.AuthService, "get_current_user", return_value=NS(rol="ADMINISTRADOR")):
            self.assertEqual(routes.require_payment_user(credentials, MagicMock()).status_code, 403)
        for exception, status in ((InvalidAccessTokenError, 401), (InactiveAccountError, 403)):
            with patch.object(routes.AuthService, "get_current_user", side_effect=exception()):
                self.assertEqual(routes.require_payment_user(credentials, MagicMock()).status_code, status)

    def test_start_header_required_and_strict_payload(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[routes.require_payment_user] = lambda: NS(id_usuario=11, rol="CAJERO")
        status, _ = asgi_request(app, "POST", "/api/sales/1/payments", {"medio": "EFECTIVO"})
        self.assertEqual(status, 422)
        status, _ = asgi_request(app, "POST", "/api/payments/1/stripe/checkout-session", {"payment_method": "pm_unknown"})
        self.assertEqual(status, 422)


class StripePaymentAdapterTests(TestCase):
    @patch("app.services.stripe_service.StripeClient")
    def test_sdk_create_amount_metadata_and_idempotency_no_confirm(self, factory):
        service = StripeService(configuration())
        key = uuid4()
        service.create_payment_intent(amount=2020, currency="BOB", sale_id=1, payment_id=2, key=key)
        kwargs = factory.return_value.v1.payment_intents.create.call_args.kwargs
        self.assertEqual(kwargs["params"]["amount"], 2020)
        self.assertEqual(kwargs["params"]["currency"], "bob")
        self.assertEqual(kwargs["params"]["confirmation_method"], "manual")
        self.assertNotIn("confirm", kwargs["params"])
        self.assertEqual(kwargs["options"]["idempotency_key"], f"fashionstore-cu22-create-{key}")

    @patch("app.services.stripe_service.StripeClient")
    def test_confirm_card_error_retrieves_authoritative_intent(self, factory):
        service = FixtureStripeService(configuration())
        client = factory.return_value.v1.payment_intents
        client.confirm.side_effect = CardError("sensitive details", param=None, code="card_declined")
        client.retrieve.return_value = {"status": "requires_payment_method"}
        self.assertEqual(service.confirm_test_payment_intent("pi_fake", "pm_card_chargeDeclined", uuid4()),
                         {"status": "requires_payment_method"})
        client.retrieve.assert_called_once_with("pi_fake")

    @patch("app.services.stripe_service.StripeClient")
    def test_arbitrary_card_method_rejected_before_sdk(self, factory):
        service = FixtureStripeService(configuration())
        with self.assertRaises(ValueError):
            service.confirm_test_payment_intent("pi_fake", "pm_arbitrary", uuid4())
        factory.return_value.v1.payment_intents.confirm.assert_not_called()
