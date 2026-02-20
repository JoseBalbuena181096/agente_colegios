"""
Conversations Router — Thin HTTP layer
=======================================
Webhook endpoint for all conversation channels (WhatsApp, Messenger, Instagram DMs, SMS).
Delegates all business logic to ConversationOrchestrator.
"""

from fastapi import APIRouter, Request

from app.dependencies import orchestrator
from app.services.payload_service import extract_webhook_data

router = APIRouter()


@router.post("/webhook_conversations")
async def receive_webhook_conversations(request: Request):
    """
    Webhook general para CONVERSACIONES (WhatsApp, Messenger DMs, Instagram DMs, SMS).
    Extrae el payload, valida, y delega al orchestrator.
    """
    raw_body = await request.json()
    data = extract_webhook_data(raw_body)

    if data.should_ignore:
        return data.ignore_response

    return orchestrator.process(data)
