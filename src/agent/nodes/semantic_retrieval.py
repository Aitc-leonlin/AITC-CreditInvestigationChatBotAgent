import json
import logging
import sqlite3
from time import perf_counter
from typing import Dict, List, Literal, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field, field_validator

from src.mappings.company_stock_code_array import CompanyStockCodeArray
from src.providers.chat_openAI_provider import chat_model, get_message_text
from src.services.account_title_matcher import find_candidates
from src.types.langgraph_state_types import OverallState


logger = logging.getLogger(__name__)
DB_PATH = "FinancialStatementXBRL.db"
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
    analysis_goal: str = Field(..., description="對問題的高層理解，例如比較營收趨勢、分析獲利變化")
    requirements: List[RequirementDraft] = Field(default_factory=list, description="回答所需的資料清單")


class CandidateChoiceItem(BaseModel):
    field_query: str = Field(..., description="對應的查詢欄位")
    concept_name: str = Field(..., description="選中的 concept_name")


class CandidateChoiceBatch(BaseModel):
    choices: List[CandidateChoiceItem] = Field(default_factory=list, description="每個 field_query 對應的最佳候選")


# 將 log payload 轉成可讀 JSON 字串，避免直接印 dict 時不易閱讀。
def dump_log_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


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


def resolve_company(identifier: str) -> Optional[Dict]:
    if not identifier:
        return None

    code_to_company_map, name_to_company_map = build_company_maps()
    direct = code_to_company_map.get(identifier) or name_to_company_map.get(identifier)
    if direct:
        return direct

    for item in CompanyStockCodeArray:
        if any(
            isinstance(value, str) and identifier in value
            for value in item.values()
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
        cursor = connection.execute(
            """
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
            """,
            (company_code, year, f"Q{effective_quarter}", concept_id, statement_type),
        )
        row = cursor.fetchone()
        result = dict(row) if row else None
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
            1. company_identifier 一定要填公司代碼、公司名、簡稱或英文名，從問題中擷取。
            2. statement_type 只能填：
            - balance_sheet
            - comprehensive_income_statement
            - statement_of_cash_flows
            3. requirements 要列出回答此題真正需要查的欄位。
            4. 每個 requirement 的 field_query 必須是字串陣列；若有同義詞、近義欄位或複數表達，請全部放進陣列。
            5. periods 只填問題中明確提到、或回答此題必要的期間。
            6. 如果問題需要比較多個期間，就列出多個 periods。
            7. 若沒有辦法判斷，requirements 仍盡量列出最可能需要的欄位。
            8. 只輸出 JSON，不要輸出 markdown、說明文字或程式碼區塊。
            9. 若問題只提到年份、年度、全年、整年、年增、年度比較，且沒有明確指定 Q1~Q4，periods 中的 quarter 必須填 null，表示要查該年度全年資料。
            10. 只有在問題明確指定季度時，quarter 才能填 1 到 4。
            11.每個requirements的field_query至少要提供5種，並且都提供英文，增加找到參考資料可以被比對到的機會。

            問題：{question}

            請輸出以下 JSON 格式：
            {{
              "company_identifier": "公司代碼、公司名稱、簡稱或英文名",
              "analysis_goal": "這題要分析什麼",
              "requirements": [
                {{
                  "field_query": ["欄位名稱1", "欄位名稱2"],
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
    return normalize_semantic_plan(parser.invoke(response))


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


def build_final_answer_result(result: Dict) -> Dict:
    if not result:
        return {}
    return {
        "company_code": result.get("company_code"),
        "year": result.get("year"),
        "quarter": result.get("quarter"),
        "report_period_end": result.get("report_period_end"),
        "concept_id": result.get("concept_id"),
        "value": result.get("value"),
        "value_numeric": result.get("value_numeric"),
        "value_text": result.get("value_text"),
        "unit_id": result.get("unit_id"),
        "requested_year": result.get("requested_year"),
        "requested_quarter": result.get("requested_quarter"),
        "requested_period_type": result.get("requested_period_type"),
    }


def build_final_answer_evidence(
    question: str,
    plan: Dict,
    company: Dict,
    retrieval_results: List[Dict],
) -> Dict:
    compact_retrieval_results = []
    for item in retrieval_results:
        requirement = item.get("requirement", {})
        compact_query_results = []
        for query_result in item.get("query_results", []):
            compact_values = []
            for value_item in query_result.get("values", []):
                result = value_item.get("result")
                if result is None:
                    continue
                compact_values.append(
                    {
                        "period": value_item.get("period"),
                        "result": build_final_answer_result(result),
                    }
                )
            if not compact_values:
                continue
            selected_candidate = query_result.get("selected_candidate", {})
            compact_query_results.append(
                {
                    "field_query": query_result.get("field_query"),
                    "selected_candidate": {
                        "concept_name": selected_candidate.get("concept_name"),
                        "zh_tw": selected_candidate.get("zh_tw"),
                        "en": selected_candidate.get("en"),
                        "statement_type": selected_candidate.get("statement_type"),
                    },
                    "values": compact_values,
                }
            )
        if not compact_query_results:
            continue
        compact_retrieval_results.append(
            {
                "requirement": {
                    "field_query": requirement.get("field_query"),
                    "statement_type": requirement.get("statement_type"),
                    "periods": requirement.get("periods"),
                    "purpose": requirement.get("purpose"),
                },
                "query_results": compact_query_results,
            }
        )

    return {
        "question": question,
        "analysis_goal": plan.get("analysis_goal"),
        "company": {
            "companyCode": company.get("companyCode"),
            "companyName": company.get("companyName"),
            "shortName": company.get("shortName"),
            "englishName": company.get("englishName"),
        },
        "retrieval_results": compact_retrieval_results,
    }


def get_log_item_zh_name(detail: Dict) -> str:
    selected_candidate = detail.get("selected_candidate") or {}
    return (
        selected_candidate.get("zh_tw")
        or detail.get("field_query")
        or "未命名項目"
    )


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
    try:
        step_started_at = perf_counter()
        plan = extract_semantic_plan(question)
        # print(f"[semantic_retrieval] extract_semantic_plan plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}")
        print(f"[timing] semantic_retrieval.extract_semantic_plan took {perf_counter() - step_started_at:.3f}s")
    except Exception as exc:
        return {
            **state,
            "answer": f"語意檢索規劃階段失敗，暫時無法分析所需財務資料。錯誤：{exc}",
            "reference_data": {"question": question},
        }
    # print("\n********** [semantic_retrieval] AI AGENT data-requirement plan start **********")
    # print(json.dumps(plan, ensure_ascii=False, indent=2))
    # print("********** [semantic_retrieval] AI AGENT data-requirement plan end **********\n")

    step_started_at = perf_counter()
    company = resolve_company(plan.get("company_identifier", ""))
    print(f"[timing] semantic_retrieval.resolve_company took {perf_counter() - step_started_at:.3f}s")
    if not company:
        return {
            **state,
            "answer": "無法辨識問題中的公司，因此無法進一步查詢資料庫。",
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

    evidence_json = {
        "question": question,
        "analysis_goal": plan.get("analysis_goal"),
        "company": company,
        "available_reports": available_reports,
        "retrieval_results": retrieval_results,
    }
    llm_evidence_json = build_final_answer_evidence(
        question=question,
        plan=plan,
        company=company,
        retrieval_results=retrieval_results,
    )
    # print("\n[semantic_retrieval] evidence_json:")
    # print(json.dumps(evidence_json, ensure_ascii=False, indent=2))
    # print("\n[semantic_retrieval] llm_evidence_json:")
    # print(json.dumps(llm_evidence_json, ensure_ascii=False, indent=2))

    fulfilled_items = 0
    planned_items = 0
    fulfilled_details = []
    planned_details = []
    for item in retrieval_results:
        requirement = item.get("requirement", {})
        query_result_map = {
            query_result.get("field_query"): query_result
            for query_result in item.get("query_results", [])
        }
        for value_item in item["values"]:
            field_query = value_item.get("field_query")
            query_result = query_result_map.get(field_query, {})
            detail = {
                "requirement": requirement,
                "field_query": field_query,
                "selected_candidate": query_result.get("selected_candidate", {}),
                "period": value_item.get("period"),
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

    print("[semantic_retrieval] fulfilled_items_list:")
    if fulfilled_details:
        for detail in fulfilled_details:
            print(f"- {get_log_item_zh_name(detail)}")
    else:
        print("- 無")

    print("[semantic_retrieval] planned_items_list:")
    if planned_details:
        for detail in planned_details:
            print(f"- {get_log_item_zh_name(detail)}")
    else:
        print("- 無")

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
    enough_information = fulfilled_items > 0 
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

    final_prompt = f"""
        你是信用徵審財報分析助手。
        請根據下列 JSON 證據資料回答問題。

        規則：
        1. 只能根據 JSON 中已查到的資料回答，不要自行臆測。
        2. 若有多個已查到值的 requirement / field_query，回答時要盡量涵蓋主要已命中的重點，不要只挑其中一筆就草率下結論。
        3. 若答案需要比較、趨勢、增減、成長率，請直接用 JSON 中的數值計算或描述。
        4. 最終回答請用繁體中文。
        5. 數值請加上千分位，並盡量帶單位。
        6. 先整理你實際引用的關鍵證據，再給分析結論；不要只輸出一句很短的總結。
        7. 若部分 requirement 有資料、部分沒有，不要假裝全部都有；只引用查到的資料，並在必要時簡短說明資料不足之處。

        請依照以下格式回答：
        一、關鍵證據
        - 列出本次回答實際引用的 3 到 8 筆關鍵數據或事實。
        - 每一點盡量包含欄位名稱、期間、數值。

        二、分析結論
        - 根據上面的證據，直接回答使用者問題。
        - 若問題涉及比較、趨勢、變化、成長率，請明確寫出比較結果與判斷依據。

        三、補充說明
        - 若有重要但未查到的欄位或期間，再簡短補充一次即可。

        ### 使用者問題
        {question}

        ### JSON 證據資料
        {json.dumps(llm_evidence_json, ensure_ascii=False, indent=2)}
        """
    try:
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
        "reference_data": evidence_json,
    }
