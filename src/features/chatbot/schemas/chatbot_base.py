import json
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import AliasChoices, BaseModel, Field

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


def preserve_text(text: Any) -> str:
    return str(text or "").strip()


class ChatbotSettings(BaseModel):
    company: Optional[str] = None
    period: Optional[str] = None
    periodYear: Optional[str] = None
    periodQuarter: Optional[str] = None
    statementType: Optional[str] = None


class ReferenceSettings(BaseModel):
    useExpertKnowledge: bool = True
    useWarehouseData: bool = Field(
        default=True,
        validation_alias=AliasChoices("useWarehouseData", "useExternalKnowledge"),
    )
    useExternalData: bool = True

    model_config = {"populate_by_name": True}


class ChatbotMessage(BaseModel):
    role: str = Field(default="user")
    content: Any = ""


class AppliedExpertKnowledgeItem(BaseModel):
    title: str = ""
    dataSource: str = ""
    industry: str = ""
    companyLabel: str = ""
    anchorDescription: str = ""
    systemPrompt: str = ""
    createdAt: str = ""
    updatedAt: str = ""


class AppliedWarehouseDataItem(BaseModel):
    category: str = ""
    title: str = ""
    industry: str = ""
    companyLabel: str = ""
    companyPromptValue: str = ""
    source: str = ""
    url: str = ""
    summary: str = ""
    recordUpdatedAt: str = ""
    createdAt: str = ""
    updatedAt: str = ""


class ChatbotRequest(BaseModel):
    question: str
    company: Optional[str] = None
    period: Optional[str] = None
    settings: ChatbotSettings = Field(default_factory=ChatbotSettings)
    referenceSettings: ReferenceSettings = Field(default_factory=ReferenceSettings)
    conversationId: Optional[str] = None
    messages: list[ChatbotMessage] = Field(default_factory=list)
    appliedExpertKnowledge: list[AppliedExpertKnowledgeItem] = Field(default_factory=list)
    appliedWarehouseData: list[AppliedWarehouseDataItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("appliedWarehouseData", "appliedExternalKnowledge"),
    )
    show_intermediate_steps: bool = False

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "question": "string",
                "company": "string",
                "period": "string",
                "settings": {
                    "company": "string",
                    "period": "string",
                    "periodYear": "string",
                    "periodQuarter": "string",
                    "statementType": "string",
                },
                "referenceSettings": {
                    "useExpertKnowledge": True,
                    "useWarehouseData": True,
                    "useExternalData": True,
                },
                "conversationId": "string",
                "messages": [
                    {
                        "role": "user",
                        "content": "",
                    }
                ],
                "appliedExpertKnowledge": [
                    {
                        "title": "",
                        "dataSource": "",
                        "industry": "",
                        "companyLabel": "",
                        "anchorDescription": "",
                        "systemPrompt": "",
                        "createdAt": "",
                        "updatedAt": "",
                    }
                ],
                "appliedWarehouseData": [
                    {
                        "category": "",
                        "title": "",
                        "industry": "",
                        "companyLabel": "",
                        "companyPromptValue": "",
                        "source": "",
                        "url": "",
                        "summary": "",
                        "recordUpdatedAt": "",
                        "createdAt": "",
                        "updatedAt": "",
                    }
                ],
                "show_intermediate_steps": False,
            }
        },
    }


class ChatbotWithExternalRequest(ChatbotRequest):
    externalDataQueryText: str = ""
    externalDataDecision: Literal["", "adopted", "rejected"] = "adopted"

    model_config = {
        "json_schema_extra": {
            "example": {
                **ChatbotRequest.model_config["json_schema_extra"]["example"],
                "externalDataQueryText": "",
                "externalDataDecision": "adopted",
            }
        }
    }


class ChatbotDataSource(BaseModel):
    title: str = ""
    source: str = ""
    url: str = ""
    summary: str = ""


class UsedExpertKnowledgeItem(BaseModel):
    title: str = ""
    anchorDescription: str = ""
    systemPrompt: str = ""
    createdAt: str = ""
    updatedAt: str = ""


class AppliedExternalDataItem(BaseModel):
    source: str = ""
    response: str = ""


class ChatbotResponse(BaseModel):
    answer: str
    data_sources: list[ChatbotDataSource] = Field(default_factory=list)
    usedExpertKnowledge: list[UsedExpertKnowledgeItem] = Field(default_factory=list)
    externalDataQueryText: str = ""


