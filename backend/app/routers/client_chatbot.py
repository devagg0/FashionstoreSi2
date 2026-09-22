"""Endpoint de CU27 para el asistente conversacional del cliente."""

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers.client_reservations import ClientDependency
from app.schemas.auth import ErrorResponse
from app.schemas.client_chatbot import ChatbotMessageRequest, ChatbotMessageResponse
from app.services.client_chatbot import (
    ClientChatbotService,
    ClientChatbotUnavailableError,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/client/chatbot", tags=["Asistente del cliente CU27"])


@router.post(
    "/message",
    response_model=ChatbotMessageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Token invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Se requiere el rol CLIENTE"},
        503: {"model": ErrorResponse, "description": "Gemini no disponible"},
    },
)
def send_message(
    payload: ChatbotMessageRequest,
    client: ClientDependency,
    db: Session = Depends(get_db),
) -> ChatbotMessageResponse | JSONResponse:
    if isinstance(client, JSONResponse):
        return client
    try:
        data = ClientChatbotService(db).answer(payload)
    except ClientChatbotUnavailableError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"success": False, "message": "El asistente no está disponible"},
        )
    except Exception:
        logger.exception("Error interno de CU27")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": "No fue posible procesar la consulta"},
        )
    return ChatbotMessageResponse(data=data)