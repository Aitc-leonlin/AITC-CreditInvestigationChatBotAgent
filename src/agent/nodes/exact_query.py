import json
import logging
import re
import sqlite3
from difflib import SequenceMatcher
from time import perf_counter
from typing import Dict, List, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from src.mappings.company_stock_code_array import CompanyStockCodeArray
from src.providers.chat_openAI_provider import chat_model, get_message_text
from src.services.account_title_matcher import find_candidates, search_item_source_paths
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


class Period(BaseModel):
    year: int = Field(..., description="使用者提問中提到的年度")
    quarter: int = Field(..., description="使用者提問中提到的季度，Q1 只回傳 1")
    range: Optional[str] = Field(None, description="季度期間文字，例如 2024年Q1到Q3")


class RequestedField(BaseModel):
    field: str = Field(..., description="使用者請求的會計項目名稱，例如 現金及約當現金")
    category: Optional[str] = Field(
        None,
        description="項目所屬的報表類別，例如 資產負債表、綜合損益表、現金流量表",
    )


class QuestionSchema(BaseModel):
    companyName: str = Field(description="使用者提問中提到的公司全名")
    companyCode: str = Field(description="公司股票代碼")
    shortName: str = Field(description="公司常用簡稱")
    englishName: str = Field(description="公司英文名稱簡寫")
    period: Period
    requested_fields: List[RequestedField]


def dump_log_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def remove_search_text(payload: object) -> object:
    if isinstance(payload, dict):
        return {
            key: remove_search_text(value)
            for key, value in payload.items()
            if key != "search_text"
        }
    if isinstance(payload, list):
        return [remove_search_text(item) for item in payload]
    return payload


def summarize_candidates(candidates: List[Dict], limit: Optional[int] = None) -> List[Dict]:
    items = candidates[:limit] if limit is not None else candidates
    return [
        {
            "concept_name": candidate.get("concept_name"),
            "statement_type": candidate.get("statement_type"),
            "code": candidate.get("code"),
            "zh_tw": candidate.get("zh_tw"),
            "en": candidate.get("en"),
            "mapping_canonical_zh": candidate.get("mapping_canonical_zh"),
            "mapping_canonical_en": candidate.get("mapping_canonical_en"),
            "mapping_aliases": candidate.get("mapping_aliases", [])[:8],
            "score": candidate.get("score"),
            "score_breakdown": candidate.get("score_breakdown"),
            "mapped_from": candidate.get("mapped_from"),
            "mapping_queries": candidate.get("mapping_queries"),
            "dictionary_sources": candidate.get("dictionary_sources", []),
        }
        for candidate in items
    ]


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


def resolve_company(schema: Dict) -> Dict:
    code_to_company_map, name_to_company_map = build_company_maps()
    company_identifiers = [
        schema.get("companyCode"),
        schema.get("companyName"),
        schema.get("shortName"),
        schema.get("englishName"),
    ]

    for index, identifier in enumerate(company_identifiers):
        if not identifier:
            continue
        found_company = (
            code_to_company_map.get(identifier)
            if index == 0
            else name_to_company_map.get(identifier)
        )
        if found_company is None:
            matches = [
                item
                for item in CompanyStockCodeArray
                if any(
                    isinstance(value, str) and identifier in value
                    for value in item.values()
                )
            ]
            found_company = matches[0] if matches else None
        if found_company:
            schema["companyName"] = found_company["companyName"]
            schema["companyCode"] = found_company["companyCode"]
            schema["shortName"] = found_company["shortName"]
            schema["englishName"] = found_company["englishName"]
            return schema
    return schema


