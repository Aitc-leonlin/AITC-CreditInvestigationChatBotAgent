import json
import re
from time import perf_counter

from pydantic import BaseModel, Field

from src.providers.chat_openAI_provider import chat_model
from src.types.langgraph_state_types import OverallState


class ExpertKnowledgeSelectionSchema(BaseModel):
    needs_expert_knowledge: bool = Field(
        description="這個問題是否需要引用專家知識作為分析佐證"
    )
    selected_indexes: list[int] = Field(
        default_factory=list,
        description="需要參考的 appliedExpertKnowledge 項目索引，從 1 開始",
    )
    reason: str = Field(
        default="",
        description="簡短說明為什麼需要或不需要引用專家知識",
    )


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


def normalize_match_text(text: str) -> str:
    return str(text or "").strip().lower().replace("台", "臺")


def build_match_tokens(text: str) -> list[str]:
    raw_parts = re.split(r"[/|,，、()（）\-\s]+", str(text or ""))
    tokens = []
    seen = set()
    for part in raw_parts:
        normalized = normalize_match_text(part)
        if not normalized:
            continue
        if len(normalized) < 2 and not normalized.isdigit():
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens


def metadata_matches_context(
    *,
    industry: str,
    company_label: str,
    context_text: str,
    company_identifiers: list[str],
) -> bool:
    normalized_context = normalize_match_text(context_text)
    normalized_company_identifiers = [normalize_match_text(item) for item in company_identifiers if item]

    if industry:
        industry_tokens = build_match_tokens(industry)
        if industry_tokens and not any(token in normalized_context for token in industry_tokens):
            return False

    if company_label:
        company_tokens = build_match_tokens(company_label)
        if company_tokens:
            has_company_match = any(token in normalized_context for token in company_tokens) or any(
                token in identifier or identifier in token
                for token in company_tokens
                for identifier in normalized_company_identifiers
                if identifier
            )
            if not has_company_match:
                return False

    return True


