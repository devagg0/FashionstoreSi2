"""Adaptador Stripe exclusivamente TEST, sin datos de tarjetas ni logs del SDK."""

import logging

import stripe
from stripe import StripeClient, StripeError
from stripe import _util

from app.core.config import Settings, settings
from app.integrations.stripe_tls import stripe_http_client

# El SDK puede registrar respuestas de autenticacion con fragmentos de claves.
# Desactivar sus dos salidas, incluida STRIPE_LOG; SDK fijado en requirements.
stripe.log = None
_util.STRIPE_LOG = None
logging.getLogger("stripe").disabled = True


class StripeConnectionError(RuntimeError):
    """Fallo seguro que no expone respuestas ni credenciales del proveedor."""


class StripeService:
    def __init__(self, configuration: Settings = settings):
        # Revalidar incluso si el llamador construyo o modifico Settings sin validar.
        safe = Settings.model_validate(configuration.model_dump())
        self._client = StripeClient(
            safe.STRIPE_SECRET_KEY.get_secret_value(),
            http_client=stripe_http_client(),
            max_network_retries=0,
        )

    def verify_test_connection(self) -> bool:
        """GET /v1/balance; no crea recursos y no devuelve datos de la cuenta."""
        try:
            balance = self._client.v1.balance.retrieve()
        except StripeError:
            raise StripeConnectionError(
                "No se pudo verificar la conexion con Stripe TEST"
            ) from None
        if "livemode" not in balance or balance["livemode"] is not False:
            raise StripeConnectionError("Stripe no confirmo una respuesta TEST")
        return True

    def create_payment_intent(self, *, amount, currency, sale_id, payment_id, key):
        try:
            return self._client.v1.payment_intents.create(
                params={
                    "amount": amount, "currency": currency.lower(),
                    "payment_method_types": ["card"],
                    "confirmation_method": "manual", "capture_method": "automatic",
                    "metadata": {"id_venta": str(sale_id), "id_pago": str(payment_id),
                                 "clave_idempotencia": str(key)},
                },
                options={"idempotency_key": f"fashionstore-cu22-create-{key}"},
            )
        except StripeError:
            raise StripeConnectionError("No se pudo iniciar Stripe TEST; reintente con la misma clave") from None

    def retrieve_payment_intent(self, reference):
        try:
            return self._client.v1.payment_intents.retrieve(reference)
        except StripeError:
            raise StripeConnectionError("No se pudo consultar Stripe TEST") from None

    def cancel_payment_intent(self, reference, key):
        try:
            return self._client.v1.payment_intents.cancel(
                reference, options={"idempotency_key": f"fashionstore-cu22-cancel-{key}"},
            )
        except StripeError:
            raise StripeConnectionError("No se pudo cerrar el intento Stripe TEST; consulte el mismo pago") from None

    def create_checkout_session(self, *, amount, currency, sale_id, payment_id, key, success_url, cancel_url):
        metadata = {"id_venta": str(sale_id), "id_pago": str(payment_id), "clave_idempotencia": str(key)}
        try:
            return self._client.v1.checkout.sessions.create(
                params={
                    "mode": "payment", "payment_method_types": ["card"],
                    "client_reference_id": str(sale_id),
                    "line_items": [{"quantity": 1, "price_data": {
                        "currency": currency.lower(), "unit_amount": amount,
                        "product_data": {"name": f"FashionStore - Venta {sale_id}"},
                    }}],
                    "metadata": metadata, "payment_intent_data": {"metadata": metadata},
                    "success_url": success_url, "cancel_url": cancel_url,
                }, options={"idempotency_key": f"fashionstore-cu22-checkout-{key}"},
            )
        except StripeError:
            raise StripeConnectionError("No se pudo crear Checkout TEST; reintente el mismo pago") from None

    def retrieve_checkout_session(self, reference):
        try:
            return self._client.v1.checkout.sessions.retrieve(
                reference, params={"expand": ["payment_intent"]})
        except StripeError:
            raise StripeConnectionError("No se pudo consultar Checkout TEST") from None

    def expire_checkout_session(self, reference, key):
        try:
            return self._client.v1.checkout.sessions.expire(
                reference, options={"idempotency_key": f"fashionstore-cu22-checkout-expire-{key}"})
        except StripeError:
            raise StripeConnectionError("No se pudo cerrar Checkout TEST; consulte el mismo pago") from None

    def create_refund(self, *, payment_intent, amount, key, refund_id=None):
        try:
            return self._client.v1.refunds.create(
                params={"payment_intent": payment_intent, "amount": amount,
                        "reason": "requested_by_customer",
                        "metadata": {"id_reembolso": str(refund_id), "clave_idempotencia": str(key)}},
                options={"idempotency_key": f"fashionstore-cu24-refund-{key}"})
        except StripeError:
            raise StripeConnectionError("Reembolso Stripe TEST incierto; reintente la misma solicitud") from None

    def retrieve_refund(self, reference):
        try:
            return self._client.v1.refunds.retrieve(reference)
        except StripeError:
            raise StripeConnectionError("No se pudo consultar el reembolso Stripe TEST") from None

    def retrieve_charge(self, reference):
        try:
            return self._client.v1.charges.retrieve(reference)
        except StripeError:
            raise StripeConnectionError("No se pudo consultar el cargo Stripe TEST") from None

    def list_refunds(self, payment_intent):
        try:
            result = self._client.v1.refunds.list(params={"payment_intent": payment_intent, "limit": 100})
            return list(result.auto_paging_iter())
        except StripeError:
            raise StripeConnectionError("No se pudieron consultar reembolsos Stripe TEST") from None
