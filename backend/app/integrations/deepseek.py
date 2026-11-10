"""Cliente reutilizable de DeepSeek (API compatible con chat/completions).

Lo consumen el asistente del cliente (CU27) y, posteriormente, CU20. La clave
nunca se registra ni se expone fuera de esta capa.
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


logger = logging.getLogger(__name__)


class DeepSeekError(Exception):
    """DeepSeek no pudo generar la respuesta solicitada."""


class DeepSeekClient:
    """Envia prompts a DeepSeek y devuelve el texto generado."""

    def __init__(self, *, timeout: int = 30) -> None:
        self.timeout = timeout

    def generate_analysis(
        self,
        *,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 700,
        json_mode: bool = False,
    ) -> str:
        if settings.DEEPSEEK_API_KEY is None:
            raise DeepSeekError("DEEPSEEK_API_KEY no configurada")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": settings.DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        url = f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {settings.DEEPSEEK_API_KEY.get_secret_value()}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise DeepSeekError(f"HTTP {response.status}")
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            # Solo el codigo HTTP: el cuerpo/cabeceras podrian contener datos sensibles.
            logger.error("DeepSeek HTTPError %s", error.code)
            raise DeepSeekError(f"HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            logger.error("DeepSeek request failed: %s", type(error).__name__)
            raise DeepSeekError(type(error).__name__) from error

        try:
            text = (body["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as error:
            raise DeepSeekError("Respuesta inesperada") from error
        if not text:
            raise DeepSeekError("Respuesta vacia")
        return text