class ChatbotWithExternalResponse(BaseModel):
    answer: str
    data_sources: list[ChatbotDataSource] = Field(default_factory=list)
    usedExpertKnowledge: list[UsedExpertKnowledgeItem] = Field(default_factory=list)
    appliedExternalData: list[AppliedExternalDataItem] = Field(default_factory=list)


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


def normalize_applied_expert_knowledge(items: list[Any]) -> list[dict[str, str]]:
    normalized_items: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            text = compact_text(item)
            if text:
                normalized_items.append(
                    {
                        "title": "",
                        "dataSource": "",
                        "industry": "",
                        "companyLabel": "",
                        "anchorDescription": "",
                        "systemPrompt": text,
                    }
                )
            continue

        title = compact_text(item.get("title"))
        data_source = compact_text(item.get("dataSource"))
        industry = compact_text(item.get("industry"))
        company_label = compact_text(item.get("companyLabel"))
        anchor_description = preserve_text(
            item.get("anchorDescription") or item.get("description")
        )
        system_prompt = preserve_text(item.get("systemPrompt"))
        created_at = compact_text(item.get("createdAt"))
        updated_at = compact_text(item.get("updatedAt"))
        if (
            title
            or data_source
            or industry
            or company_label
            or anchor_description
            or system_prompt
            or created_at
            or updated_at
        ):
            normalized_items.append(
                {
                    "title": title,
                    "dataSource": data_source,
                    "industry": industry,
                    "companyLabel": company_label,
                    "anchorDescription": anchor_description,
                    "systemPrompt": system_prompt,
                    "createdAt": created_at,
                    "updatedAt": updated_at,
                }
            )
    return normalized_items


def normalize_applied_warehouse_data(items: list[Any]) -> list[dict[str, str]]:
    normalized_items: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue

        category = compact_text(item.get("category"))
        title = compact_text(item.get("title"))
        industry = compact_text(item.get("industry"))
        company_label = compact_text(item.get("companyLabel"))
        company_prompt_value = compact_text(item.get("companyPromptValue"))
        source = compact_text(item.get("source"))
        url = compact_text(item.get("url"))
        summary = preserve_text(item.get("summary"))
        record_updated_at = compact_text(item.get("recordUpdatedAt"))
        created_at = compact_text(item.get("createdAt"))
        updated_at = compact_text(item.get("updatedAt"))

        if (
            category
            or title
            or industry
            or company_label
            or company_prompt_value
            or source
            or url
            or summary
            or record_updated_at
            or created_at
            or updated_at
        ):
            normalized_items.append(
                {
                    "category": category,
                    "title": title,
                    "industry": industry,
                    "companyLabel": company_label,
                    "companyPromptValue": company_prompt_value,
                    "source": source,
                    "url": url,
                    "summary": summary,
                    "recordUpdatedAt": record_updated_at,
                    "createdAt": created_at,
                    "updatedAt": updated_at,
                }
            )
    return normalized_items


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
                "source": STATEMENT_TYPE_LABELS.get(
                    statement_type, str(statement_type or "財務資料")
                ),
                "url": "",
                "summary": compact_text(f"{label} {value_text}".strip()),
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
                "source": STATEMENT_TYPE_LABELS.get(
                    fact.get("statement_type"),
                    str(fact.get("statement_type") or "財務資料"),
                ),
                "url": "",
                "summary": compact_text(
                    f"{fact.get('label') or fact.get('field_query') or fact.get('concept_name') or '未命名項目'} "
                    f"{format_value_with_unit(fact.get('value'), fact.get('unit'))}".strip()
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
                "source": "計算指標",
                "url": "",
                "summary": compact_text(
                    f"{metric.get('label') or '計算指標'} "
                    f"{format_number(metric.get('value'))}"
                ),
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
                "source": "排除或低可信資料",
                "url": "",
                "summary": compact_text(
                    f"{item.get('field_query') or selected_candidate.get('zh_tw') or selected_candidate.get('concept_name') or '未命名項目'} "
                    f"{item.get('reason') or '未提供最終回答引用'}"
                ),
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


def build_used_expert_knowledge(graph_answer: dict[str, Any]) -> list[dict[str, str]]:
    if not bool(graph_answer.get("use_expert_knowledge", True)):
        return []
    items = graph_answer.get("selected_applied_expert_knowledge")
    if items is None:
        items = graph_answer.get("applied_expert_knowledge") or []
    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "title": compact_text(item.get("title")),
                "anchorDescription": preserve_text(
                    item.get("anchorDescription") or item.get("description")
                ),
                "systemPrompt": preserve_text(item.get("systemPrompt")),
                "createdAt": compact_text(item.get("createdAt")),
                "updatedAt": compact_text(item.get("updatedAt")),
            }
        )
    return normalized_items


