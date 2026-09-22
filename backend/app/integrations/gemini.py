"""Cliente minimo para el analisis generativo de reportes con Gemini."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_GENERATE_CONTENT_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)


class GeminiAnalysisError(Exception):
    """Gemini no pudo generar el analisis solicitado."""


class GeminiClient:
    """Envia un prompt de texto a Gemini y devuelve el analisis generado, sin exponer la clave fuera de esta capa."""

    def generate_analysis(self, *, prompt: str) -> str:
        if settings.GEMINI_API_KEY is None:
            raise GeminiAnalysisError
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700},
        }
        request = Request(
            f"{GEMINI_GENERATE_CONTENT_URL}?key={settings.GEMINI_API_KEY.get_secret_value()}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise GeminiAnalysisError
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            # DIAGNOSTICO TEMPORAL: imprime el detalle real de Gemini (codigo y mensaje)
            # para identificar si el fallo es de API Key, modelo, permisos o cuota.
            try:
                detail = error.read().decode("utf-8")
            except Exception:
                detail = "<sin cuerpo>"
            logger.error("Gemini HTTPError %s: %s", error.code, detail)
            print(f"[GEMINI DEBUG] HTTP {error.code}: {detail}")
            raise GeminiAnalysisError from error
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            # DIAGNOSTICO TEMPORAL: imprime el error real de red/parseo.
            logger.error("Gemini request failed: %r", error)
            print(f"[GEMINI DEBUG] {type(error).__name__}: {error}")
            raise GeminiAnalysisError from error

        try:
            parts = body["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
        except (KeyError, IndexError, TypeError) as error:
            raise GeminiAnalysisError from error
        if not text:
            raise GeminiAnalysisError
        return text
