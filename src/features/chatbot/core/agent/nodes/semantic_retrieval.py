import json
import logging
import re
import sqlite3
from time import perf_counter
from typing import Dict, List, Literal, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, field_validator

from src.features.chatbot.core.mappings.company_stock_code_array import CompanyStockCodeArray
from src.features.chatbot.core.providers.chat_openAI_provider import chat_model, get_message_text
from src.features.chatbot.services.account_title_matcher import find_candidates
from src.shared.database.db_path import resolve_sqlite_db_path
from src.features.chatbot.models.langgraph_state_types import OverallState


logger = logging.getLogger(__name__)
DB_PATH = resolve_sqlite_db_path()
VALID_STATEMENT_TYPES = {
    "balance_sheet",
    "comprehensive_income_statement",
    "statement_of_cash_flows",
}
METADATA_FIELD_PREFIXES = (
    "tifrs-notes_Company",
    "tifrs-notes_Year",
    "tifrs-notes_Quarter",
    "tifrs-notes_Report",
    "tifrs-notes_Market",
    "tifrs-notes_Industry",
)
def build_expert_knowledge_prompt_section(state: OverallState) -> str:
    if not bool(state.get("use_expert_knowledge", True)):
        return "無"
    expert_knowledge_items = state.get("selected_applied_expert_knowledge")
    if expert_knowledge_items is None:
        expert_knowledge_items = state.get("applied_expert_knowledge") or []
    if not expert_knowledge_items:
        return "無"

    lines = []
    for index, item in enumerate(expert_knowledge_items, start=1):
        if isinstance(item, dict):
            system_prompt = str(item.get("systemPrompt") or "").strip()
        else:
            system_prompt = str(item or "").strip()

        if system_prompt:
            lines.append(f"{index}. {system_prompt}")
    return "\n".join(lines)


def build_warehouse_data_prompt_section(state: OverallState) -> str:
    if not bool(state.get("use_warehouse_data", True)):
        return "無"
    warehouse_data_items = state.get("selected_applied_warehouse_data")
    if not warehouse_data_items:
        warehouse_data_items = state.get("applied_warehouse_data") or []
    if not warehouse_data_items:
        return "無"

    lines = []
    for index, item in enumerate(warehouse_data_items, start=1):
        if not isinstance(item, dict):
            continue

        metadata_parts = []
        for label, key in (
            ("category", "category"),
            ("title", "title"),
            ("industry", "industry"),
            ("companyLabel", "companyLabel"),
            ("companyPromptValue", "companyPromptValue"),
            ("source", "source"),
            ("url", "url"),
            ("recordUpdatedAt", "recordUpdatedAt"),
            ("createdAt", "createdAt"),
            ("updatedAt", "updatedAt"),
        ):
            value = str(item.get(key) or "").strip()
            if value:
                metadata_parts.append(f"{label}={value}")

        summary = str(item.get("summary") or "").strip()
        if not metadata_parts and not summary:
            continue

        lines.append(f"{index}. {'; '.join(metadata_parts)}")
        if summary:
            lines.append(f"   summary: {summary}")

    return "\n".join(lines) if lines else "無"


def build_external_data_prompt_section(state: OverallState) -> str:
    if not bool(state.get("use_external_data", True)):
        return "無"
    query_text = str(state.get("external_data_query_text") or "").strip()
    response_text = str(state.get("external_data_response") or "").strip()
    if not query_text and not response_text:
        return "無"

    lines = []
    if query_text:
        lines.append(f"查詢主題: {query_text}")
    if response_text:
        lines.append("查詢結果:")
        lines.append(response_text)
    return "\n".join(lines)
class PeriodItem(BaseModel):
    year: int = Field(..., description="西元年")
    quarter: Optional[int] = Field(None, description="季度，1 到 4；若是全年或未明確指定，可為空")


