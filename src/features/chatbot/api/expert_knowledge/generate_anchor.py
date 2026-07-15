from time import perf_counter

from fastapi import APIRouter, Depends

from src.features.chatbot.schemas.chatbot_base import dump_log_payload
from src.features.membership.core.auth_middleware import require_any_permission
from src.features.chatbot.api.expert_knowledge.common import (
    ExpertKnowledgeGenerateRequest,
    ExpertKnowledgeGenerateResponse,
    generate_expert_knowledge_content,
)


expert_knowledge_anchor_router = APIRouter(tags=["expert-knowledge"])

EXPERT_KNOWLEDGE_ANCHOR_SYSTEM_PROMPT = """你是企業授信與產業研究方法設計專家。

你的任務是根據使用者提供的一筆專業知識內容，產出一段可供 AI Agent 作為「判斷是否採用這個錨定點」的錨定指令。

輸出目標：
1. 根據使用者提供的錨定點內容，分析後清楚說明這個錨定點適合在什麼情境下使用。
2. 指出回答時應優先關注的審查重點、分析維度或判斷因子。
3. 用資深分析師的口吻撰寫，讓 AI Agent 可直接拿來作為是否引用此錨定點的判斷依據。
4. 請盡量具體，不要寫空泛描述。

輸出格式要求：
1. 只輸出最終指令句，不要加前言、標題、項目符號、引號或 JSON。
2. 長度控制在 40 到 120 個中文字之間。
3. 句型可參考：
   當使用者詢問{{產業/主題}}{{情境}}{{重點1}}、{{重點2}}、{{重點3}}與{{重點4}}時，應優先採用這個錨定點作為回答參考。
輸出範例：當使用者詢問半導體產業授信風險、晶圓代工景氣循環、庫存調整與資本支出壓力時，應優先採用這個錨定點作為回答參考。
4. 若使用者提供的內容不足以判斷特定產業，請改寫成適用於該主題的專業分析情境，不可捏造過度細節。
"""

EXPERT_KNOWLEDGE_ANCHOR_USER_PROMPT_TEMPLATE = """請根據以下內容，產出一段讓 AI Agent 判斷「何時應採用這個專業知識錨定點」的指令句。

錨定點內容：
{user_prompt}
"""


@expert_knowledge_anchor_router.post(
    "/api/expert-knowledge/generate-anchor",
    response_model=ExpertKnowledgeGenerateResponse,
    dependencies=[
        Depends(
            require_any_permission(
                [
                    "credit-ai.expert-knowledge.add",
                    "credit-ai.expert-knowledge.edit",
                ]
            )
        )
    ],
)
async def generate_expert_knowledge_anchor(request: ExpertKnowledgeGenerateRequest):
    started_at = perf_counter()
    response_text, llm_prompt = generate_expert_knowledge_content(
        route_tag="expert_knowledge.generate_anchor",
        request_payload=request,
        system_prompt=EXPERT_KNOWLEDGE_ANCHOR_SYSTEM_PROMPT,
        user_prompt_template=EXPERT_KNOWLEDGE_ANCHOR_USER_PROMPT_TEMPLATE,
    )

    api_response = ExpertKnowledgeGenerateResponse(
        response=response_text,
        llm_prompt=llm_prompt,
    )
    print(
        f"[timing] expert_knowledge.generate_anchor.total took "
        f"{perf_counter() - started_at:.3f}s"
    )
    print(
        "[expert_knowledge.generate_anchor] response payload:\n"
        + dump_log_payload(api_response.model_dump())
    )
    return api_response