def build_used_warehouse_data(graph_answer: dict[str, Any]) -> list[dict[str, str]]:
    if not bool(graph_answer.get("use_warehouse_data", True)):
        return []
    items = graph_answer.get("selected_applied_warehouse_data")
    if items is None:
        items = graph_answer.get("applied_warehouse_data") or []
    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "category": compact_text(item.get("category")),
                "title": compact_text(item.get("title")),
                "industry": compact_text(item.get("industry")),
                "companyLabel": compact_text(item.get("companyLabel")),
                "companyPromptValue": compact_text(item.get("companyPromptValue")),
                "source": compact_text(item.get("source")),
                "url": compact_text(item.get("url")),
                "summary": preserve_text(item.get("summary")),
                "recordUpdatedAt": compact_text(item.get("recordUpdatedAt")),
                "createdAt": compact_text(item.get("createdAt")),
                "updatedAt": compact_text(item.get("updatedAt")),
            }
        )
    return normalized_items


def build_applied_external_data(graph_answer: dict[str, Any]) -> list[dict[str, str]]:
    if not bool(graph_answer.get("use_external_data", True)):
        return []
    external_data_result = graph_answer.get("external_data_result") or {}
    if str(external_data_result.get("decision") or "").strip().lower() != "adopted":
        return []

    response_text = str(graph_answer.get("external_data_response") or "").strip()
    if not response_text:
        return []
    source = preserve_text(graph_answer.get("external_data_query_text")) or "AI Agent 外部資料查詢"

    return [
        {
            "source": source,
            "response": response_text,
        }
    ]


def build_graph_input(
    request: ChatbotRequest | ChatbotWithExternalRequest,
    *,
    request_source: str,
) -> dict[str, Any]:
    graph_input = {
        "messages": build_langchain_messages(request.messages, request.question),
        "user_input": build_enriched_user_input(request),
        "request_source": request_source,
        "use_expert_knowledge": request.referenceSettings.useExpertKnowledge,
        "use_warehouse_data": request.referenceSettings.useWarehouseData,
        "use_external_data": request.referenceSettings.useExternalData,
        "applied_expert_knowledge": normalize_applied_expert_knowledge(
            request.appliedExpertKnowledge
        ),
        "applied_warehouse_data": normalize_applied_warehouse_data(
            request.appliedWarehouseData
        ),
    }

    if request_source == "chatbot-with-external":
        external_data_decision = compact_text(request.externalDataDecision).lower()
        if external_data_decision:
            graph_input["external_data_decision"] = external_data_decision

        external_data_query_text = preserve_text(request.externalDataQueryText)
        if external_data_query_text:
            graph_input["external_data_query_text"] = external_data_query_text

    return graph_input


def build_graph_config(
    request: ChatbotRequest | ChatbotWithExternalRequest,
    *,
    request_source: str,
) -> dict[str, Any]:
    """Build LangGraph runtime config, including LangSmith trace attributes."""
    config: dict[str, Any] = {
        "run_name": f"aitc-{request_source}",
        "tags": ["aitc-credit-investigation", request_source],
        "metadata": {
            "request_source": request_source,
            "use_expert_knowledge": request.referenceSettings.useExpertKnowledge,
            "use_warehouse_data": request.referenceSettings.useWarehouseData,
            "use_external_data": request.referenceSettings.useExternalData,
        },
    }
    if request.conversationId:
        config["configurable"] = {"thread_id": request.conversationId}
    return config


def build_chatbot_response(
    graph_answer: dict[str, Any],
    *,
    include_external_data_query_text: bool = True,
    include_applied_external_data: bool = False,
) -> dict[str, Any]:
    data_sources = build_api_data_sources(graph_answer)
    used_expert_knowledge = build_used_expert_knowledge(graph_answer)

    print("[chatbot] response data_sources:\n" + dump_log_payload(data_sources))
    print("[chatbot] used expert knowledge:\n" + dump_log_payload(used_expert_knowledge))

    response = {
        "answer": graph_answer["answer"],
        "data_sources": data_sources,
        "usedExpertKnowledge": used_expert_knowledge,
    }
    if include_external_data_query_text:
        response["externalDataQueryText"] = preserve_text(
            graph_answer.get("external_data_query_text")
        )
    if include_applied_external_data:
        response["appliedExternalData"] = build_applied_external_data(graph_answer)
    return response
