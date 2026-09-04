"""Cliente mínimo para el correo transaccional de Brevo."""

from html import escape
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailError(Exception):
    """Brevo no pudo aceptar el correo transaccional."""


class BrevoEmailClient:
    """Envía correos de recuperación sin exponer la clave fuera de esta capa."""

    def send_password_recovery_code(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        code: str,
    ) -> None:
        """Envía un código temporal; nunca envía ni conoce contraseñas."""
        safe_name = escape(recipient_name)
        safe_code = escape(code)
        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; color: #2b2625;">
            <h2>Recupera tu cuenta FashionStore</h2>
            <p>Hola {safe_name},</p>
            <p>Tu código de recuperación es:</p>
            <p style="font-size: 28px; font-weight: 700; letter-spacing: 6px;">
              {safe_code}
            </p>
            <p>El código vence en 10 minutos.</p>
            <p>Si no solicitaste este cambio, ignora este correo.</p>
          </body>
        </html>
        """.strip()
        payload = {
            "sender": {
                "email": str(settings.BREVO_SENDER_EMAIL),
                "name": settings.BREVO_SENDER_NAME,
            },
            "to": [
                {
                    "email": recipient_email,
                    "name": recipient_name,
                }
            ],
            "subject": "Código de recuperación de FashionStore",
            "htmlContent": html_content,
        }
        request = Request(
            BREVO_TRANSACTIONAL_EMAIL_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "accept": "application/json",
                "api-key": settings.BREVO_API_KEY.get_secret_value(),
                "content-type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 201:
                    raise BrevoEmailError
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise BrevoEmailError from error