def resolve_company_profile(company_code: str) -> Dict[str, Optional[str]]:
    profile = {
        "industry_type": None,
        "report_scope": None,
        "report_id_pattern": None,
    }
    if not company_code:
        return profile

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT industry_type, report_scope, report_id
            FROM report_instance
            WHERE company_code = ?
            ORDER BY year DESC, quarter DESC
            LIMIT 1
            """,
            (company_code,),
        ).fetchone()
        if not row:
            return profile

        report_id = row["report_id"]
        report_id_pattern = None
        if report_id and company_code in report_id:
            report_id_pattern = report_id.replace(company_code, "{company_code}")

        report_scope = row["report_scope"]
        if not report_scope and report_id:
            report_id_lower = report_id.lower()
            for scope in ("cr", "er", "ir", "sr"):
                if f"-{scope}-" in report_id_lower:
                    report_scope = scope.upper()
                    break

        return {
            "industry_type": row["industry_type"],
            "report_scope": report_scope,
            "report_id_pattern": report_id_pattern,
        }
    finally:
        connection.close()


def extract_question_schema(question: str) -> Dict:
    parser = JsonOutputParser(pydantic_object=QuestionSchema)
    prompt = PromptTemplate(
        template="""盡可能回覆問題，並組成指定格式。無法取得資訊的欄位填入空字串。
companyName 一定要從問題中取出文字代入。
quarter 請回傳 1 到 4 的整數。

問題：{question}
格式：{format_instructions}""",
        input_variables=["question"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    print("[exact_query] extract_question_schema prompt:\n" + prompt.format(question=question))
    chain = prompt | chat_model | parser
    return chain.invoke({"question": question})


def filter_candidates(candidates: List[Dict]) -> List[Dict]:
    filtered = []
    for candidate in candidates:
        concept_name = candidate.get("concept_name") or ""
        if any(concept_name.startswith(prefix) for prefix in METADATA_FIELD_PREFIXES):
            continue
        filtered.append(candidate)
    return filtered


def dedupe_candidates(candidates: List[Dict]) -> List[Dict]:
    deduped = {}
    for candidate in candidates:
        concept_name = candidate.get("concept_name")
        statement_type = candidate.get("statement_type")
        key = (concept_name, statement_type)
        if not concept_name:
            continue
        existing = deduped.get(key)
        if existing is None or float(candidate.get("score") or 0) > float(existing.get("score") or 0):
            deduped[key] = candidate
    return list(deduped.values())


def normalize_statement_types(statement_types: List[str]) -> List[str]:
    normalized = []
    for statement_type in statement_types:
        if statement_type in VALID_STATEMENT_TYPES and statement_type not in normalized:
            normalized.append(statement_type)
    return normalized


def normalize_field_name(text: Optional[str]) -> str:
    if not text:
        return ""
    normalized = str(text).strip().lower()
    normalized = normalized.replace("（", "(").replace("）", ")")
    normalized = re.sub(r"[\s、，,／/]+", "", normalized)
    normalized = re.sub(r"[()（）]", "", normalized)
    return normalized


def field_name_match_score(left: Optional[str], right: Optional[str]) -> float:
    left_norm = normalize_field_name(left)
    right_norm = normalize_field_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.92
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def build_statement_type_candidates(
    field_name: str,
    statement_types: List[str],
    company_code: Optional[str],
    industry_type: Optional[str],
    limit_per_type: int = 8,
) -> List[Dict]:
    normalized_types = normalize_statement_types(statement_types) or list(VALID_STATEMENT_TYPES)
    all_candidates: List[Dict] = []
    candidate_logs: List[Dict] = []
    for statement_type in normalized_types:
        candidates = filter_candidates(
            find_candidates(
                field_name,
                statement_type,
                limit=limit_per_type,
                company_code=company_code,
                industry_type=industry_type,
            )
        )
        dictionary_sources = search_item_source_paths(statement_type, company_code)
        candidate_logs.append(
            {
                "field_name": field_name,
                "statement_type": statement_type,
                "dictionary_sources": dictionary_sources,
                "candidate_count": len(candidates),
                "candidates": summarize_candidates(
                    [
                        {
                            **candidate,
                            "statement_type": statement_type,
                            "dictionary_sources": dictionary_sources,
                        }
                        for candidate in candidates
                    ]
                ),
            }
        )
        for candidate in candidates:
            all_candidates.append(
                {
                    **candidate,
                    "statement_type": statement_type,
                    "dictionary_sources": dictionary_sources,
                }
            )

    deduped_candidates = dedupe_candidates(all_candidates)
    deduped_candidates.sort(
        key=lambda item: (
            -float(item.get("score") or 0),
            item.get("statement_type") or "",
            item.get("code") or "",
            item.get("concept_name") or "",
        )
    )
    print(
        "[exact_query] candidate_search_by_statement_type:\n"
        + dump_log_payload(candidate_logs)
    )
    print(
        "[exact_query] candidate_pool_after_merge:\n"
        + dump_log_payload(
            {
                "field_name": field_name,
                "requested_statement_types": normalized_types,
                "merged_candidate_count": len(deduped_candidates),
                "candidates": summarize_candidates(deduped_candidates),
            }
        )
    )
    return deduped_candidates


def select_candidate(
    user_question: str,
    field_name: str,
    statement_types: List[str],
    candidates: List[Dict],
) -> Optional[Dict]:
    if not candidates:
        print(
            "[exact_query] candidate_selection_skipped:\n"
            + dump_log_payload(
                {
                    "field_name": field_name,
                    "reason": "no_candidates",
                    "statement_types": statement_types,
                }
            )
        )
        return None
    if len(candidates) == 1:
        print(
            "[exact_query] candidate_selection_single_candidate:\n"
            + dump_log_payload(
                {
                    "field_name": field_name,
                    "statement_types": statement_types,
                    "selected_candidate": summarize_candidates(candidates, limit=1)[0],
                }
            )
        )
        return candidates[0]

    options = [
        {
            "concept_name": item.get("concept_name"),
            "statement_type": item.get("statement_type"),
            "code": item.get("code"),
            "zh_tw": item.get("zh_tw"),
            "en": item.get("en"),
            "mapping_canonical_zh": item.get("mapping_canonical_zh"),
            "mapping_canonical_en": item.get("mapping_canonical_en"),
            "mapping_aliases": item.get("mapping_aliases", [])[:8],
            "score": item.get("score"),
            "dictionary_sources": item.get("dictionary_sources", []),
        }
        for item in candidates
    ]
    print(
        "==========[exact_query] options:\n"
        + dump_log_payload(
            {
                "options": options
            }
        )
    )

    prompt = f"""
