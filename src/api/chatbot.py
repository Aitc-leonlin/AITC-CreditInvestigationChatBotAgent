import json
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# import graph
from src.agent.graph import graph
from src.providers.chat_openAI_provider import chat_model, get_message_text

chatbot_router = APIRouter(tags=["chatbot"])

STATEMENT_TYPE_LABELS = {
    "balance_sheet": "資產負債表",
    "comprehensive_income_statement": "綜合損益表",
    "statement_of_cash_flows": "現金流量表",
}


def dump_log_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def format_number(value: Any) -> str:
    if value is None:
        return ""

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)

    if decimal_value == decimal_value.to_integral():
        return f"{int(decimal_value):,}"
    return format(decimal_value.normalize(), ",f").rstrip("0").rstrip(".")


def format_value_with_unit(value: Any, unit: Any) -> str:
    value_text = format_number(value)
    unit_text = str(unit or "").strip()
    if unit_text:
        return f"{value_text} {unit_text}".strip()
    return value_text


def build_period_title(year: Any, quarter: Any, company_name: Any = None) -> str:
    year_text = str(year or "").strip()
    company_text = str(company_name or "").strip()
    if quarter in (1, 2, 3, 4):
        title = f"{year_text} 年 Q{quarter} 財報"
    else:
        title = f"{year_text} 財報資料" if year_text else "財報資料"
    if company_text:
        return f"{company_text} {title}"
    return title


def compact_text(text: Any) -> str:
    return " ".join(str(text or "").split())


class ChatbotSettings(BaseModel):
    company: Optional[str] = None
    period: Optional[str] = None
    periodYear: Optional[str] = None
    periodQuarter: Optional[str] = None
    statementType: Optional[str] = None


class ChatbotMessage(BaseModel):
    role: str = Field(default="user")
    content: Any = ""


class ChatbotRequest(BaseModel):
    question: str
    company: Optional[str] = None
    period: Optional[str] = None
    settings: ChatbotSettings = Field(default_factory=ChatbotSettings)
    conversationId: Optional[str] = None
    messages: list[ChatbotMessage] = Field(default_factory=list)


class ExpertKnowledgeGenerateAnchorRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        alias="PROMPT",
        description="前端提供的專業知識錨定點描述或提示內容",
    )

    model_config = {"populate_by_name": True}


class ExpertKnowledgeGenerateAnchorResponse(BaseModel):
    response: str
    llm_prompt: str


class ExpertKnowledgeGenerateAnalysisRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        alias="PROMPT",
        description="前端提供的專業知識分析指引描述或提示內容",
    )

    model_config = {"populate_by_name": True}


class ExpertKnowledgeGenerateAnalysisResponse(BaseModel):
    response: str
    llm_prompt: str


EXPERT_KNOWLEDGE_SYSTEM_PROMPT = """你是企業授信與產業研究方法設計專家。

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

EXPERT_KNOWLEDGE_USER_PROMPT_TEMPLATE = """請根據以下內容，產出一段讓 AI Agent 判斷「何時應採用這個專業知識錨定點」的指令句。

