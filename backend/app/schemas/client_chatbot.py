"""Contratos de CU27 para el asistente conversacional del cliente."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ChatbotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class ChatbotMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    history: list[ChatbotMessage] = Field(default_factory=list, max_length=12)
    id_sucursal: int | None = Field(default=None, gt=0)
    id_ciudad: int | None = Field(default=None, gt=0)


class ChatbotProductData(BaseModel):
    id_producto: int
    nombre: str
    categoria: str
    precio: Decimal
    colores: list[str]
    tallas: list[str]
    disponibilidad: str | None
    cantidad_disponible: int | None


class ChatbotResponseData(BaseModel):
    reply: str
    products: list[ChatbotProductData]


class ChatbotMessageResponse(BaseModel):
    success: Literal[True] = True
    data: ChatbotResponseData