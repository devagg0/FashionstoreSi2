"""Integracion basica: ReportAIService arma el prompt y usa GeminiClient para analizar CU28/29/30."""

from unittest import TestCase

from app.integrations.gemini import GeminiAnalysisError
from app.schemas.admin_sales_report import SalesReportData
from app.services.report_ai_service import ReportAIService


class FakeGeminiClient:
    """Sustituye la llamada HTTP real a Gemini para la prueba de integracion."""

    def __init__(self, response: str | None = None, error: bool = False):
        self.response = response
        self.error = error
        self.received_prompt: str | None = None

    def generate_analysis(self, *, prompt: str) -> str:
        self.received_prompt = prompt
        if self.error:
            raise GeminiAnalysisError
        return self.response


class ReportAIServiceIntegrationTests(TestCase):
    """Valida que el servicio use el cliente Gemini y traduzca sus errores."""

    def setUp(self) -> None:
        self.sales_data = SalesReportData(
            kpis={
                "cantidad_ventas": 12,
                "importe_antes_descuentos": "1000.00",
                "descuentos": "50.00",
                "importe_vendido": "950.00",
                "ticket_promedio": "79.16",
                "unidades_vendidas": 30,
                "clientes_identificados": 10,
                "ventas_sin_cliente": 2,
            },
            por_canal=[],
            por_sucursal=[],
            productos_mas_vendidos=[],
            serie_diaria=[],
        )

    def test_analyze_sales_sends_summary_and_returns_gemini_text(self) -> None:
        client = FakeGeminiClient(response="Resumen: ventas estables, mantener stock de temporada.")
        service = ReportAIService(client=client)

        result = service.analyze_sales(self.sales_data)

        self.assertEqual(result, "Resumen: ventas estables, mantener stock de temporada.")
        self.assertIn("950.00", client.received_prompt)
        self.assertIn("Cantidad de ventas: 12", client.received_prompt)
