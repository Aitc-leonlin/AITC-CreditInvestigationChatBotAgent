import json
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any, Optional

from fastapi import APIRouter
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field

# import graph
from src.agent.graph import graph

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
