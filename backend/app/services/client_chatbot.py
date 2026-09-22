"""Servicio independiente de CU27 para asistencia conversacional de clientes."""

from app.integrations.gemini import GeminiAnalysisError, GeminiClient
from app.schemas.catalog import CatalogProductData
from app.schemas.client_chatbot import (
    ChatbotMessage,
    ChatbotMessageRequest,
    ChatbotProductData,
    ChatbotResponseData,
)
from app.services.catalog import CatalogService


class ClientChatbotUnavailableError(Exception):
    """El asistente no pudo generar una respuesta."""


class ClientChatbotService:
    """Orquesta catálogo y Gemini sin permitir acceso de Gemini a la base de datos."""

    MAX_PRODUCTS = 20

    def __init__(
        self,
        db,
        *,
        gemini_client: GeminiClient | None = None,
        catalog_service: CatalogService | None = None,
    ) -> None:
        self.gemini_client = gemini_client or GeminiClient()
        self.catalog_service = catalog_service or CatalogService(db)

    def answer(self, request: ChatbotMessageRequest) -> ChatbotResponseData:
        products = self._find_products(request)
        context = [self._product_context(product) for product in products]
        prompt = self._build_prompt(request.message, request.history, context)
        try:
            reply = self.gemini_client.generate_analysis(prompt=prompt)
        except GeminiAnalysisError as error:
            raise ClientChatbotUnavailableError from error
        return ChatbotResponseData(
            reply=reply,
            products=[self._product_data(product) for product in products],
        )

    def _find_products(self, request: ChatbotMessageRequest) -> list[CatalogProductData]:
        products, _ = self.catalog_service.list_products(
            search=None,
            section=None,
            category_id=None,
            size_id=None,
            color_id=None,
            min_price=None,
            max_price=None,
            on_promotion=None,
            branch_id=request.id_sucursal,
            city_id=request.id_ciudad,
            sort="recientes",
            page=1,
            page_size=self.MAX_PRODUCTS,
        )
        terms = self._terms(request.message)
        if not terms:
            return products
        matched = [product for product in products if self._matches(product, terms)]
        return matched or products

    @staticmethod
    def _terms(message: str) -> set[str]:
        ignored = {
            "busco", "quiero", "necesito", "para", "una", "uno", "unos",
            "unas", "con", "que", "tenga", "tienen", "hay", "disponible",
            "disponibilidad", "prenda", "producto", "ayuda", "elegir",
        }
        return {
            term.strip(".,!?;:()[]{}").lower()
            for term in message.split()
            if len(term.strip(".,!?;:()[]{}")) > 2
            and term.strip(".,!?;:()[]{}").lower() not in ignored
        }

    @classmethod
    def _matches(cls, product: CatalogProductData, terms: set[str]) -> bool:
        searchable = " ".join(
            [
                product.nombre,
                product.categoria,
                product.descripcion_corta or "",
                *(color.nombre for color in product.colores_disponibles),
                *(size.nombre for size in product.tallas_disponibles),
            ]
        ).lower()
        return any(term in searchable for term in terms)

    @staticmethod
    def _product_context(product: CatalogProductData) -> dict:
        availability = product.disponibilidad_sucursal
        return {
            "id": product.id_producto,
            "nombre": product.nombre,
            "categoria": product.categoria,
            "descripcion": product.descripcion_corta,
            "precio": str(product.precio_final),
            "colores": [color.nombre for color in product.colores_disponibles],
            "tallas": [size.nombre for size in product.tallas_disponibles],
            "disponibilidad": availability.estado if availability else None,
            "cantidad_disponible": (
                availability.cantidad_disponible if availability else None
            ),
        }

    @staticmethod
    def _product_data(product: CatalogProductData) -> ChatbotProductData:
        availability = product.disponibilidad_sucursal
        return ChatbotProductData(
            id_producto=product.id_producto,
            nombre=product.nombre,
            categoria=product.categoria,
            precio=product.precio_final,
            colores=[color.nombre for color in product.colores_disponibles],
            tallas=[size.nombre for size in product.tallas_disponibles],
            disponibilidad=availability.estado if availability else None,
            cantidad_disponible=(
                availability.cantidad_disponible if availability else None
            ),
        )

    @staticmethod
    def _build_prompt(
        message: str, history: list[ChatbotMessage], products: list[dict]
    ) -> str:
        history_text = "\n".join(
            f"{item.role}: {item.content.strip()}" for item in history[-12:]
        ) or "sin historial"
        return (
            "Eres el asistente de compras de FashionStore, una tienda de moda. "
            "Responde en español, de forma breve y útil. Usa exclusivamente los "
            "productos del contexto. No inventes productos, precios, tallas, colores "
            "ni disponibilidad. Si no hay coincidencias, dilo y pide un criterio "
            "diferente. Puedes ayudar a elegir una prenda explicando la relación "
            "entre la necesidad del cliente y los datos disponibles.\n\n"
            f"Historial reciente:\n{history_text}\n\n"
            f"Pregunta actual: {message.strip()}\n\n"
            f"Productos verificados por el catálogo:\n{products}"
        )