def select_applied_expert_knowledge(state: OverallState) -> OverallState:
    started_at = perf_counter()
    if not bool(state.get("use_expert_knowledge", True)):
        print("[select_applied_expert_knowledge] skipped: use_expert_knowledge is false")
        return {
            **state,
            "needs_expert_knowledge": False,
            "selected_applied_expert_knowledge": [],
            "expert_knowledge_selection_result": {
                "needs_expert_knowledge": False,
                "selected_indexes": [],
                "reason": "Skipped because referenceSettings.useExpertKnowledge is false.",
            },
        }

    expert_knowledge_items = state.get("applied_expert_knowledge") or []
    if not expert_knowledge_items:
        print("[select_applied_expert_knowledge] no applied expert knowledge provided")
        return {
            **state,
            "needs_expert_knowledge": False,
            "selected_applied_expert_knowledge": [],
            "expert_knowledge_selection_result": {
                "needs_expert_knowledge": False,
                "selected_indexes": [],
                "reason": "No applied expert knowledge provided.",
            },
        }

    question = state.get("rephrased_question") or state.get("user_input") or ""
    semantic_plan = state.get("semantic_plan") or {}
    analysis_goal = sanitize_llm_text(semantic_plan.get("analysis_goal") or "")
    requirements = semantic_plan.get("requirements") or []
    company_identifiers = semantic_plan.get("company_identifiers") or []
    if not company_identifiers and semantic_plan.get("company_identifier"):
        company_identifiers = [semantic_plan.get("company_identifier")]
    purpose_lines = []
    purpose_texts = []
    for index, requirement in enumerate(requirements, start=1):
        purpose = sanitize_llm_text(requirement.get("purpose") or "")
        field_query = requirement.get("field_query") or []
        if purpose or field_query:
            if purpose:
                purpose_texts.append(purpose)
            purpose_lines.append(
                json.dumps(
                    {
                        "index": index,
                        "field_query": field_query,
                        "purpose": purpose,
                    },
                    ensure_ascii=False,
                )
            )
    sanitized_question = sanitize_llm_text(question)
    context_text = "\n".join(
        [
            sanitized_question,
            analysis_goal,
            "\n".join(purpose_texts),
            " ".join(str(item) for item in company_identifiers if item),
        ]
    )

    candidate_lines = []
    filtered_candidate_records = []
    for index, item in enumerate(expert_knowledge_items, start=1):
        # industry = str(item.get("industry") or "").strip()
        # company_label = str(item.get("companyLabel") or "").strip()
        # if not metadata_matches_context(
        #     industry=industry,
        #     company_label=company_label,
        #     context_text=context_text,
        #     company_identifiers=company_identifiers,
        # ):
        #     continue
        filtered_candidate_records.append((index, item))

    if not filtered_candidate_records:
        print("[select_applied_expert_knowledge] all candidates filtered out by industry/companyLabel")
        return {
            **state,
            "needs_expert_knowledge": False,
            "selected_applied_expert_knowledge": [],
            "expert_knowledge_selection_result": {
                "needs_expert_knowledge": False,
                "selected_indexes": [],
                "reason": "All candidates were filtered out by industry/companyLabel relevance.",
            },
        }

    for index, item in filtered_candidate_records:
        candidate_lines.append(
            json.dumps(
                {
                    "index": index,
                    "title": item.get("title", ""),
                    "dataSource": item.get("dataSource", ""),
                    "industry": item.get("industry", ""),
                    "companyLabel": item.get("companyLabel", ""),
                    "anchorDescription": item.get("anchorDescription", ""),
                },
                ensure_ascii=False,
            )
        )

    prompt = f"""
你是授信與財務分析流程中的專家知識篩選器。

你的任務是判斷：根據 LLM 已整理出的問題分析目的，是否需要參考前端提供的 appliedExpertKnowledge 作為分析佐證。

判斷規則：
1. 主要根據 analysis_goal 與 requirements 內的 purpose 來判斷是否相關。
2. title 只能當作識別用途，不可拿來當主要判斷依據。
3. systemPrompt 在這一步不可用來判斷是否匹配；它只會在後續真的被選中後才提供給最終回答模型使用。
4. 只能根據每個條目的 anchorDescription 與 analysis_goal / purpose 的語意關聯來判斷是否相關。
5. 若問題涉及授信判斷、風險分析、產業脈絡、信用徵審、還款能力、擔保品、決策建議、異常財務變化原因判讀，且 anchorDescription 與分析目的明顯相關，則可選入。
6. 若問題只是單純查數字、定義解釋，或 anchorDescription 與 analysis_goal / purpose 無明顯關聯，則不要選入。
7. 原始使用者問題只可作為輔助理解上下文，不可凌駕 analysis_goal 與 purpose。
8. 可選 0 個、1 個或多個條目，但只選真正相關的。

請輸出 JSON：
{{
  "needs_expert_knowledge": true,
  "selected_indexes": [1, 2],
  "reason": "..."
}}

原始使用者問題：
{sanitized_question}

analysis_goal：
{analysis_goal or "無"}

requirements / purpose：
{chr(10).join(purpose_lines) if purpose_lines else "無"}

候選專家知識：
{chr(10).join(candidate_lines)}
""".strip()

    print("[select_applied_expert_knowledge] prompt:\n" + prompt)
    structured_llm = chat_model.with_structured_output(ExpertKnowledgeSelectionSchema)

    try:
        selection = structured_llm.invoke(prompt).model_dump()
    except Exception as exc:
        print(f"[select_applied_expert_knowledge] structured output failed, fallback to none: {exc}")
        selection = {
            "needs_expert_knowledge": False,
            "selected_indexes": [],
            "reason": f"LLM selection failed: {exc}",
        }

    selected_indexes = selection.get("selected_indexes") or []
    normalized_indexes = []
    for index in selected_indexes:
        try:
            numeric_index = int(index)
        except (TypeError, ValueError):
            continue
        valid_indexes = {original_index for original_index, _ in filtered_candidate_records}
        if numeric_index in valid_indexes and numeric_index not in normalized_indexes:
            normalized_indexes.append(numeric_index)

    selected_items = [expert_knowledge_items[index - 1] for index in normalized_indexes]
    needs_expert_knowledge = bool(selection.get("needs_expert_knowledge")) and bool(selected_items)
    if not needs_expert_knowledge:
        selected_items = []
        normalized_indexes = []

    selection["needs_expert_knowledge"] = needs_expert_knowledge
    selection["selected_indexes"] = normalized_indexes

    print(
        "[select_applied_expert_knowledge] result:\n"
        + json.dumps(selection, ensure_ascii=False, indent=2)
    )
    print(
        "[select_applied_expert_knowledge] selected items:\n"
        + json.dumps(selected_items, ensure_ascii=False, indent=2)
    )
    print(
        f"[timing] select_applied_expert_knowledge took {perf_counter() - started_at:.3f}s"
    )

    return {
        **state,
        "needs_expert_knowledge": needs_expert_knowledge,
        "selected_applied_expert_knowledge": selected_items,
        "expert_knowledge_selection_result": selection,
    }