錨定點內容：
{user_prompt}
"""


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


def stringify_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text).strip())
            elif item is not None:
                parts.append(str(item).strip())
        return " ".join(part for part in parts if part)
    return str(content or "").strip()


def build_langchain_messages(messages: list[ChatbotMessage], fallback_question: str) -> list[BaseMessage]:
    history: list[BaseMessage] = []
    for item in messages:
        content = stringify_message_content(item.content)
        if not content:
            continue
        role = str(item.role or "").strip().lower()
        if role in {"assistant", "ai", "bot"}:
            history.append(AIMessage(content=content))
        else:
            history.append(HumanMessage(content=content))

    if not history:
        history.append(HumanMessage(content=fallback_question))
    return history


def build_enriched_user_input(request: ChatbotRequest) -> str:
    lines = [f"問題：{request.question.strip()}"]

    if request.company:
        lines.append(f"公司：{request.company.strip()}")
    if request.period:
        lines.append(f"期間：{request.period.strip()}")

    settings_lines = []
    if request.settings.company:
        settings_lines.append(f"company={request.settings.company.strip()}")
    if request.settings.period:
        settings_lines.append(f"period={request.settings.period.strip()}")
    if request.settings.periodYear:
        settings_lines.append(f"periodYear={request.settings.periodYear.strip()}")
    if request.settings.periodQuarter:
        settings_lines.append(f"periodQuarter={request.settings.periodQuarter.strip()}")
    if request.settings.statementType:
        settings_lines.append(f"statementType={request.settings.statementType.strip()}")
    if settings_lines:
        lines.append("指定設定：" + "，".join(settings_lines))

    return "\n".join(lines)


def build_exact_query_data_sources(reference_data: dict[str, Any]) -> list[dict[str, str]]:
    schema = reference_data.get("schema") or {}
    company_name = schema.get("companyName")
    results = reference_data.get("resolved_field_results") or []
    data_sources = []

    for item in results:
        answer_data = item.get("answer_data") or {}
        selected_candidate = item.get("selected_candidate") or {}
        statement_type = (
            selected_candidate.get("statement_type")
            or answer_data.get("statement_type")
        )
        label = (
            answer_data.get("zh_name")
            or selected_candidate.get("zh_tw")
            or item.get("field")
            or answer_data.get("en_name")
            or selected_candidate.get("en")
            or selected_candidate.get("concept_name")
            or "未命名欄位"
        )
        value = (
            answer_data.get("value_numeric")
            if answer_data.get("value_numeric") is not None
            else answer_data.get("value_text") or answer_data.get("value")
        )
        value_text = format_value_with_unit(value, answer_data.get("unit_id"))
        year = answer_data.get("year") or schema.get("period", {}).get("year")
        quarter_text = answer_data.get("quarter") or ""
        quarter_number = None
        if isinstance(quarter_text, str) and quarter_text.startswith("Q"):
            try:
                quarter_number = int(quarter_text[1:])
            except ValueError:
                quarter_number = None

        data_sources.append(
            {
                "title": build_period_title(year, quarter_number, company_name),
                "content": compact_text(f"{label} {value_text}".strip()),
                "reference": STATEMENT_TYPE_LABELS.get(
                    statement_type, str(statement_type or "財務資料")
                ),
            }
        )

    return data_sources


def build_semantic_data_sources(llm_evidence: dict[str, Any]) -> list[dict[str, str]]:
    company = llm_evidence.get("company") or {}
    company_name = company.get("name")
    data_sources = []

    for fact in llm_evidence.get("facts") or []:
        period = fact.get("period") or {}
        data_sources.append(
            {
                "title": build_period_title(
                    period.get("year"),
                    period.get("quarter"),
                    company_name,
                ),
                "content": compact_text(
                    f"{fact.get('label') or fact.get('field_query') or fact.get('concept_name') or '未命名項目'} "
                    f"{format_value_with_unit(fact.get('value'), fact.get('unit'))}".strip()
                ),
                "reference": STATEMENT_TYPE_LABELS.get(
                    fact.get("statement_type"),
                    str(fact.get("statement_type") or "財務資料"),
                ),
            }
        )

    summary_title = build_period_title(
        (llm_evidence.get("periods") or [{}])[0].get("year"),
        (llm_evidence.get("periods") or [{}])[0].get("quarter"),
        company_name,
    )
    for metric in llm_evidence.get("computed_metrics") or []:
        data_sources.append(
            {
                "title": summary_title,
                "content": compact_text(
                    f"{metric.get('label') or '計算指標'} "
                    f"{format_number(metric.get('value'))}"
                ),
                "reference": "計算指標",
            }
        )

    for item in llm_evidence.get("excluded_or_low_confidence_facts") or []:
        selected_candidate = item.get("selected_candidate") or {}
        period = item.get("period") or {}
        data_sources.append(
            {
                "title": build_period_title(
                    period.get("year"),
                    period.get("quarter"),
                    company_name,
                ),
                "content": compact_text(
                    f"{item.get('field_query') or selected_candidate.get('zh_tw') or selected_candidate.get('concept_name') or '未命名項目'} "
                    f"{item.get('reason') or '未提供最終回答引用'}"
                ),
                "reference": "排除或低可信資料",
            }
        )

    return data_sources


def build_api_data_sources(graph_answer: dict[str, Any]) -> list[dict[str, str]]:
    reference_data = graph_answer.get("reference_data")
    if not isinstance(reference_data, dict):
        return []

    if reference_data.get("resolved_field_results"):
        return build_exact_query_data_sources(reference_data)

    llm_evidence = reference_data.get("llm_evidence")
    if isinstance(llm_evidence, dict):
        return build_semantic_data_sources(llm_evidence)

    return []


def build_llm_prompt_text(formatted_messages: list[BaseMessage]) -> str:
    return "\n\n".join(
        f"[{message.type}] {getattr(message, 'content', '')}"
        for message in formatted_messages
    )


def generate_expert_knowledge_content(
    *,
    route_tag: str,
    request_payload: BaseModel,
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


@chatbot_router.post("/chatbot")
async def get_chatbot_answer(request: ChatbotRequest):
    started_at = perf_counter()
    user_input = build_enriched_user_input(request)
    graph_input = {
        "messages": build_langchain_messages(request.messages, request.question),
        "user_input": user_input,
    }
    graph_config = (
        {"configurable": {"thread_id": request.conversationId}}
        if request.conversationId
        else None
    )
    print("[chatbot] request payload:\n" + dump_log_payload(request.model_dump()))
    print("[chatbot] graph input:\n" + dump_log_payload(graph_input))
    graph_answer = (
        graph.invoke(graph_input, config=graph_config)
        if graph_config
        else graph.invoke(graph_input)
    )
    print(f"[timing] chatbot.total_graph_to_final_answer took {perf_counter() - started_at:.3f}s")
    data_sources = build_api_data_sources(graph_answer)
    print("[chatbot] response data_sources:\n" + dump_log_payload(data_sources))

    return {
        "answer": graph_answer["answer"],
        "data_sources": data_sources,
    }


@chatbot_router.post(
    "/api/expert_knowledge/generate_anchor",
    response_model=ExpertKnowledgeGenerateAnchorResponse,
)
async def generate_expert_knowledge_anchor(request: ExpertKnowledgeGenerateAnchorRequest):
    started_at = perf_counter()
    response_text, llm_prompt = generate_expert_knowledge_content(
        route_tag="expert_knowledge.generate_anchor",
        request_payload=request,
        system_prompt=EXPERT_KNOWLEDGE_SYSTEM_PROMPT,
        user_prompt_template=EXPERT_KNOWLEDGE_USER_PROMPT_TEMPLATE,
    )

    api_response = ExpertKnowledgeGenerateAnchorResponse(
        response=response_text,
        llm_prompt=llm_prompt,
    )
    print(
        f"[timing] expert_knowledge.generate_anchor.total took {perf_counter() - started_at:.3f}s"
    )
    print(
        "[expert_knowledge.generate_anchor] response payload:\n"
        + dump_log_payload(api_response.model_dump())
    )
    return api_response


@chatbot_router.post(
    "/api/expert_knowledge/generate_analysis",
    response_model=ExpertKnowledgeGenerateAnalysisResponse,
)
async def generate_expert_knowledge_analysis(request: ExpertKnowledgeGenerateAnalysisRequest):
    started_at = perf_counter()
    response_text, llm_prompt = generate_expert_knowledge_content(
        route_tag="expert_knowledge.generate_analysis",
        request_payload=request,
        system_prompt=EXPERT_KNOWLEDGE_ANALYSIS_SYSTEM_PROMPT,
        user_prompt_template=EXPERT_KNOWLEDGE_ANALYSIS_USER_PROMPT_TEMPLATE,
    )

    api_response = ExpertKnowledgeGenerateAnalysisResponse(
        response=response_text,
        llm_prompt=llm_prompt,
    )
    print(
        f"[timing] expert_knowledge.generate_analysis.total took {perf_counter() - started_at:.3f}s"
    )
    print(
        "[expert_knowledge.generate_analysis] response payload:\n"
        + dump_log_payload(api_response.model_dump())
    )
    return api_response
