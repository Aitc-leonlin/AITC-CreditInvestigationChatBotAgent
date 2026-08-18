from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.features.chatbot.core.providers.chat_openAI_provider import chat_model, get_message_text
from src.shared.database.serialization import database_json_dumps


NO_ANALYSIS_DATA_MESSAGE = "資料不足，無法產生分析。"


def has_context_data(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(has_context_data(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_context_data(item) for item in value)
    return bool(value)


def build_report_section_prompt(
    *,
    section_title: str,
    analysis_goal: str,
    context: dict[str, Any],
) -> str:
    context_text = database_json_dumps(context, ensure_ascii=False, indent=2)
    return (
        f"請根據下列 DB 資料產生「{section_title}」。\n"
        f"分析目標：{analysis_goal}\n"
        "要求：\n"
        "1. 僅能使用提供的 DB 資料，不可自行補外部事實。\n"
        "2. 若某項資料缺漏，請明確說明該項資料不足，不要推測。\n"
        "3. 請用繁體中文，輸出 2 到 4 段授信用語的分析文字。\n"
        "4. 重點放在信用風險、償債能力、營運壓力與可觀察事項。\n\n"
        f"DB 資料：\n{context_text}"
    )


def generate_report_section_analysis(
    *,
    section_title: str,
    analysis_goal: str,
    context: dict[str, Any],
) -> str:
    if not has_context_data(context):
        return NO_ANALYSIS_DATA_MESSAGE

    try:
        response = chat_model.invoke(
            [
                SystemMessage(
                    content=(
                        "You are a senior credit investigation analyst. "
                        "Use only the supplied database context. "
                        "Return concise Traditional Chinese report paragraphs."
                    )
                ),
                HumanMessage(
                    content=build_report_section_prompt(
                        section_title=section_title,
                        analysis_goal=analysis_goal,
                        context=context,
                    )
                ),
            ]
        )
    except Exception:
        return "AI 分析暫時無法產生，請確認模型服務設定後重試。"
    return get_message_text(response)
