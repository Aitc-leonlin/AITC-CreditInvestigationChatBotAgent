import os
from time import perf_counter

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from typing_extensions import TypedDict
from src.types.langgraph_state_types import OverallState
from src.providers.chat_openAI_provider import chat_model, get_message_text


class InputState(TypedDict):
    user_input: str


def sanitize_llm_text(text: str) -> str:
    if not text:
        return ""
    sanitized_chars = []
    for char in str(text):
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        if char in "\n\r\t" or codepoint >= 32:
            sanitized_chars.append(char)
    return "".join(sanitized_chars)


# langGraph Node:將question提供給LLM進行分析，判斷是否在「財務報表相關問題」範圍內
def classify_is_question_in_range(state: OverallState):
    started_at = perf_counter()
    classifyQuestionTypePrompt = f"""
        ###指示：
            你是一個分類器。判斷使用者訊息是否可以從「財務報表」中找到答案。
        ###規則：
            
            回覆直接全部回True
        ###問題: ${state['rephrased_question']}"""

    sanitized_prompt = sanitize_llm_text(classifyQuestionTypePrompt)
    print("[classify_is_question_in_range] prompt:\n" + sanitized_prompt)
    res = chat_model.invoke(sanitized_prompt)
    is_question_in_range = get_message_text(res)

    print("is_question_in_range======", is_question_in_range)
    print(f"[timing] classify_is_question_in_range took {perf_counter() - started_at:.3f}s")
    return {**state, "is_question_in_range": is_question_in_range}
