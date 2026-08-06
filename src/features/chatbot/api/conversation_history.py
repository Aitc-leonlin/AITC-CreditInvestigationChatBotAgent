from fastapi import APIRouter, Depends

from src.features.chatbot.schemas.conversation_history import (
    ConversationResponse,
    ConversationUpsertCommand,
)
from src.features.chatbot.services.conversation_history_service import ConversationHistoryService
from src.features.membership.core.auth_middleware import require_permission
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse

conversation_history_router = APIRouter(
    prefix="/api/chat/conversations",
    tags=["chat-conversation-history"],
)


def conversation_service() -> ConversationHistoryService:
    return ConversationHistoryService()


@conversation_history_router.get(
    "",
    response_model=StandardResponse[list[ConversationResponse]],
)
async def list_conversations(user: dict = Depends(require_permission("credit-ai.chat"))):
    return ok(conversation_service().list_for_user(user["id"]))


@conversation_history_router.get(
    "/{conversation_id}",
    response_model=StandardResponse[ConversationResponse],
)
async def get_conversation(
    conversation_id: str,
    user: dict = Depends(require_permission("credit-ai.chat")),
):
    return ok(conversation_service().get_for_user(conversation_id, user["id"]))


@conversation_history_router.put(
    "/{conversation_id}",
    response_model=StandardResponse[ConversationResponse],
)
async def upsert_conversation(
    conversation_id: str,
    payload: ConversationUpsertCommand,
    user: dict = Depends(require_permission("credit-ai.chat")),
):
    return ok(
        conversation_service().upsert_for_user(
            conversation_id,
            user["id"],
            payload.model_dump(),
        )
    )


@conversation_history_router.delete(
    "/{conversation_id}",
    response_model=StandardResponse[dict[str, bool]],
)
async def delete_conversation(
    conversation_id: str,
    user: dict = Depends(require_permission("credit-ai.chat")),
):
    conversation_service().delete_for_user(conversation_id, user["id"])
    return ok({"deleted": True})