你是一個財報欄位對應助手。
請依照使用者問題，從候選清單中選出最符合的候選欄位。
你必須同時考慮 concept_name 與 statement_type，因為不同報表可能有相似欄位。
只能從候選清單中挑選。
只回答 JSON，不要解釋。

### 允許的報表別
{statement_types}

### 使用者問題
{user_question}

### 使用者要找的欄位
{field_name}

### 候選清單
{options}
"""
    parser = JsonOutputParser(pydantic_object=SelectedCandidateSchema)
    prompt_with_format = (
        prompt
        + f"""

### JSON 格式
{parser.get_format_instructions()}
"""
    )
    print("[exact_query] candidate_selection prompt:\n" + prompt_with_format)
    response = chat_model.invoke(prompt_with_format)
    raw_response = get_message_text(response)
    print(
        "[exact_query] candidate_selection_llm_raw_response:\n"
        + dump_log_payload(
            {
                "field_name": field_name,
                "statement_types": statement_types,
                "raw_response": raw_response,
            }
        )
    )
    parsed = parser.parse(raw_response)
    print("[exact_query] parsed:", parsed)

    concept_name = parsed.get("concept_name")
    chosen_statement_type = parsed.get("statement_type")
    for candidate in candidates:
        if (
            candidate.get("concept_name") == concept_name
            and candidate.get("statement_type") == chosen_statement_type
        ):
            print(
                "[exact_query] candidate_selection_result:\n"
                + dump_log_payload(
                    {
                        "field_name": field_name,
                        "statement_types": statement_types,
                        "selection_mode": "llm_exact_match",
                        "selected_candidate": summarize_candidates([candidate], limit=1)[0],
                    }
                )
            )
            return candidate
    for candidate in candidates:
        if candidate.get("concept_name") == concept_name:
            print(
                "[exact_query] candidate_selection_result:\n"
                + dump_log_payload(
                    {
                        "field_name": field_name,
                        "statement_types": statement_types,
                        "selection_mode": "llm_concept_match_fallback_statement_type",
                        "selected_candidate": summarize_candidates([candidate], limit=1)[0],
                        "llm_output": parsed,
                    }
                )
            )
            return candidate
    print(
        "[exact_query] candidate_selection_result:\n"
        + dump_log_payload(
            {
                "field_name": field_name,
                "statement_types": statement_types,
                "selection_mode": "fallback_first_candidate",
                "selected_candidate": summarize_candidates(candidates, limit=1)[0],
                "llm_output": parsed,
            }
        )
    )
    return candidates[0]


class SelectedCandidateSchema(BaseModel):
    concept_name: str = Field(description="從候選清單中選出的 concept_name")
    statement_type: str = Field(description="該 concept_name 對應的報表類型")


def fetch_financial_value(
    company_code: str,
    year: int,
    quarter: int,
    statement_type: str,
    concept_id: str,
    industry_type: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    if statement_type not in VALID_STATEMENT_TYPES:
        return None

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
            CASE
                WHEN ? IS NOT NULL AND ri.industry_type = ? THEN 0
                WHEN ? IS NOT NULL AND (ri.industry_type IS NULL OR ri.industry_type = '') THEN 1
                ELSE 2
            END,
            CASE WHEN xf.segment_json IS NULL THEN 0 ELSE 1 END,
            CASE WHEN xf.unit_id = 'TWD' THEN 0 ELSE 1 END,
            ABS(fmv.value) DESC
        LIMIT 1
        """
        params = (
            company_code,
            year,
            f"Q{quarter}",
            concept_id,
            statement_type,
            industry_type,
            industry_type,
            industry_type,
        )
        row = connection.execute(query, params).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def resolve_answer_data(
    schema: Dict,
    company_profile: Dict[str, Optional[str]],
    selected_candidate: Dict,
    candidates: List[Dict],
) -> tuple[Optional[Dict], Dict, List[Dict]]:
    ordered_candidates = [selected_candidate] + [
        item
        for item in candidates
        if (
            item.get("concept_name") != selected_candidate.get("concept_name")
            or item.get("statement_type") != selected_candidate.get("statement_type")
        )
    ]
    attempt_logs: List[Dict] = []
    for candidate in ordered_candidates:
        answer_data = fetch_financial_value(
            company_code=schema["companyCode"],
            year=schema["period"]["year"],
            quarter=schema["period"]["quarter"],
            statement_type=candidate["statement_type"],
            concept_id=candidate["concept_name"],
            industry_type=company_profile.get("industry_type"),
        )
      
      
        if answer_data:
            return answer_data, candidate, attempt_logs
        
    print(f"========No Answer Data Found for field '{schema.get('requested_fields', [{}])[0].get('field')}' with candidates:\n{dump_log_payload(ordered_candidates)}")
    return None, selected_candidate, attempt_logs


