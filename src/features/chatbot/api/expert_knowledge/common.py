from fastapi import HTTPException
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.features.chatbot.schemas.chatbot_base import dump_log_payload
from src.features.chatbot.core.providers.chat_openAI_provider import chat_model, get_message_text


class ExpertKnowledgeGenerateRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        alias="PROMPT",
        description="前端提供的專業知識內容或提示內容",
    )

    model_config = {"populate_by_name": True}


class ExpertKnowledgeGenerateResponse(BaseModel):
    response: str
    llm_prompt: str


def build_llm_prompt_text(formatted_messages: list[BaseMessage]) -> str:
    return "\n\n".join(
        f"[{message.type}] {getattr(message, 'content', '')}"
        for message in formatted_messages
    )


def generate_expert_knowledge_content(
    *,
    route_tag: str,
    request_payload: ExpertKnowledgeGenerateRequest,
    system_prompt: str,
    user_prompt_template: str,
) -> tuple[str, str]:
    user_prompt = request_payload.prompt.strip()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", user_prompt_template),
        ]
    )
    formatted_messages = prompt.format_messages(user_prompt=user_prompt)
    llm_prompt = build_llm_prompt_text(formatted_messages)
    print(
        f"[{route_tag}] request payload:\n"
        + dump_log_payload(request_payload.model_dump(by_alias=True))
    )
    print(f"[{route_tag}] llm prompt:\n" + llm_prompt)

    try:
        response = chat_model.invoke(formatted_messages)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {exc}") from exc

    return get_message_text(response), llm_prompt