class RequirementDraft(BaseModel):
    field_query: List[str] = Field(
        default_factory=list,
        description="要查的財務欄位陣列，例如 ['營業收入', '營收']、['資產總額']、['本期淨利', '稅後淨利']",
    )
    statement_type: str = Field(
        ...,
        description="只可填 balance_sheet、comprehensive_income_statement、statement_of_cash_flows",
    )
    periods: List[PeriodItem] = Field(default_factory=list, description="此欄位需要查的期間")
    purpose: str = Field(..., description="查這些數據是為了回答什麼，例如比較、趨勢、計算差異")

    @field_validator("field_query", mode="before")
    @classmethod
    def normalize_field_query(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []


class SemanticPlanDraft(BaseModel):
    company_identifier: str = Field(..., description="公司代碼、公司全名、簡稱或英文名")
    company_identifiers: List[str] = Field(
        default_factory=list,
        description="可用於本地公司清單比對的公司識別候選值，例如公司代碼、公司全名、簡稱、英文名",
    )
    analysis_goal: str = Field(..., description="對問題的高層理解，例如比較營收趨勢、分析獲利變化")
    requirements: List[RequirementDraft] = Field(default_factory=list, description="回答所需的資料清單")

    @field_validator("company_identifiers", mode="before")
    @classmethod
    def normalize_company_identifiers(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []


class CandidateChoiceItem(BaseModel):
    field_query: str = Field(..., description="對應的查詢欄位")
    concept_name: str = Field(..., description="選中的 concept_name")


class CandidateChoiceBatch(BaseModel):
    choices: List[CandidateChoiceItem] = Field(default_factory=list, description="每個 field_query 對應的最佳候選")


# 將 log payload 轉成可讀 JSON 字串，避免直接印 dict 時不易閱讀。
def dump_log_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def quote_sql_debug_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def render_sql_debug_preview(query: str, params: tuple) -> str:
    rendered = query
    for value in params:
        rendered = rendered.replace("?", quote_sql_debug_value(value), 1)
    return rendered


# 清理要送進 LLM 的文字，避免非法控制字元導致 API request 失敗。
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


def normalize_periods(periods: List[Dict]) -> List[Dict]:
    normalized_periods = []
    seen = set()
    for period in periods or []:
        if not isinstance(period, dict):
            continue
        year = period.get("year")
        quarter = period.get("quarter")
        try:
            year = int(year)
        except (TypeError, ValueError):
            continue
        try:
            quarter = int(quarter) if quarter is not None else None
        except (TypeError, ValueError):
            quarter = None
        if quarter not in {1, 2, 3, 4}:
            quarter = None
        key = (year, quarter)
        if key in seen:
            continue
        seen.add(key)
        normalized_periods.append({"year": year, "quarter": quarter})
    return normalized_periods


def normalize_semantic_plan(plan: Dict) -> Dict:
    normalized_plan = dict(plan or {})
    company_identifiers = normalized_plan.get("company_identifiers") or []
    if isinstance(company_identifiers, str):
        company_identifiers = [company_identifiers]
    if not isinstance(company_identifiers, list):
        company_identifiers = []
    company_identifier = normalized_plan.get("company_identifier")
    if company_identifier:
        company_identifiers.insert(0, company_identifier)
    normalized_company_identifiers = []
    seen_company_identifiers = set()
    for item in company_identifiers:
        text = str(item).strip()
        if not text or text in seen_company_identifiers:
            continue
        seen_company_identifiers.add(text)
        normalized_company_identifiers.append(text)
    normalized_plan["company_identifiers"] = normalized_company_identifiers

    normalized_requirements = []
    for requirement in normalized_plan.get("requirements", []):
        if not isinstance(requirement, dict):
            continue
        normalized_requirement = dict(requirement)
        normalized_requirement["periods"] = normalize_periods(requirement.get("periods", []))
        normalized_requirements.append(normalized_requirement)
    normalized_plan["requirements"] = normalized_requirements
    return normalized_plan


def build_company_maps() -> tuple[Dict[str, Dict], Dict[str, Dict]]:
    code_to_company_map = {}
    name_to_company_map = {}
    for item in CompanyStockCodeArray:
        code_to_company_map[item["companyCode"]] = item
        for key in ["companyName", "shortName", "englishName"]:
            value = item.get(key)
            if value:
                name_to_company_map[value] = item
    return code_to_company_map, name_to_company_map


def normalize_company_text(value: object) -> str:
    return str(value or "").strip().lower().replace("台", "臺")


def build_company_identifier_candidates(identifiers: object) -> List[str]:
    raw_identifiers = identifiers if isinstance(identifiers, list) else [identifiers]
    candidates = []
    seen = set()

    def append_candidate(value: object) -> None:
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        candidates.append(text)

    for identifier in raw_identifiers:
        text = str(identifier or "").strip()
        if not text:
            continue
        append_candidate(text)
        for code in re.findall(r"\b\d{4,6}\b", text):
            append_candidate(code)
        for part in re.split(r"[(),，、/|;；]", text):
            append_candidate(part)
            if "台" in part:
                append_candidate(part.replace("台", "臺"))
            if "臺" in part:
                append_candidate(part.replace("臺", "台"))

    return candidates


def resolve_company(identifiers: object) -> Optional[Dict]:
    candidates = build_company_identifier_candidates(identifiers)
    if not candidates:
        return None

    code_to_company_map, name_to_company_map = build_company_maps()
    for identifier in candidates:
        direct = code_to_company_map.get(identifier) or name_to_company_map.get(identifier)
        if direct:
            return direct

    for identifier in candidates:
        normalized_identifier = normalize_company_text(identifier)
        if not normalized_identifier:
            continue
        for item in CompanyStockCodeArray:
            normalized_values = [
                normalize_company_text(value)
                for value in item.values()
                if isinstance(value, str) and value.strip()
            ]
            if any(normalized_identifier == value for value in normalized_values):
                return item
            if len(normalized_identifier) >= 2 and any(
                normalized_identifier in value or value in normalized_identifier
                for value in normalized_values
            ):
                return item
    return None


def list_company_reports(company_code: str) -> List[Dict]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(
            """
            SELECT report_id, company_code, year, quarter, report_scope, industry_type, module, period_end
            FROM report_instance
            WHERE company_code = ?
            ORDER BY year DESC, quarter DESC
            """,
            (company_code,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def filter_candidates(candidates: List[Dict]) -> List[Dict]:
    filtered = []
    for candidate in candidates:
        concept_name = candidate.get("concept_name") or ""
        if any(concept_name.startswith(prefix) for prefix in METADATA_FIELD_PREFIXES):
            continue
        filtered.append(candidate)
    return filtered


def dedupe_candidates(candidates: List[Dict], limit: int) -> List[Dict]:
    seen = {}
    for candidate in candidates:
        key = candidate.get("concept_name")
        if key and key not in seen:
            seen[key] = candidate
    items = list(seen.values())
    items.sort(
        key=lambda item: (
            -(item.get("score") or 0),
            item.get("statement_type") or "",
            item.get("code") or "",
            item.get("concept_name") or "",
        )
    )
    return items[:limit]


# 依 requirement 提供的多個 field_query 與報表類型，跨 statement 搜集候選欄位並去重排序。
def search_candidates_across_statements(
    field_queries: List[str],
    statement_type: str,
    limit: int,
    company_code: Optional[str] = None,
) -> List[Dict]:
    target_types = (
        [statement_type]
        if statement_type in VALID_STATEMENT_TYPES
        else sorted(VALID_STATEMENT_TYPES)
    )
    collected: List[Dict] = []
    normalized_queries = [query.strip() for query in field_queries if isinstance(query, str) and query.strip()]
    for current_statement_type in target_types:
        for field_query in normalized_queries:
            for item in filter_candidates(
                find_candidates(
                    field_query,
                    current_statement_type,
                    limit=limit,
                    company_code=company_code,
                )
            ):
                enriched = dict(item)
                enriched["statement_type"] = current_statement_type
                enriched["matched_query"] = field_query
                collected.append(enriched)
    return dedupe_candidates(collected, limit)


def fetch_financial_value(
    company_code: str,
    year: int,
    quarter: Optional[int],
    statement_type: str,
    concept_id: str,
) -> Optional[Dict]:
    if statement_type not in VALID_STATEMENT_TYPES:
        return None
    effective_quarter = 4 if quarter is None else quarter

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        query = """
            SELECT
                ri.report_id,
                ri.company_code,
                ri.year,
                ri.quarter,
                ri.report_scope,
                ri.industry_type,
                ri.period_end AS report_period_end,
                fd.field_id,
                fd.canonical_name,
                fd.zh_name,
                fd.en_name,
                fd.statement_type,
                fmv.concept_id,
                fmv.value,
                xf.value_numeric,
                xf.value_text,
                xf.unit_id,
                xf.instant_date,
                xf.period_start,
                xf.period_end,
                xf.segment_json
            FROM financial_metric_value AS fmv
            JOIN report_instance AS ri
              ON ri.report_id = fmv.report_id
            LEFT JOIN field_dictionary AS fd
              ON fd.field_id = fmv.field_id
            LEFT JOIN xbrl_fact AS xf
              ON xf.fact_id = fmv.fact_id
            WHERE ri.company_code = ?
              AND ri.year = ?
              AND ri.quarter = ?
              AND fmv.concept_id = ?
              AND fmv.value IS NOT NULL
              AND (fd.statement_type = ? OR fd.statement_type IS NULL)
              AND (
                    (fd.statement_type = 'balance_sheet' AND xf.instant_date = ri.period_end)
                 OR (fd.statement_type IN ('comprehensive_income_statement', 'statement_of_cash_flows') AND xf.period_end = ri.period_end)
                 OR (fd.statement_type IS NULL AND (xf.instant_date = ri.period_end OR xf.period_end = ri.period_end))
              )
            ORDER BY
                CASE WHEN xf.segment_json IS NULL THEN 0 ELSE 1 END,
                CASE WHEN xf.unit_id = 'TWD' THEN 0 ELSE 1 END,
                ABS(fmv.value) DESC
            LIMIT 1
            """
        params = (company_code, year, f"Q{effective_quarter}", concept_id, statement_type)
        print(
            "[semantic_retrieval] SQL financial_metric_value lookup:\n"
            + dump_log_payload(
                {
                    "company_code": company_code,
                    "year": year,
                    "quarter": f"Q{effective_quarter}",
                    "requested_quarter": quarter,
                    "statement_type": statement_type,
                    "concept_id": concept_id,
                    "where_focus": {
                        "ri.company_code": company_code,
                        "ri.year": year,
                        "ri.quarter": f"Q{effective_quarter}",
                        "fmv.concept_id": concept_id,
                        "fd.statement_type": statement_type,
                    },
                    "params": params,
                    "sql": query,
                    "sql_preview": render_sql_debug_preview(query, params),
                }
            )
        )
        cursor = connection.execute(query, params)
        row = cursor.fetchone()
        result = dict(row) if row else None
        # print(
        #     "[semantic_retrieval] SQL financial_metric_value result:\n"
        #     + dump_log_payload(
        #         {
        #             "found": result is not None,
        #             "concept_id": concept_id,
        #             "value": result.get("value") if result else None,
        #             "value_numeric": result.get("value_numeric") if result else None,
        #             "unit_id": result.get("unit_id") if result else None,
        #             "report_id": result.get("report_id") if result else None,
        #         }
        #     )
        # )
        if result is not None:
            result["requested_year"] = year
            result["requested_quarter"] = quarter
            result["requested_period_type"] = "annual" if quarter is None else "quarterly"
        return result
    finally:
        connection.close()


def extract_semantic_plan(question: str) -> Dict:
    # 先請 LLM 將使用者問題拆成「分析目標 + 需要查的欄位 + 期間」的結構化計畫。
    parser = JsonOutputParser(pydantic_object=SemanticPlanDraft)
    sanitized_question = sanitize_llm_text(question)
    prompt = PromptTemplate(
        template="""你是財務資料需求規劃器。
            你的任務是先判斷：要回答使用者問題，至少需要哪些財務數據。

            規則：
            1. company_identifier 一定要填最適合代表公司的單一識別值，優先使用公司代碼，其次公司簡稱、公司全名或英文名。
            2. company_identifiers 必須填字串陣列，將問題中的公司資訊拆成可供本地公司清單比對的候選值。
               - 若問題包含「台灣水泥 (台泥, Taiwan Cement Corporation, 1101)」，請拆成 ["1101", "台泥", "台灣水泥", "Taiwan Cement Corporation"]。
               - 不要只輸出整段複合描述；必須把代碼、簡稱、全名、英文名分開放入陣列。
               - 若有公司代碼，company_identifier 優先填公司代碼。
            3. statement_type 只能填：
            - balance_sheet
            - comprehensive_income_statement
            - statement_of_cash_flows
            4. requirements 要列出回答此題真正需要查的欄位，最多10 個 requirement；不要為了增加命中率展開過多欄位。
            5. 每個 requirement 的 field_query 必須是字串陣列，最多 3 個查詢詞；只放最核心的中文欄位名稱與必要別名，不要列出大量同義詞。
            6. periods 只填問題中明確提到、或回答此題必要的期間。
            7. 如果問題需要比較多個期間，就列出多個 periods。
            8. 若沒有辦法判斷，requirements 仍只列出最可能需要的 1 到 3 個欄位。
            9. 只輸出 JSON，不要輸出 markdown、說明文字或程式碼區塊。
            10. 若問題只提到年份、年度、全年、整年、年增、年度比較，且沒有明確指定 Q1~Q4，periods 中的 quarter 必須填 null，表示要查該年度全年資料。
            11. 只有在問題明確指定季度時，quarter 才能填 1 到 4。
            12. purpose 要簡短描述此 requirement 的用途；全體 requirements 的 purpose 類型最多 5 個，不要拆出超過 5 種分析目的。
            13. 不需要每個 field_query 都提供英文；只有使用者問題本身使用英文，或該英文是必要的正式會計項目名稱時才加入。

            問題：{question}

            請輸出以下 JSON 格式：
            {{
              "company_identifier": "優先填公司代碼，否則填公司名稱、簡稱或英文名",
              "company_identifiers": ["公司代碼", "公司簡稱", "公司名稱", "公司英文名"],
              "analysis_goal": "這題要分析什麼",
              "requirements": [
                {{
                  "field_query": ["核心欄位名稱", "必要別名，最多 3 個"],
                  "statement_type": "balance_sheet 或 comprehensive_income_statement 或 statement_of_cash_flows",
                  "periods": [
                    {{"year": 2024, "quarter": null}},
                    {{"year": 2024, "quarter": 1}}
                  ],
                  "purpose": "查這些欄位的目的"
                }}
              ]
            }}""",
        input_variables=["question"],
    )
    formatted_prompt = sanitize_llm_text(prompt.format(question=sanitized_question))
    print(
        "[semantic_retrieval] extract_semantic_plan request prompt metadata:\n"
        + dump_log_payload(
            {
                "question": sanitized_question,
                "prompt_length": len(formatted_prompt),
                "prompt_preview": formatted_prompt[:2000],
            }
        )
    )
    print("[semantic_retrieval] extract_semantic_plan request prompt full:\n" + formatted_prompt)
    try:
        response = chat_model.invoke(formatted_prompt)
    except Exception as exc:
        print(
            "[semantic_retrieval] extract_semantic_plan request failed:\n"
            + dump_log_payload(
                {
                    "question": sanitized_question,
                    "prompt_length": len(formatted_prompt),
                    "prompt_preview": formatted_prompt[:2000],
                    "error": str(exc),
                }
            )
        )
        raise
    # print(
    #     "[semantic_retrieval] extract_semantic_plan raw llm response:\n"
    #     + dump_log_payload(
    #         {
    #             "question": sanitized_question,
    #             "response_content": get_message_text(response),
    #         }
    #     )
    # )
    semantic_plan = normalize_semantic_plan(parser.invoke(response))
    # print(
    #     "[semantic_retrieval] extract_semantic_plan parsed JSON:\n"
    #     + json.dumps(semantic_plan, ensure_ascii=False, indent=2, default=str)
    # )
    return semantic_plan


def choose_best_candidate(question: str, requirement: Dict, candidates: List[Dict]) -> Dict:
    if not candidates:
        return {}
    if len(candidates) == 1:
        return candidates[0]
    top_candidate = candidates[0]
    second_candidate = candidates[1] if len(candidates) > 1 else None
    top_score = float(top_candidate.get("score") or 0)
    second_score = float(second_candidate.get("score") or 0) if second_candidate else 0.0
    if top_score >= second_score + 12:
        return top_candidate

    compact_candidates = [
        {
            "concept_name": candidate.get("concept_name"),
            "zh_tw": candidate.get("zh_tw"),
            "en": candidate.get("en"),
            "code": candidate.get("code"),
            "statement_type": candidate.get("statement_type"),
            "matched_query": candidate.get("matched_query"),
            "score": candidate.get("score"),
        }
        for candidate in candidates[:3]
    ]
    compact_requirement = {
        "field_query": requirement.get("field_query"),
        "statement_type": requirement.get("statement_type"),
        "periods": requirement.get("periods"),
        "purpose": requirement.get("purpose"),
    }

    prompt = sanitize_llm_text(
        f"""
你是財務欄位選擇器。
請根據使用者問題與資料需求，從候選清單中選出最適合查資料的一個 concept_name。
只能回答 concept_name，不要解釋。

### 使用者問題
{question}

### 資料需求
{json.dumps(compact_requirement, ensure_ascii=False, indent=2)}

### 候選清單
{json.dumps(compact_candidates, ensure_ascii=False, indent=2)}
"""
    )
    try:
        print("[semantic_retrieval] choose_best_candidate prompt:\n" + prompt)
        response = chat_model.invoke(prompt)
        chosen = get_message_text(response).strip()
        for candidate in candidates:
            if candidate.get("concept_name") == chosen:
                return candidate
        print(
            "[semantic_retrieval] choose_best_candidate fallback due to unmatched llm output:\n"
            + dump_log_payload(
                {
                    "question": question,
                    "requirement": compact_requirement,
                    "candidates": compact_candidates,
                    "llm_output": chosen,
                }
            )
        )
    except Exception as exc:
        print(f"[semantic_retrieval] choose_best_candidate fallback due to error: {exc}")
    return candidates[0]


def choose_best_candidates_for_requirement(
    question: str,
    requirement: Dict,
    candidates_by_field_query: Dict[str, List[Dict]],
) -> Dict[str, Dict]:
    selected_candidates = {}
    llm_tasks = []

    for field_query, candidates in candidates_by_field_query.items():
        if not candidates:
            selected_candidates[field_query] = {}
            continue
        if len(candidates) == 1:
            selected_candidates[field_query] = candidates[0]
            continue
        top_candidate = candidates[0]
        second_candidate = candidates[1] if len(candidates) > 1 else None
        top_score = float(top_candidate.get("score") or 0)
        second_score = float(second_candidate.get("score") or 0) if second_candidate else 0.0
        if top_score >= second_score + 12:
            selected_candidates[field_query] = top_candidate
            continue
        llm_tasks.append(
            {
                "field_query": field_query,
                "candidates": [
                    {
                        "concept_name": candidate.get("concept_name"),
                        "zh_tw": candidate.get("zh_tw"),
                        "en": candidate.get("en"),
                        "code": candidate.get("code"),
                        "statement_type": candidate.get("statement_type"),
                        "matched_query": candidate.get("matched_query"),
                        "score": candidate.get("score"),
                    }
                    for candidate in candidates[:3]
                ],
            }
        )

    if not llm_tasks:
        return selected_candidates

    parser = JsonOutputParser(pydantic_object=CandidateChoiceBatch)
    compact_requirement = {
        "field_query": requirement.get("field_query"),
        "statement_type": requirement.get("statement_type"),
        "periods": requirement.get("periods"),
        "purpose": requirement.get("purpose"),
    }
    prompt = sanitize_llm_text(
        f"""
你是財務欄位選擇器。
請根據使用者問題與資料需求，為每個 field_query 從對應候選清單中選出最適合查資料的一個 concept_name。

規則：
1. 只能從該 field_query 自己的 candidates 中選。
2. 每個 field_query 最多選一個 concept_name。
3. 只輸出 JSON，不要輸出 markdown、說明文字或程式碼區塊。

### 使用者問題
{question}

### 資料需求
{json.dumps(compact_requirement, ensure_ascii=False, indent=2)}

### 待選欄位與候選清單
{json.dumps(llm_tasks, ensure_ascii=False, indent=2)}

### JSON 格式
{{
  "choices": [
    {{"field_query": "營業收入", "concept_name": "ifrs-full_Revenue"}}
  ]
}}
"""
    )
    try:
        print("[semantic_retrieval] choose_best_candidates_for_requirement prompt:\n" + prompt)
        response = chat_model.invoke(prompt)
        parsed = parser.parse(get_message_text(response))
        choice_map = {
            item.get("field_query"): item.get("concept_name")
            for item in parsed.get("choices", [])
            if isinstance(item, dict)
        }
        for task in llm_tasks:
            field_query = task["field_query"]
            chosen = choice_map.get(field_query)
            matched_candidate = next(
                (
                    candidate
                    for candidate in candidates_by_field_query.get(field_query, [])
                    if candidate.get("concept_name") == chosen
                ),
                None,
            )
            if matched_candidate:
                selected_candidates[field_query] = matched_candidate
            else:
                selected_candidates[field_query] = choose_best_candidate(
                    question,
                    {**requirement, "field_query": [field_query]},
                    candidates_by_field_query.get(field_query, []),
                )
        return selected_candidates
    except Exception as exc:
        print(f"[semantic_retrieval] choose_best_candidates_for_requirement fallback due to error: {exc}")
        for task in llm_tasks:
            field_query = task["field_query"]
            selected_candidates[field_query] = choose_best_candidate(
                question,
                {**requirement, "field_query": [field_query]},
                candidates_by_field_query.get(field_query, []),
            )
        return selected_candidates


def build_llm_evidence_candidate(candidate: Dict) -> Dict:
    # 將候選欄位縮成較精簡的證據格式，避免後續傳給 LLM 的 token 過大。
    if not candidate:
        return {}
    return {
        "concept_name": candidate.get("concept_name"),
        "zh_tw": candidate.get("zh_tw"),
        "en": candidate.get("en"),
        "code": candidate.get("code"),
        "statement_type": candidate.get("statement_type"),
        "matched_query": candidate.get("matched_query"),
        "score": candidate.get("score"),
        "mapped_from": candidate.get("mapped_from"),
        "mapping_queries": candidate.get("mapping_queries"),
    }


def build_candidate_score_log(candidate: Dict) -> Dict:
    if not candidate:
        return {}
    return {
        "concept_name": candidate.get("concept_name"),
        "zh_tw": candidate.get("zh_tw"),
        "en": candidate.get("en"),
        "code": candidate.get("code"),
        "statement_type": candidate.get("statement_type"),
        "matched_query": candidate.get("matched_query"),
        "score": candidate.get("score"),
        "mapped_from": candidate.get("mapped_from"),
        "mapping_queries": candidate.get("mapping_queries"),
        "score_breakdown": candidate.get("score_breakdown"),
    }


def print_requirement_candidate_score_log(
    requirement: Dict,
    candidates_by_field_query: Dict[str, List[Dict]],
    selected_candidates_by_field_query: Dict[str, Dict],
    limit: int = 5,
) -> None:
    payload = {
        "requirement": {
            "field_query": requirement.get("field_query"),
            "statement_type": requirement.get("statement_type"),
            "periods": requirement.get("periods"),
            "purpose": requirement.get("purpose"),
        },
        "field_query_matches": [],
    }
    for field_query, candidates in candidates_by_field_query.items():
        selected_candidate = selected_candidates_by_field_query.get(field_query, {})
        payload["field_query_matches"].append(
            {
                "field_query": field_query,
                "selected_candidate": build_candidate_score_log(selected_candidate),
                "top_candidates": [
                    build_candidate_score_log(candidate)
                    for candidate in candidates[:limit]
                ],
            }
        )
    # print(
    #     "[semantic_retrieval] requirement_candidate_score_log:\n"
    #     + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    # )


def get_fact_label(field_query: str, candidate: Dict) -> str:
    return (
        candidate.get("zh_tw")
        or candidate.get("en")
        or field_query
        or candidate.get("concept_name")
        or "未命名項目"
    )


def normalize_match_text(value: object) -> str:
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def is_candidate_low_confidence(field_query: str, candidate: Dict) -> bool:
    if not candidate:
        return True

    concept_name = normalize_match_text(candidate.get("concept_name"))
    label_text = normalize_match_text(
        " ".join(
            [
                str(candidate.get("zh_tw") or ""),
                str(candidate.get("en") or ""),
                str(candidate.get("matched_query") or ""),
            ]
        )
    )
    field_text = normalize_match_text(field_query)
    combined_candidate_text = f"{concept_name} {label_text}"

    # 常見錯配：使用者要流動/短期資產，卻選到資產總計、短期借款或單一金融資產。
    if any(term in field_text for term in ("liquid assets", "short term assets", "short-term assets")):
        if "assets" == concept_name.split()[-1] or "shorttermborrowings" in concept_name.replace(" ", ""):
            return True
        if "borrowings" in combined_candidate_text:
            return True

    if "current assets total" in field_text:
        if "currentassets" not in concept_name.replace(" ", ""):
            return True

    if "current liabilities" in field_text:
        if "currentliabilities" not in concept_name.replace(" ", ""):
            return True

    if "cash and cash equivalents" in field_text or "現金及約當現金" in field_text:
        if "cashandcashequivalents" not in concept_name.replace(" ", ""):
            return True

    if "short term debt" in field_text or "short-term debt" in field_text:
        debt_terms = ("borrowings", "commercialpapers", "notesbillspayable", "shortterm")
        if not any(term in combined_candidate_text.replace(" ", "") for term in debt_terms):
            return True

    return False


def build_compact_fact(
    field_query: str,
    requirement: Dict,
    selected_candidate: Dict,
    value_item: Dict,
) -> Dict:
    result = value_item.get("result") or {}
    period = value_item.get("period") or {}
    return {
        "label": get_fact_label(field_query, selected_candidate),
        "field_query": field_query,
        "concept_name": selected_candidate.get("concept_name"),
        "statement_type": selected_candidate.get("statement_type") or requirement.get("statement_type"),
        "period": {
            "year": result.get("year") or period.get("year"),
            "quarter": result.get("quarter"),
            "report_period_end": result.get("report_period_end"),
        },
        "value": result.get("value_numeric")
        if result.get("value_numeric") is not None
        else result.get("value"),
        "value_text": result.get("value_text"),
        "unit": result.get("unit_id"),
        "purpose": requirement.get("purpose"),
    }


def compact_metric_value(value: float) -> float:
    return round(value, 4)


def find_numeric_fact(facts: List[Dict], concept_names: List[str]) -> Optional[Dict]:
    concept_name_set = set(concept_names)
    for fact in facts:
        if fact.get("concept_name") in concept_name_set and isinstance(fact.get("value"), (int, float)):
            return fact
    return None


def build_computed_metrics(facts: List[Dict]) -> List[Dict]:
    metrics = []
    current_assets = find_numeric_fact(facts, ["ifrs-full_CurrentAssets"])
    current_liabilities = find_numeric_fact(facts, ["ifrs-full_CurrentLiabilities"])
    cash = find_numeric_fact(facts, ["ifrs-full_CashAndCashEquivalents"])
    operating_cash_flow = find_numeric_fact(
        facts,
        [
            "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "ifrs-full_CashFlowsFromUsedInOperations",
            "tifrs-SCF_CashFlowsFromUsedInOperatingActivities",
        ],
    )

    if current_assets and current_liabilities and current_liabilities["value"]:
        metrics.append(
            {
                "label": "流動比率",
                "formula": "流動資產 / 流動負債",
                "value": compact_metric_value(current_assets["value"] / current_liabilities["value"]),
            }
        )

    if cash and current_liabilities and current_liabilities["value"]:
        metrics.append(
            {
                "label": "現金對流動負債比",
                "formula": "現金及約當現金 / 流動負債",
                "value": compact_metric_value(cash["value"] / current_liabilities["value"]),
            }
        )

    if operating_cash_flow and current_liabilities and current_liabilities["value"]:
        metrics.append(
            {
                "label": "營業現金流對流動負債比",
                "formula": "營業活動淨現金流 / 流動負債",
                "value": compact_metric_value(operating_cash_flow["value"] / current_liabilities["value"]),
            }
        )

    return metrics


def build_final_answer_evidence(
    question: str,
    plan: Dict,
    company: Dict,
    retrieval_results: List[Dict],
) -> Dict:
    facts = []
    excluded_or_low_confidence_facts = []
    fact_keys = set()

    for item in retrieval_results:
        requirement = item.get("requirement", {})
        for query_result in item.get("query_results", []):
            field_query = query_result.get("field_query")
            selected_candidate = query_result.get("selected_candidate", {})
            for value_item in query_result.get("values", []):
                result = value_item.get("result")
                if result is None:
                    excluded_or_low_confidence_facts.append(
                        {
                            "field_query": field_query,
                            "reason": "查無資料庫數值",
                            "selected_candidate": {
                                "concept_name": selected_candidate.get("concept_name"),
                                "zh_tw": selected_candidate.get("zh_tw"),
                                "en": selected_candidate.get("en"),
                            },
                            "period": value_item.get("period"),
                        }
                    )
                    continue

                if is_candidate_low_confidence(field_query, selected_candidate):
                    excluded_or_low_confidence_facts.append(
                        {
                            "field_query": field_query,
                            "reason": "候選欄位與查詢語意可能不一致，未提供給最終回答引用",
                            "selected_candidate": {
                                "concept_name": selected_candidate.get("concept_name"),
                                "zh_tw": selected_candidate.get("zh_tw"),
                                "en": selected_candidate.get("en"),
                            },
                            "value": result.get("value_numeric")
                            if result.get("value_numeric") is not None
                            else result.get("value"),
                            "unit": result.get("unit_id"),
                            "period": {
                                "year": result.get("year"),
                                "quarter": result.get("quarter"),
                                "report_period_end": result.get("report_period_end"),
                            },
                        }
                    )
                    continue

                fact = build_compact_fact(
                    field_query=field_query,
                    requirement=requirement,
                    selected_candidate=selected_candidate,
                    value_item=value_item,
                )
                fact_key = (
                    fact.get("concept_name"),
                    fact.get("statement_type"),
                    fact.get("period", {}).get("year"),
                    fact.get("period", {}).get("quarter"),
                    fact.get("period", {}).get("report_period_end"),
                )
                if fact_key in fact_keys:
                    continue
                fact_keys.add(fact_key)
                facts.append(fact)

    periods = []
    period_keys = set()
    for fact in facts:
        period = fact.get("period") or {}
        period_key = (period.get("year"), period.get("quarter"), period.get("report_period_end"))
        if period_key in period_keys:
            continue
        period_keys.add(period_key)
        periods.append(period)

    return {
        "question": question,
        "analysis_goal": plan.get("analysis_goal"),
        "company": {
            "code": company.get("companyCode"),
            "name": company.get("companyName"),
            "short_name": company.get("shortName"),
            "english_name": company.get("englishName"),
        },
        "periods": periods,
        "facts": facts,
        "computed_metrics": build_computed_metrics(facts),
        "excluded_or_low_confidence_facts": excluded_or_low_confidence_facts[:20],
    }


def get_log_item_zh_name(detail: Dict) -> str:
    selected_candidate = detail.get("selected_candidate") or {}
    return (
        selected_candidate.get("zh_tw")
        or detail.get("field_query")
        or "未命名項目"
    )


def print_unique_log_item_names(label: str, details: List[Dict]) -> None:
    print(label)
    seen_items = set()
    for detail in details:
        name = get_log_item_zh_name(detail)
        selected_candidate = detail.get("selected_candidate") or {}
        concept_name = selected_candidate.get("concept_name")
        item_key = (name, concept_name)
        if item_key in seen_items:
            continue
        seen_items.add(item_key)
        if concept_name:
            print(f"- {name} ({concept_name})")
        else:
            print(f"- {name}")
    if not seen_items:
        print("- 無")


def retrieve_requirement_data(question: str, company: Dict, requirement: Dict) -> Dict:
    # 針對單一 requirement 中的每個 field_query 逐一找候選欄位，並以 requirement 為單位批次挑選最佳 concept，再查各期間數值。
    field_queries = requirement.get("field_query", [])
    query_results = []
    values = []
    candidates_by_field_query = {}
    value_result_cache = {}
    emitted_value_keys = set()

    candidate_search_started_at = perf_counter()
    for field_query in field_queries:
        # 先根據 field_query、報表類型與公司常用 family 範圍，找出可比對的候選 XBRL concept。
        candidates = search_candidates_across_statements(
            field_queries=[field_query],
            statement_type=requirement["statement_type"],
            limit=8,
            company_code=company["companyCode"],
        )
        candidates_by_field_query[field_query] = candidates
    print(
        f"[timing] semantic_retrieval.match_requirement_field_queries took {perf_counter() - candidate_search_started_at:.3f}s "
        f"(statement_type={requirement.get('statement_type')}, field_queries={len(field_queries)}, "
        f"candidate_count={sum(len(candidates) for candidates in candidates_by_field_query.values())})"
    )

    selected_candidates_by_field_query = choose_best_candidates_for_requirement(
        question=question,
        requirement=requirement,
        candidates_by_field_query=candidates_by_field_query,
    )
    print_requirement_candidate_score_log(
        requirement=requirement,
        candidates_by_field_query=candidates_by_field_query,
        selected_candidates_by_field_query=selected_candidates_by_field_query,
    )

    for field_query in field_queries:
        candidates = candidates_by_field_query.get(field_query, [])
        selected_candidate = selected_candidates_by_field_query.get(field_query, {})

        query_values = []
        for period in requirement.get("periods", []):
            result = None
            quarter = period.get("quarter")
            value_key = None
            if selected_candidate:
                statement_type = selected_candidate.get("statement_type") or requirement["statement_type"]
                concept_name = selected_candidate.get("concept_name")
                value_key = (
                    statement_type,
                    concept_name,
                    period.get("year"),
                    quarter,
                )
                if value_key in value_result_cache:
                    result = value_result_cache[value_key]
                else:
                    # if quarter is None:
                    #     print(
                    #         "[semantic_retrieval] fetch_financial_value in annual mode (quarter missing, fallback to Q4 cumulative/year-end):\n"
                    #         + json.dumps(
                    #             {
                    #                 "field_query": field_query,
                    #                 "period": period,
                    #                 "selected_candidate": build_llm_evidence_candidate(selected_candidate),
                    #             },
                    #             ensure_ascii=False,
                    #             indent=2,
                    #         )
                    #     )
                    # 針對選中的 concept，在指定公司與期間上查詢實際財務數值。
                    result = fetch_financial_value(
                        company_code=company["companyCode"],
                        year=period["year"],
                        quarter=quarter,
                        statement_type=statement_type,
                        concept_id=concept_name,
                    )
                    value_result_cache[value_key] = result
            value_item = {
                "field_query": field_query,
                "period": period,
                "result": result,
            }
            if value_key is None or value_key not in emitted_value_keys:
                query_values.append(value_item)
                values.append(value_item)
                if value_key is not None:
                    emitted_value_keys.add(value_key)

        # 保留每個 field_query 的完整查詢結果，供後續 fulfilled/planned 統計與最終證據組裝使用。
        query_results.append(
            {
                "field_query": field_query,
                "selected_candidate": build_llm_evidence_candidate(selected_candidate),
                "candidates": [build_llm_evidence_candidate(candidate) for candidate in candidates],
                "values": query_values,
            }
        )

    # 回傳這個 requirement 底下所有 field_query 的結果彙總，以及展平後的 values 清單。
    return {
        "requirement": requirement,
        "query_results": query_results,
        "values": values,
    }


def semantic_retrieval(state: OverallState) -> OverallState:
    # 語意檢索主流程：
    # 1. 讓 LLM 規劃回答問題需要哪些財務資料
    # 2. 解析公司並查詢實際可用報表
    # 3. 逐個 requirement 取回資料庫證據
    # 4. 若證據足夠，再交給 LLM 產生最終分析回答
    print("semantic_retrieval in =======")
    started_at = perf_counter()

    question = state["rephrased_question"] or state["user_input"]
    plan = state.get("semantic_plan")
    if not isinstance(plan, dict) or not plan:
        semantic_plan_error = state.get("semantic_plan_error")
        return {
            **state,
            "answer": (
                "語意檢索規劃階段失敗，暫時無法分析所需財務資料。"
                + (f"錯誤：{semantic_plan_error}" if semantic_plan_error else "")
            ),
            "reference_data": {"question": question},
        }

    step_started_at = perf_counter()
    company = resolve_company(plan.get("company_identifiers") or plan.get("company_identifier", ""))
    print(f"company: {json.dumps(company, ensure_ascii=False, indent=2)}")

    print(f"[timing] semantic_retrieval.resolve_company took {perf_counter() - step_started_at:.3f}s")
    if not company:
        return {
            **state,
            "answer": "當前提供的公司名稱資訊不足，無法匹配到現有台灣公司，請補充該公司完整名稱",
            "reference_data": {"plan": plan},
        }

    step_started_at = perf_counter()
    available_reports = list_company_reports(company["companyCode"])
    print(f"[timing] semantic_retrieval.list_company_reports took {perf_counter() - step_started_at:.3f}s")
    # print("\n[semantic_retrieval] company:")
    # print(json.dumps(company, ensure_ascii=False, indent=2))
    # print("\n[semantic_retrieval] available_reports:")
    # print(json.dumps(available_reports[:20], ensure_ascii=False, indent=2))

    retrieval_results = []
    step_started_at = perf_counter()
    for requirement in plan.get("requirements", []):
        result = retrieve_requirement_data(question, company, requirement)
        retrieval_results.append(result)
    print(f"[timing] semantic_retrieval.retrieve_requirement_data_total took {perf_counter() - step_started_at:.3f}s")

    llm_evidence_json = build_final_answer_evidence(
        question=question,
        plan=plan,
        company=company,
        retrieval_results=retrieval_results,
    )
    evidence_json = {
        "question": question,
        "analysis_goal": plan.get("analysis_goal"),
        "company": company,
        "available_reports": available_reports,
        "retrieval_results": retrieval_results,
        "llm_evidence": llm_evidence_json,
        "selected_warehouse_data": state.get("selected_applied_warehouse_data") or [],
        "selected_expert_knowledge": state.get("selected_applied_expert_knowledge") or [],
        "external_data_query_text": state.get("external_data_query_text") or "",
        "external_data_response": state.get("external_data_response") or "",
        "external_data_response_prompt": state.get("external_data_response_prompt") or "",
    }
    # print("\n[semantic_retrieval] evidence_json:")
    # print(json.dumps(evidence_json, ensure_ascii=False, indent=2))
    # print("\n[semantic_retrieval] llm_evidence_json:")
    # print(json.dumps(llm_evidence_json, ensure_ascii=False, indent=2))

    fulfilled_items = 0
    planned_items = 0
    fulfilled_details = []
    planned_details = []
    planned_detail_keys = set()
    for item in retrieval_results:
        requirement = item.get("requirement", {})
        query_result_map = {
            query_result.get("field_query"): query_result
            for query_result in item.get("query_results", [])
        }
        for value_item in item["values"]:
            field_query = value_item.get("field_query")
            query_result = query_result_map.get(field_query, {})
            selected_candidate = query_result.get("selected_candidate", {})
            period = value_item.get("period") or {}
            planned_detail_key = (
                selected_candidate.get("statement_type"),
                selected_candidate.get("concept_name"),
                period.get("year"),
                period.get("quarter"),
            )
            if selected_candidate and planned_detail_key in planned_detail_keys:
                continue
            if selected_candidate:
                planned_detail_keys.add(planned_detail_key)
            detail = {
                "requirement": requirement,
                "field_query": field_query,
                "selected_candidate": selected_candidate,
                "period": period,
                "result": value_item.get("result"),
                "is_fulfilled": value_item.get("result") is not None,
            }
            planned_details.append(detail)
            planned_items += 1
            if value_item.get("result") is not None:
                fulfilled_items += 1
                fulfilled_details.append(detail)

    # print(
    #     "[semantic_retrieval] planned_details:\n"
    #     + json.dumps(planned_details, ensure_ascii=False, indent=2, default=str)
    # )
    # print(
    #     "[semantic_retrieval] fulfilled_details:\n"
    #     + json.dumps(fulfilled_details, ensure_ascii=False, indent=2, default=str)
    # )

    print_unique_log_item_names("[semantic_retrieval] fulfilled_items_list:", fulfilled_details)
    print_unique_log_item_names("[semantic_retrieval] planned_items_list:", planned_details)

    print("[semantic_retrieval] all_requirement_field_queries:")
    requirements = plan.get("requirements", [])
    if requirements:
        for index, requirement in enumerate(requirements, start=1):
            field_queries = requirement.get("field_query") or []
            if field_queries:
                for field_query in field_queries:
                    print(f"- requirement_{index}: {field_query}")
            else:
                print(f"- requirement_{index}: 無")
    else:
        print("- 無")

    print("fulfilled_items =", fulfilled_items)
    print("planned_items =", planned_items)
    has_external_data_response = bool(str(state.get("external_data_response") or "").strip())
    enough_information = bool(llm_evidence_json.get("facts")) or has_external_data_response
    # enough_information = fulfilled_items > 0 and fulfilled_items == planned_items

    # print(
    #     json.dumps(
    #         {
    #             "planned_items": planned_items,
    #             "fulfilled_items": fulfilled_items,
    #             "enough_information": enough_information,
    #         },
    #         ensure_ascii=False,
    #         indent=2,
    #     )
    # )

    if not enough_information:
        print(f"[timing] semantic_retrieval.total took {perf_counter() - started_at:.3f}s")
        return {
            **state,
            "answer": "我已分析需要的財務資料並查詢資料庫，但目前資料不足以完整回答這個問題。",
            "reference_data": evidence_json,
        }

    use_expert_knowledge = bool(state.get("use_expert_knowledge", True))
    use_warehouse_data = bool(state.get("use_warehouse_data", True))
    optional_rule_lines = []
    if use_expert_knowledge:
        optional_rule_lines.append(
            "若有提供專家分析參考，請逐一吸收所有條目的觀點，並在分析結論中反映其對財務資料解讀的影響，不可忽略。"
        )

    if use_warehouse_data:
        optional_rule_lines.extend(
            [
                "若有提供資料倉儲參考資料，請優先使用其中與題目最相關的內容，摘要其與公司、產業、風險事件或判決爭議的關聯。",
                "如果資料倉儲資料存在原文連結或來源，回答中可簡短標示資料類型與來源，但不要大段轉貼原文。",
            ]
        )

    if has_external_data_response:
        optional_rule_lines.extend(
            [
                "若有提供外部資料查詢結果，請在回答中新增獨立章節列出其摘要，並用於補充事件背景、負面消息、產業脈絡或信用風險判斷。",
                "外部資料查詢結果不可作為財務報表數字來源；若內容存在不確定性或無法確認，必須在補充說明揭露限制。",
            ]
        )

    numbered_optional_rule_lines = [
        f"{index}. {rule}"
        for index, rule in enumerate(optional_rule_lines, start=7)
    ]
    final_rule_index = 7 + len(numbered_optional_rule_lines)

    expert_section = ""
    if use_expert_knowledge:
        expert_section = """
        ***專業分析***
        - 根據專家分析參考，把內容列出來，這段不用作為分析結論的依據，只要把專家說了什麼列出來即可，並標示為「專家分析參考」。
        - 如果專家分析參考是空的，則這一段可以省略不寫。
        """.strip()

    warehouse_data = ""
    if use_warehouse_data:
        warehouse_data = """
        ***資料倉儲***
        - 資料倉儲參考資料，把內容列出來，這段不用作為分析結論的依據，只要把資料倉儲說了什麼列出來即可，並標示為「資料倉儲參考」。
        """.strip()

    external_data_section = ""
    if has_external_data_response:
        external_data_section = """
        ***外部資料查詢結果***
        - 將 AI Agent 外部資料查詢結果整理成可讀摘要，明確列出查詢主題、摘要重點、可能影響與資料限制。
        - 這一段可作為分析結論的背景依據，但不可取代財務報表數字。
        """.strip()

    prompt_reference_sections = []
    if use_expert_knowledge:
        prompt_reference_sections.extend(
            ["### 專家分析參考", build_expert_knowledge_prompt_section(state), ""]
        )
    if use_warehouse_data:
        prompt_reference_sections.extend(
            ["### 資料倉儲參考資料", build_warehouse_data_prompt_section(state), ""]
        )
    if has_external_data_response:
        prompt_reference_sections.extend(
            ["### 外部資料查詢結果", build_external_data_prompt_section(state), ""]
        )

    final_prompt = f"""
        你是信用徵審財報分析助手。
        請根據財務報表資料來源、資料倉儲參考資料、外部資料查詢結果與專家分析參考進行綜合判斷，不要臆測。
        財務報表資料來源是財務數字與關鍵證據的唯一來源；資料倉儲、外部資料查詢結果與專家分析參考是信用徵審風險、事件背景、營運策略與決策判斷的輔助來源。

        規則：
        1. 只能引用 facts 與 computed_metrics，不要引用 excluded_or_low_confidence_facts 作為判斷依據。
        2. 若需要比較、趨勢、增減或比率，優先使用 computed_metrics；不足時才用 facts 中的數值計算。
        3. 回答使用繁體中文，數值標注以***仟元***為單位。
        4. 若有被排除或低可信資料，只能在補充說明簡短提醒，不要拿來下結論。
        5. 若有提供資料倉儲、外部資料查詢結果或專家分析參考資料，「一、參考數據」「二、專業分析」「三、分析結論」「四、補充說明」都必須納入這些背景後再回答。
        6. 資料倉儲、外部資料查詢結果與專家分析不可作為財務數字來源；若引用這些資料，只能用於說明事件背景、產業脈絡、經營策略、風險重點、審查方向、訴訟或負面消息背景、信用徵審判斷。
        {chr(10).join(numbered_optional_rule_lines)}
        {final_rule_index}. 最後的分析決策結果必須同時交代：財務報表證據支持什麼、資料倉儲或外部資料背景補充什麼、專家分析參考提醒什麼、綜合後如何影響判斷。
        {final_rule_index + 1}. 回答的內容不用在括弧中作太多的說明跟解釋。

        請依照以下格式回答，並自動將標題補上中文數字一二三，依序下去：
        ***參考數據***
        - 主要參考財務報表資料來源，來列出本次回答實際引用的關鍵數據、比率或事實。
        - 每一點盡量包含欄位名稱、期間、數值，但不要把conecpt_name秀出來。
        - 如果有標注數據時間範圍，用「截至」作為期間結尾的詞彙；如果是單一期間的數據，則標注該期間即可。例如：「截至2025 年度期末」

        {expert_section}

        {warehouse_data}

        {external_data_section}

        ***分析結論***
        - 根據財務報表、資料倉儲參考、外部資料查詢結果與專家分析參考，直接回答使用者問題，並說明判斷依據。
        - 明確說明資料倉儲、外部資料查詢結果或專家分析如何改變、強化或限制財務資料本身的解讀。

        ***補充說明***
        - 若有重要但未查到、被排除或低可信的欄位，簡短補充即可。
        - 若有資料倉儲、外部資料查詢結果或專家分析參考資料，必須補充其限制：這些資料是背景與判讀輔助，不等同於本次查詢出的財務報表財務數字來源。

        ### 使用者問題
        {question}

        {chr(10).join(prompt_reference_sections)}

        ### 財務報表資料來源
        {json.dumps(llm_evidence_json, ensure_ascii=False, indent=2)}

        """
    try:
        print("[semantic_retrieval] final_answer prompt:\n" + final_prompt)
        step_started_at = perf_counter()
        final_answer = get_message_text(chat_model.invoke(final_prompt))
        print(f"[timing] semantic_retrieval.final_answer_generation took {perf_counter() - step_started_at:.3f}s")
    except Exception as exc:
        final_answer = (
            "已查到足夠的財務資料，但最終分析回答階段失敗。"
            f"你可以先參考 reference_data 中的 JSON 證據。錯誤：{exc}"
        )
    print("[semantic_retrieval] final_answer:\n" + str(final_answer))

    print(f"[timing] semantic_retrieval.total took {perf_counter() - started_at:.3f}s")
    return {
        **state,
        "answer": final_answer,
        "final_answer": final_answer,
        "post_analysis_answer": final_answer,
        "reference_data": evidence_json,
    }
