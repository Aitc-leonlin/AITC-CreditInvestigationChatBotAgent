from time import perf_counter

from fastapi import APIRouter, Depends

from src.features.chatbot.schemas.chatbot_base import dump_log_payload
from src.features.membership.core.auth_middleware import require_any_permission
from src.features.chatbot.api.expert_knowledge.common import (
    ExpertKnowledgeGenerateRequest,
    ExpertKnowledgeGenerateResponse,
    generate_expert_knowledge_content,
)


expert_knowledge_analysis_router = APIRouter(tags=["expert-knowledge"])

EXPERT_KNOWLEDGE_ANALYSIS_SYSTEM_PROMPT = """你是熟悉企業授信審查、產業分析與財務評估的資深分析師。

你的任務是根據使用者提供的一筆專業知識內容，產出可直接提供給後續 LLM 作為 RAG 參考的「專業分析指引」。

輸出目標：
1. 將使用者提供的知識改寫成數段可直接引用的專業分析內容。
2. 每段內容需明確說明某個分析面向在什麼情境下應如何判讀。
3. 每段內容需包含應留意的風險、判斷邏輯，以及建議搭配觀察的指標或補充資訊。
4. 內容要像授信審查報告中的分析說明，可直接放入後續 RAG 流程作為提示內容。
5. 請盡量具體，不要只列關鍵字或寫成口號。

輸出格式要求：
1. 只輸出分析內容本身，不要加前言、結語、引號或 JSON。
2. 以 Markdown 輸出，使用編號小節格式，例如：
   ### 1. 應收帳款分析
3. 至少輸出 3 個分析面向，每個面向各 1 段完整說明。
4. 每段內容應包含：
   - 該面向的判讀情境
   - 應注意的風險或原因
   - 建議搭配觀察的財務指標、營運指標或客戶結構資訊
5. 若使用者提供內容不足以拆成特定科目，請依主題自行整理出合理的分析面向，但不可捏造公司特定事實。
"""

EXPERT_KNOWLEDGE_ANALYSIS_USER_PROMPT_TEMPLATE = """請根據以下內容，產出可供後續 RAG 流程使用的專業分析指引。

專業知識內容：
{user_prompt}
"""


@expert_knowledge_analysis_router.post(
    "/api/expert-knowledge/generate-analysis",
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
async def generate_expert_knowledge_analysis(request: ExpertKnowledgeGenerateRequest):
    started_at = perf_counter()
    response_text, llm_prompt = generate_expert_knowledge_content(
        route_tag="expert_knowledge.generate_analysis",
        request_payload=request,
        system_prompt=EXPERT_KNOWLEDGE_ANALYSIS_SYSTEM_PROMPT,
        user_prompt_template=EXPERT_KNOWLEDGE_ANALYSIS_USER_PROMPT_TEMPLATE,
    )

    api_response = ExpertKnowledgeGenerateResponse(
        response=response_text,
        llm_prompt=llm_prompt,
    )
    print(
        f"[timing] expert_knowledge.generate_analysis.total took "
        f"{perf_counter() - started_at:.3f}s"
    )
    print(
        "[expert_knowledge.generate_analysis] response payload:\n"
        + dump_log_payload(api_response.model_dump())
    )
    return api_response
