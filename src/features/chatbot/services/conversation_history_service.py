from typing import Any

from src.features.chatbot.repositories.conversation_history_repository import ConversationHistoryRepository
from src.features.membership.core.exceptions import ResourceNotFoundError


class ConversationHistoryService:
    def __init__(self, repository: ConversationHistoryRepository | None = None):
        self.repository = repository or ConversationHistoryRepository()

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        return self.repository.list_for_user(user_id)

    def get_for_user(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        conversation = self.repository.get_for_user(conversation_id, user_id)
        if conversation is None:
            raise ResourceNotFoundError("Conversation not found.", {"id": conversation_id})
        return conversation

    def upsert_for_user(
        self,
        conversation_id: str,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        conversation = self.repository.upsert_for_user(conversation_id, user_id, payload)
        if conversation is None:
            raise ResourceNotFoundError("Conversation not found.", {"id": conversation_id})
        return conversation

    def delete_for_user(self, conversation_id: str, user_id: str) -> None:
        if not self.repository.delete_for_user(conversation_id, user_id):
            raise ResourceNotFoundError("Conversation not found.", {"id": conversation_id})