def exact_query(state: OverallState) -> OverallState:
    started_at = perf_counter()
    logger.info("[exact_query] input state:\n%s", dump_log_payload(state))
    step_started_at = perf_counter()
    schema = extract_question_schema(state["user_input"])
    schema = resolve_company(schema)
    company_profile = resolve_company_profile(schema.get("companyCode", ""))
    print(f"[timing] exact_query.extract_question_schema_and_resolve_company took {perf_counter() - step_started_at:.3f}s")

    requested_fields = schema.get("requested_fields", [])
    if not requested_fields:
        return {
            **state,
            "answer": "無法從問題中辨識要查詢的財務欄位。",
        }

    state_statement_types = normalize_statement_types(state.get("statement_types", []))
    statement_type_result = state.get("statement_type_result", {})
    field_mapping_list = statement_type_result.get("field_mappings", [])

    def resolve_field_statement_types(field_name: str) -> List[str]:
        best_mapping = None
        best_score = 0.0
        for mapping in field_mapping_list:
            score = field_name_match_score(mapping.get("field_name"), field_name)
            if score > best_score:
                best_mapping = mapping
                best_score = score
            if score >= 0.999:
                types = normalize_statement_types(mapping.get("statement_types", []))
                primary = mapping.get("primary_statement_type")
                if primary in VALID_STATEMENT_TYPES and primary not in types:
                    types.insert(0, primary)
                print(
                    "[exact_query] resolve_field_statement_types matched_mapping:\n"
                    + dump_log_payload(
                        {
                            "target_field": field_name,
                            "matched_field_name": mapping.get("field_name"),
                            "match_mode": "exact_normalized",
                            "match_score": round(score, 3),
                            "statement_types": types,
                            "primary_statement_type": primary,
                        }
                    )
                )
                return types
        if best_mapping and best_score >= 0.72:
            types = normalize_statement_types(best_mapping.get("statement_types", []))
            primary = best_mapping.get("primary_statement_type")
            if primary in VALID_STATEMENT_TYPES and primary not in types:
                types.insert(0, primary)
            print(
                "[exact_query] resolve_field_statement_types matched_mapping:\n"
                + dump_log_payload(
                    {
                        "target_field": field_name,
                        "matched_field_name": best_mapping.get("field_name"),
                        "match_mode": "best_fuzzy_match",
                        "match_score": round(best_score, 3),
                        "statement_types": types,
                        "primary_statement_type": primary,
                    }
                )
            )
            return types
        if state.get("statement_type") in VALID_STATEMENT_TYPES:
            print(
                "[exact_query] resolve_field_statement_types fallback:\n"
                + dump_log_payload(
                    {
                        "target_field": field_name,
                        "fallback_mode": "state.statement_type",
                        "statement_types": [state["statement_type"]],
                    }
                )
            )
            return [state["statement_type"]]
        if state_statement_types:
            print(
                "[exact_query] resolve_field_statement_types fallback:\n"
                + dump_log_payload(
                    {
                        "target_field": field_name,
                        "fallback_mode": "state.statement_types",
                        "statement_types": state_statement_types,
                    }
                )
            )
            return state_statement_types
        print(
            "[exact_query] resolve_field_statement_types fallback:\n"
            + dump_log_payload(
                {
                    "target_field": field_name,
                    "fallback_mode": "all_valid_statement_types",
                    "statement_types": list(VALID_STATEMENT_TYPES),
                }
            )
        )
        return list(VALID_STATEMENT_TYPES)

    field_results = []
    unresolved_fields = []

    for requested_field in requested_fields:
        target_field = requested_field["field"]
        target_statement_types = resolve_field_statement_types(target_field)

        step_started_at = perf_counter()
        candidates = build_statement_type_candidates(
            field_name=target_field,
            statement_types=target_statement_types,
            company_code=schema.get("companyCode"),
            industry_type=company_profile.get("industry_type"),
            limit_per_type=8,
        )
        print(
            f"[timing] exact_query.find_candidates took {perf_counter() - step_started_at:.3f}s "
            f"(field={target_field}, statement_types={target_statement_types})"
        )

        if not candidates:
            unresolved_fields.append(
                {
                    "field": target_field,
                    "statement_types": target_statement_types,
                    "reason": "找不到對應的資料字典欄位",
                }
            )
            continue

        step_started_at = perf_counter()
        selected_candidate = select_candidate(
            user_question=state["user_input"],
            field_name=target_field,
            statement_types=target_statement_types,
            candidates=candidates,
        )
        print(
            f"[timing] exact_query.select_candidate took {perf_counter() - step_started_at:.3f}s "
            f"(field={target_field})"
        )
        if not selected_candidate:
            unresolved_fields.append(
                {
                    "field": target_field,
                    "statement_types": target_statement_types,
                    "reason": "無法判斷對應的財報欄位",
                }
            )
            continue

        step_started_at = perf_counter()
        answer_data, resolved_candidate, attempt_logs = resolve_answer_data(
            schema=schema,
            company_profile=company_profile,
            selected_candidate=selected_candidate,
            candidates=candidates,
        )
        print(
            f"[timing] exact_query.resolve_answer_data took {perf_counter() - step_started_at:.3f}s "
            f"(field={target_field})"
        )

        debug_payload = {
            "query_context": {
                "company_code": schema["companyCode"],
                "company_name": schema["companyName"],
                "year": schema["period"]["year"],
                "quarter": schema["period"]["quarter"],
                "company_profile": company_profile,
                "statement_types": target_statement_types,
                "target_field": target_field,
                "selected_candidate": {
                    "concept_name": selected_candidate.get("concept_name"),
                    "statement_type": selected_candidate.get("statement_type"),
                    "code": selected_candidate.get("code"),
                    "zh_tw": selected_candidate.get("zh_tw"),
                    "en": selected_candidate.get("en"),
                },
                "candidate_count": len(candidates),
            },
            "candidates": [
                {
                    "concept_name": candidate.get("concept_name"),
                    "statement_type": candidate.get("statement_type"),
                    "code": candidate.get("code"),
                    "zh_tw": candidate.get("zh_tw"),
                    "en": candidate.get("en"),
                    "score": candidate.get("score"),
                }
                for candidate in candidates
            ],
            "attempts": attempt_logs,
        }
        logger.info("[exact_query] lookup debug:\n%s", dump_log_payload(debug_payload))

        field_result = {
            "field": target_field,
            "requested_statement_types": target_statement_types,
            "selected_candidate": resolved_candidate,
            "candidates": candidates,
            "answer_data": answer_data,
            "attempts": attempt_logs,
        }
        field_results.append(field_result)

        if not answer_data:
            unresolved_fields.append(
                {
                    "field": target_field,
                    "statement_types": target_statement_types,
                    "selected_candidate": resolved_candidate,
                    "reason": "已完成欄位比對，但查無主期間資料",
                }
            )

    resolved_field_results = [
        remove_search_text(item)
        for item in field_results
        if item.get("answer_data") is not None
    ]
    if not resolved_field_results:
        return {
            **state,
            "answer": "已完成欄位比對，但目前查無可回覆的財務數值。",
            "reference_data": {
                "schema": schema,
                "company_profile": company_profile,
                "statement_type_result": statement_type_result,
                "field_results": field_results,
                "unresolved_fields": unresolved_fields,
            },
        }

    final_prompt = f"""
你是一個專業的信用徵審團隊助手，請根據資料庫查到的財務報表資料直接回答問題。
若問題一次要求多個欄位，請逐項列出。
若答案為數字，請保留正負號，加入千分位格式，並帶出單位。
若該欄位中文名稱存在，優先用中文欄位名稱表達。
若有些欄位查不到，請簡短註明哪些欄位查無主期間資料。
不要臆測，僅根據提供資料回答。

### 問題
{state['user_input']}

### 查詢條件
公司：{schema['companyName']} ({schema['companyCode']})
期間：{schema['period']['year']} 年 Q{schema['period']['quarter']}
公司申報分類：{dump_log_payload(company_profile)}
整體報表分類：{state_statement_types or statement_type_result.get('statement_types', [])}

### 各欄位查詢結果
{dump_log_payload(resolved_field_results)}

### 未查得欄位
{dump_log_payload(unresolved_fields)}
"""

    print("[exact_query] final_answer prompt:\n" + final_prompt)
    step_started_at = perf_counter()
    final_answer = get_message_text(chat_model.invoke(final_prompt))
    print(f"[timing] exact_query.final_answer_generation took {perf_counter() - step_started_at:.3f}s")
    print("[exact_query] final_answer:\n" + str(final_answer))
    print(f"[timing] exact_query.total took {perf_counter() - started_at:.3f}s")
    return {
        **state,
        "answer": final_answer,
        "reference_data": {
            "schema": schema,
            "company_profile": company_profile,
            "statement_type_result": statement_type_result,
            "field_results": field_results,
            "resolved_field_results": resolved_field_results,
            "unresolved_fields": unresolved_fields,
        },
    }
