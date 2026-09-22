"""Prueba única del endpoint de CU27 con Gemini aislado."""

from decimal import Decimal
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.routers import client_chatbot as routes
from app.schemas.catalog import CatalogProductData, CatalogSizeData
from app.schemas.client_chatbot import ChatbotMessageRequest
from app.services.client_chatbot import ClientChatbotService


class ClientChatbotEndpointTest(TestCase):
    def test_client_question_receives_gemini_response_with_verified_product(self):
        product = CatalogProductData(
            id_producto=7,
            nombre="Vestido rojo de fiesta",
            descripcion_corta="Vestido elegante para ocasiones especiales",
            seccion="MUJER",
            id_categoria=3,
            categoria="Vestidos",
            precio_base=Decimal("240.00"),
            precio_final=Decimal("200.00"),
            tiene_promocion=True,
            promocion_destacada=None,
            porcentaje_descuento=Decimal("16.67"),
            monto_descuento=Decimal("40.00"),
            imagen_principal=None,
            colores_disponibles=[],
            tallas_disponibles=[CatalogSizeData(id_talla=2, nombre="M")],
        )
        catalog = MagicMock()
        catalog.list_products.return_value = ([product], NS(total=1))
        gemini = MagicMock()
        gemini.generate_analysis.return_value = (
            "Encontré un vestido rojo de fiesta en talla M por Bs 200.00."
        )
        service = ClientChatbotService(
            MagicMock(), catalog_service=catalog, gemini_client=gemini
        )

        with patch.object(routes, "ClientChatbotService", return_value=service):
            response = routes.send_message(
                ChatbotMessageRequest(message="Busco un vestido rojo para una fiesta"),
                NS(id_usuario=10, rol="CLIENTE"),
                MagicMock(),
            )

        self.assertEqual(response.data.reply, "Encontré un vestido rojo de fiesta en talla M por Bs 200.00.")
        self.assertEqual(response.data.products[0].id_producto, 7)
        prompt = gemini.generate_analysis.call_args.kwargs["prompt"]
        self.assertIn("Vestido rojo de fiesta", prompt)
        self.assertIn("No inventes productos", prompt)