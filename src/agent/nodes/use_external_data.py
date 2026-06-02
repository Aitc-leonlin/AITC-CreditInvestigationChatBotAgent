import json
import os
from time import perf_counter

from openai import OpenAI
from pydantic import BaseModel, Field

from src.providers.chat_openAI_provider import chat_model
from src.types.langgraph_state_types import OverallState


class ExternalDataDecisionSchema(BaseModel):
    needs_external_data: bool = Field(
        description="這個問題是否需要先查詢外部資料，才能更完整回答"
    )
    external_data_query_text: str = Field(
        default="",
        description="若需要外部資料，提供給前端查詢外部資訊的建議查詢句"
    )
    reason: str = Field(default="", description="簡短說明判斷原因")


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


def invoke_structured_with_retry(structured_llm, prompt: str) -> dict:
    try:
        return structured_llm.invoke(prompt).model_dump()
    except Exception as exc:
        print("[use_external_data] structured output parse failed, retrying:", exc)

    retry_prompt = (
        prompt
        + """

### 輸出格式修正規則
前一次輸出格式不符合系統要求。請重新輸出，且必須完全符合下列 JSON schema：
{
  "needs_external_data": true,
  "external_data_query_text": "建議查詢句",
  "reason": "簡短原因"
}

嚴格規則：
1. 只能輸出 JSON object，不要輸出 markdown、說明文字或程式碼區塊。
2. key 名稱只能使用 needs_external_data、external_data_query_text、reason。
3. 若 needs_external_data = false，external_data_query_text 必須輸出空字串。
4. 若 needs_external_data = true，external_data_query_text 必須是可直接拿去查外部資訊的繁體中文完整句子。
"""
    )
    print("[use_external_data] retry prompt:\n" + retry_prompt)
    try:
        return structured_llm.invoke(retry_prompt).model_dump()
    except Exception as exc:
        print("[use_external_data] structured output retry failed, fallback to no external data:", exc)
        return {
            "needs_external_data": False,
            "external_data_query_text": "",
            "reason": f"structured output failed: {exc}",
        }


def query_external_data_with_llm(state: OverallState, query_text: str) -> tuple[str, str]:
    question = sanitize_llm_text(state.get("rephrased_question") or state.get("user_input") or "")
    semantic_plan = state.get("semantic_plan") or {}
    analysis_goal = sanitize_llm_text(semantic_plan.get("analysis_goal") or "")
    external_data_model = "gpt-5.5"
    prompt = f"""
你是信用徵審流程中的外部資料搜尋與摘要 Agent。

請使用網路搜尋查詢「外部資料查詢主題」，整理可供最終回答引用的外部背景資料。

重要規則：
1. 請聚焦公司、期間、新聞、重大事件、產業脈絡、訴訟、裁罰、政策、供應鏈或信用風險。
2. 不要把外部資料當成財務報表數字來源；外部資料只可作為事件背景、風險脈絡與判斷輔助。
3. 若無法確認具體事件或來源，請明確寫出「無法確認」與限制，不要捏造新聞、日期、來源或事件。
4. 請用繁體中文輸出，格式固定為：
   - 查詢主題：
   - 摘要重點：
   - 可能影響：
   - 資料限制：

使用者原始問題：
{question}

analysis_goal：
{analysis_goal}

外部資料查詢主題：
{query_text}
"""
    print("[use_external_data] external data llm prompt:\n" + prompt)
    client = OpenAI()
    response = client.responses.create(
        model=external_data_model,
        tools=[
            {"type": "web_search"},
        ],
        input=prompt,
    )
    response_text = sanitize_llm_text(response.output_text)
    print("[use_external_data] external data llm response:\n" + response_text)
    return response_text, prompt


