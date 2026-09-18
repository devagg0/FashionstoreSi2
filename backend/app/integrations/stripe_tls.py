"""TLS de Stripe con las CA confiables del sistema y el bundle del SDK."""

import ssl

from requests import Session
from requests.adapters import HTTPAdapter
from stripe import RequestsClient


class SystemTrustAdapter(HTTPAdapter):
    def __init__(self):
        # En Windows carga CA/ROOT. Mantiene CERT_REQUIRED y check_hostname.
        self._ssl_context = ssl.create_default_context()
        super().__init__()

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        if verify is False:
            raise ValueError("Stripe requiere verificacion TLS")
        host, pool = super().build_connection_pool_key_attributes(
            request, verify, cert
        )
        # Conservar ca_certs/ca_cert_dir del SDK y agregar confianza del sistema.
        pool["ssl_context"] = self._ssl_context
        pool["cert_reqs"] = "CERT_REQUIRED"
        return host, pool


def stripe_http_client() -> RequestsClient:
    session = Session()
    session.mount("https://", SystemTrustAdapter())
    return RequestsClient(session=session, timeout=15, verify_ssl_certs=True)
