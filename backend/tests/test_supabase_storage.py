"""Pruebas del adaptador de Supabase Storage sin realizar solicitudes reales."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.integrations.supabase_storage import (
    SupabaseStorageClient,
    SupabaseStorageConfigurationError,
    SupabaseStorageUploadError,
)


class SupabaseStorageClientTests(TestCase):
    def test_upload_uses_private_key_and_builds_public_url(self):
        response = MagicMock(status=200)
        response.__enter__.return_value = response
        client = SupabaseStorageClient(
            base_url="https://project.supabase.co/",
            service_role_key="private-service-role",
            bucket="product images",
        )

        with patch(
            "app.integrations.supabase_storage.urlopen", return_value=response
        ) as request_call:
            stored = client.upload_public_image(
                object_path="products/7/a b.webp",
                content=b"RIFFxxxxWEBP",
                content_type="image/webp",
            )

        request = request_call.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            "https://project.supabase.co/storage/v1/object/"
            "product%20images/products/7/a%20b.webp",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer private-service-role")
        self.assertEqual(request.headers["Apikey"], "private-service-role")
        self.assertEqual(
            stored.public_url,
            "https://project.supabase.co/storage/v1/object/public/"
            "product%20images/products/7/a%20b.webp",
        )

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(SupabaseStorageConfigurationError):
            SupabaseStorageClient(
                base_url="not-a-url",
                service_role_key="secret",
                bucket="products",
            )

    def test_transport_error_is_hidden(self):
        client = SupabaseStorageClient(
            base_url="https://project.supabase.co",
            service_role_key="private-service-role",
            bucket="products",
        )
        with patch(
            "app.integrations.supabase_storage.urlopen",
            side_effect=OSError("private network details"),
        ), self.assertRaises(SupabaseStorageUploadError):
            client.upload_public_image(
                object_path="products/7/a.jpg",
                content=b"image",
                content_type="image/jpeg",
            )