def use_external_data(state: OverallState) -> OverallState:
    started_at = perf_counter()
    use_external_data_enabled = bool(state.get("use_external_data", True))
    request_source = str(state.get("request_source") or "").strip().lower()
    decision = str(state.get("external_data_decision") or "").strip().lower()
    query_text = sanitize_llm_text(state.get("external_data_query_text") or "")

    if not use_external_data_enabled:
        result = {
            "needs_external_data": False,
            "external_data_query_text": "",
            "reason": "Skipped because referenceSettings.useExternalData is false.",
            "decision": "disabled",
        }
        print("[use_external_data] skipped: use_external_data is false")
        return {
            **state,
            "needs_external_data": False,
            "awaiting_external_data_confirmation": False,
            "external_data_result": result,
        }

    if request_source == "chatbot-with-external" and decision == "adopted":
        external_data_response = ""
        external_data_response_prompt = ""
        try:
            external_data_response, external_data_response_prompt = query_external_data_with_llm(
                state,
                query_text,
            )
            print(
                "[use_external_data] external_data_response after query:\n"
                + external_data_response
            )
            print(
                "[use_external_data] external_data_response_prompt after query:\n"
                + external_data_response_prompt
            )
        except Exception as exc:
            external_data_response = f"外部資料查詢失敗：{exc}"
            print("[use_external_data] external data llm failed:", exc)

        result = {
            "needs_external_data": True,
            "external_data_query_text": query_text,
            "external_data_response": external_data_response,
            "reason": "Frontend adopted the suggested external data query text.",
            "decision": "adopted",
        }
        print("[use_external_data] adopted external data query text:\n" + query_text)
        print(f"[timing] use_external_data took {perf_counter() - started_at:.3f}s")
        return {
            **state,
            "needs_external_data": True,
            "awaiting_external_data_confirmation": False,
            "external_data_query_text": query_text,
            "external_data_response": external_data_response,
            "external_data_response_prompt": external_data_response_prompt,
            "external_data_result": result,
        }

    if request_source == "chatbot-with-external" and decision == "rejected":
        result = {
            "needs_external_data": False,
            "external_data_query_text": query_text,
            "reason": "Frontend rejected the suggested external data query text.",
            "decision": "rejected",
        }
        print("[use_external_data] rejected external data query text")
        print(f"[timing] use_external_data took {perf_counter() - started_at:.3f}s")
        return {
            **state,
            "needs_external_data": False,
            "awaiting_external_data_confirmation": False,
            "external_data_result": result,
        }

    if request_source == "chatbot-with-external":
        result = {
            "needs_external_data": False,
            "external_data_query_text": "",
            "reason": "Skipped because this node only asks LLM for /chatbot requests.",
            "decision": decision,
        }
        print("[use_external_data] skipped: request_source is not /chatbot")
        print(f"[timing] use_external_data took {perf_counter() - started_at:.3f}s")
        return {
            **state,
            "needs_external_data": False,
            "awaiting_external_data_confirmation": False,
            "external_data_result": result,
        }

    question = sanitize_llm_text(state.get("rephrased_question") or state.get("user_input") or "")
    semantic_plan = state.get("semantic_plan") or {}
    analysis_goal = sanitize_llm_text(semantic_plan.get("analysis_goal") or "")
    requirements = semantic_plan.get("requirements") or []
    requirement_lines = []
    for index, requirement in enumerate(requirements, start=1):
        requirement_lines.append(
            json.dumps(
                {
                    "index": index,
                    "field_query": requirement.get("field_query") or [],
                    "statement_type": requirement.get("statement_type") or "",
                    "periods": requirement.get("periods") or [],
                    "purpose": requirement.get("purpose") or "",
                },
                ensure_ascii=False,
            )
        )

    prompt = f"""
你是授信與財報分析流程中的外部資料判斷器。

你的任務是根據使用者問題、analysis_goal 與各 requirement 的 purpose，
判斷這題是否需要先查詢「財務報表資料庫以外」的外部資訊，才能更完整回答。

請特別判斷下列情境是否需要外部資料：
1. 問題要求即時、最新、近期、目前、最近發展、最新消息、重大事件。
2. 問題涉及產業景氣、新聞事件、訴訟、裁罰、政策、供應鏈、經營策略、信用事件、違約風險、非財報資料背景。
3. 問題需要知道財報數字以外的外部原因、外部佐證、產業脈絡或事件背景。

請判斷下列情境通常不需要外部資料：
1. 單純查財務數字、比率、期間比較、趨勢分析，且只靠財報資料即可回答。
2. 問題雖然是分析，但核心仍只依賴財報欄位與期間資料即可完成。

輸出規則：
1. 若需要外部資料，needs_external_data = true。
2. 若需要外部資料，external_data_query_text 必須是一句可直接交給前端查詢外部資訊的繁體中文查詢句。
3. external_data_query_text 要具體包含公司、期間、主題或事件，不可只寫關鍵字。
4. 若不需要外部資料，needs_external_data = false，external_data_query_text = ""。
5. 只能輸出 JSON。

原始問題：
{question}

analysis_goal：
{analysis_goal}

requirements：
{chr(10).join(requirement_lines) if requirement_lines else "無"}
"""

    print("[use_external_data] prompt:\n" + prompt)
    structured_llm = chat_model.with_structured_output(ExternalDataDecisionSchema)
    result = invoke_structured_with_retry(structured_llm, prompt)
    print("[use_external_data] result:\n" + json.dumps(result, ensure_ascii=False, indent=2))

    needs_external_data = bool(result.get("needs_external_data"))
    external_data_query_text = sanitize_llm_text(result.get("external_data_query_text") or "")
    if needs_external_data and external_data_query_text:
        answer = (
            f"這個問題可能需要外部查詢「{external_data_query_text}」的資料，"
            "請前端確認是否要用這段話查詢外部的資訊。"
        )
        print(f"[timing] use_external_data took {perf_counter() - started_at:.3f}s")
        return {
            **state,
            "needs_external_data": True,
            "awaiting_external_data_confirmation": True,
            "external_data_query_text": external_data_query_text,
            "external_data_result": result,
            "answer": answer,
        }

    result["external_data_query_text"] = ""
    result["needs_external_data"] = False
    print(f"[timing] use_external_data took {perf_counter() - started_at:.3f}s")
    return {
        **state,
        "needs_external_data": False,
        "awaiting_external_data_confirmation": False,
        "external_data_query_text": "",
        "external_data_result": result,
    }
