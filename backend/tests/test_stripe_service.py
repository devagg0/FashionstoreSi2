"""Stripe mockeado; solo credenciales ficticias y ninguna solicitud real."""

import logging
import ssl
from unittest import TestCase
from unittest.mock import call, patch

from pydantic import ValidationError
from stripe import AuthenticationError, APIConnectionError, StripeError
from stripe import Balance
from requests import Request

from app.core.config import Settings
from app.services.stripe_service import StripeConnectionError, StripeService
from app.integrations.stripe_tls import SystemTrustAdapter, stripe_http_client


def configuration(**overrides):
    values = dict(
        DATABASE_URL="sqlite://",
        JWT_SECRET_KEY="x" * 32,
        BREVO_API_KEY="fake-brevo",
        BREVO_SENDER_EMAIL="test@example.com",
        BREVO_SENDER_NAME="Tests",
        STRIPE_SECRET_KEY="sk_test_fake_unit_only",
        STRIPE_PUBLISHABLE_KEY="pk_test_fake_unit_only",
        STRIPE_MODE="test",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


class StripeConfigurationTests(TestCase):
    def test_test_configuration_and_secret_representations(self):
        config = configuration()
        self.assertEqual(config.STRIPE_MODE, "test")
        self.assertNotIn("sk_test_fake_unit_only", repr(config))
        self.assertNotIn("pk_test_fake_unit_only", repr(config))
        self.assertNotIn("sk_test_fake_unit_only", config.model_dump_json())

    def test_invalid_modes_are_rejected(self):
        for mode in ("live", "TEST", "", " test "):
            with self.subTest(mode=mode), self.assertRaises(ValidationError):
                configuration(STRIPE_MODE=mode)

    def test_live_empty_and_wrong_keys_rejected_without_exposure(self):
        for field, keys in (
            ("STRIPE_SECRET_KEY", ("sk_live_fake", "rk_test_fake", "", "sk_test_")),
            ("STRIPE_PUBLISHABLE_KEY", ("pk_live_fake", "sk_test_fake", "", "pk_test_")),
        ):
            for key in keys:
                with self.subTest(field=field, key=key):
                    with self.assertRaises(ValidationError) as caught:
                        configuration(**{field: key})
                    self.assertNotIn("input_value", str(caught.exception))
                    if key:
                        self.assertNotIn(key, str(caught.exception))

    def test_missing_keys_rejected(self):
        for field in ("STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_MODE"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                configuration(**{field: None})


class StripeServiceTests(TestCase):
    @patch("app.services.stripe_service.StripeClient")
    def test_read_only_test_connection(self, client_factory):
        client = client_factory.return_value
        client.v1.balance.retrieve.return_value = Balance.construct_from(
            {"object": "balance", "livemode": False}, "fake-unit-key"
        )
        service = StripeService(configuration())
        self.assertTrue(service.verify_test_connection())
        self.assertEqual(client_factory.call_args.args, ("sk_test_fake_unit_only",))
        self.assertEqual(client.mock_calls, [call.v1.balance.retrieve()])

    @patch("app.services.stripe_service.StripeClient")
    def test_live_or_unconfirmed_response_rejected(self, client_factory):
        for response in ({"livemode": True}, {}, {"livemode": None}):
            client_factory.return_value.v1.balance.retrieve.return_value = response
            with self.subTest(response=response), self.assertRaises(StripeConnectionError):
                StripeService(configuration()).verify_test_connection()

    @patch("app.services.stripe_service.StripeClient")
    def test_provider_errors_hidden(self, client_factory):
        for error in (AuthenticationError, APIConnectionError, StripeError):
            client_factory.return_value.v1.balance.retrieve.side_effect = error("sk_test_fake_sensitive")
            with self.subTest(error=error):
                with self.assertRaises(StripeConnectionError) as caught:
                    StripeService(configuration()).verify_test_connection()
                self.assertNotIn("sk_test_fake_sensitive", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    @patch("app.services.stripe_service.StripeClient")
    def test_modified_settings_revalidated_before_client(self, client_factory):
        config = configuration().model_copy(update={"STRIPE_MODE": "live"})
        with self.assertRaises(ValidationError):
            StripeService(config)
        client_factory.assert_not_called()

    def test_sdk_logs_disabled(self):
        from stripe import _util
        import stripe

        self.assertTrue(logging.getLogger("stripe").disabled)
        self.assertIsNone(stripe.log)
        self.assertIsNone(_util.STRIPE_LOG)


class StripeTLSTests(TestCase):
    def test_system_context_preserves_sdk_bundle_and_verification(self):
        adapter = SystemTrustAdapter()
        request = Request("GET", "https://api.stripe.com/v1/balance").prepare()
        _, pool = adapter.build_connection_pool_key_attributes(
            request, "sdk-ca-bundle.pem"
        )
        self.assertEqual(pool["ca_certs"], "sdk-ca-bundle.pem")
        self.assertEqual(pool["cert_reqs"], "CERT_REQUIRED")
        self.assertEqual(pool["ssl_context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(pool["ssl_context"].check_hostname)
        self.assertGreater(pool["ssl_context"].cert_store_stats()["x509_ca"], 0)

    def test_disabled_verification_rejected(self):
        adapter = SystemTrustAdapter()
        request = Request("GET", "https://api.stripe.com/v1/balance").prepare()
        with self.assertRaises(ValueError):
            adapter.build_connection_pool_key_attributes(request, False)

    def test_context_used_by_sdk_session_without_global_tls_changes(self):
        client = stripe_http_client()
        self.assertTrue(client._verify_ssl_certs)
        self.assertIsInstance(
            client._session.get_adapter("https://api.stripe.com"), SystemTrustAdapter
        )
        client._session.close()
