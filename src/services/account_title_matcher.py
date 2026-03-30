import json
import re
import sqlite3
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Optional


SERVICES_DIR = Path(__file__).parent
DICTIONARY_PATH = SERVICES_DIR / "xbrl_data_dictionary_all.json"
SPLIT_DIR = SERVICES_DIR / "xbrl_dictionary_splits"
DB_PATH = SERVICES_DIR.parent.parent / "FinancialStatementXBRL.db"

STATEMENT_FILTERS = {
    "balance_sheet": {
        "role_keywords": ["BalanceSheet"],
        "families": {"BSCI"},
    },
    "comprehensive_income_statement": {
        "role_keywords": ["StatementOfComprehensiveIncome"],
        "families": {"BSCI"},
    },
    "statement_of_cash_flows": {
        "role_keywords": ["StatementOfCashFlows"],
        "families": {"SCF"},
    },
}


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text)


def extract_tokens(text: Optional[str]) -> List[str]:
    if not text:
        return []
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.lower())
    return [token for token in cleaned.split() if token]


@lru_cache(maxsize=1)
def load_dictionary() -> List[Dict]:
    return json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def load_dictionary_file(path_text: str) -> List[Dict]:
    path = Path(path_text)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def split_file_path(statement_type: str, family: Optional[str] = None) -> Path:
    statement_dir = SPLIT_DIR / statement_type
    file_name = "__all__.json" if not family else f"{family}.json"
    return statement_dir / file_name


def family_variants(family: str) -> List[str]:
    variants = [family]
    if "_" in family:
        variants.append(family.replace("_", "-"))
    if "-" in family:
        variants.append(family.replace("-", "_"))
    return list(dict.fromkeys(variant for variant in variants if variant))


@lru_cache(maxsize=256)
def get_company_families(company_code: str) -> tuple[str, ...]:
    if not company_code or not DB_PATH.exists():
        return ()
    connection = sqlite3.connect(DB_PATH)
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT
                   CASE
                       WHEN instr(tc.taxonomy_id, ':') > 0 THEN substr(tc.taxonomy_id, instr(tc.taxonomy_id, ':') + 1)
                       ELSE tc.taxonomy_id
                   END AS family
            FROM financial_metric_value AS fmv
            JOIN report_instance AS ri
              ON ri.report_id = fmv.report_id
            JOIN taxonomy_concept AS tc
              ON tc.concept_id = fmv.concept_id
            WHERE ri.company_code = ?
              AND tc.taxonomy_id IS NOT NULL
              AND tc.taxonomy_id <> ''
            ORDER BY family
            """,
            (company_code,),
        ).fetchall()
        return tuple(row[0] for row in rows if row and row[0])
    finally:
        connection.close()


def dedupe_items(items: List[Dict]) -> List[Dict]:
    seen = {}
    for item in items:
        concept_name = item.get("concept_name")
        if concept_name and concept_name not in seen:
            seen[concept_name] = item
    return list(seen.values())


def load_search_items(statement_type: str, company_code: Optional[str] = None) -> List[Dict]:
    if statement_type not in STATEMENT_FILTERS:
        return load_dictionary()

    loaded_items: List[Dict] = []
    families = get_company_families(company_code) if company_code else ()
    for family in families:
        for family_variant in family_variants(family):
            family_path = split_file_path(statement_type, family_variant)
            loaded_items.extend(load_dictionary_file(str(family_path)))

    if loaded_items:
        return dedupe_items(loaded_items)

    statement_all_path = split_file_path(statement_type)
    statement_items = load_dictionary_file(str(statement_all_path))
    if statement_items:
        return dedupe_items(statement_items)

    return load_dictionary()


def role_matches(item: Dict, statement_type: str) -> bool:
    # print("item =", item)
    config = STATEMENT_FILTERS.get(statement_type)
    # print("config =", config)
    if not config:
        has_code = bool(item.get("code"))
        # print("has_code =", has_code)
        return has_code
    families = set(item.get("families", []))
    # print("families =", families)
    roles = item.get("roles", [])
    # print("roles =", roles)
    family_match = bool(families & config["families"])
    # print("family_match =", family_match)
    role_match = any(
        keyword in role
        for role in roles
        for keyword in config["role_keywords"]
    )
    # print("role_match =", role_match)
    if statement_type == "statement_of_cash_flows":
        has_code = bool(item.get("code"))
        # print("has_code =", has_code)
        final_result = has_code and (family_match or role_match)
        # print("final_result =", final_result)
        return final_result
    has_code = bool(item.get("code"))
    # print("has_code =", has_code)
    final_result = has_code and family_match and role_match
    # print("final_result =", final_result)
    return final_result


def build_mapping_queries(item: Dict) -> List[str]:
    queries: List[str] = []
    for value in [
        item.get("zh_tw"),
        item.get("en"),
        item.get("name"),
    ]:
        if isinstance(value, str) and value.strip():
            queries.append(value.strip())
    return list(dict.fromkeys(queries))


def score_item(item: Dict, query: str) -> float:
    query_norm = normalize_text(query)
    if not query_norm:
        return 0.0

    texts = [
        item.get("zh_tw"),
        item.get("en"),
        item.get("name"),
        item.get("concept_name"),
        item.get("search_text"),
    ]
    normalized_texts = [normalize_text(text) for text in texts if text]
    if not normalized_texts:
        return 0.0

    score = 0.0
    for text in normalized_texts:
        if query_norm == text:
            score = max(score, 100.0)
        elif query_norm and query_norm in text:
            score = max(score, 90.0)
        elif text and text in query_norm:
            score = max(score, 85.0)
        score = max(score, SequenceMatcher(None, query_norm, text).ratio() * 70.0)

    query_tokens = set(extract_tokens(query))
    for text in texts:
        item_tokens = set(extract_tokens(text))
        if query_tokens and item_tokens:
            overlap = len(query_tokens & item_tokens)
            score += overlap * 8.0

    if item.get("zh_tw") and normalize_text(item["zh_tw"]).startswith(query_norm[: min(len(query_norm), 4)]):
        score += 5.0

    if item.get("code") and re.search(r"\d", item["code"]):
        score += 1.0

    return score


def score_item_with_mapping(item: Dict, original_query: str, mapping_queries: List[str]) -> float:
    score = score_item(item, original_query)
    if mapping_queries:
        mapping_scores = [score_item(item, query) for query in mapping_queries if query]
        if mapping_scores:
            score = max(score, max(mapping_scores))
            score += max(mapping_scores) * 0.1
    return score


def map_query_to_dictionary(field_name: str, items: List[Dict], limit: int = 5) -> List[Dict]:
    scored = []
    for item in items:
        if not item.get("code"):
            continue
        score = score_item(item, field_name)
        if score <= 0:
            continue
        scored.append(
            {
                "item": item,
                "score": round(score, 3),
                "mapping_queries": build_mapping_queries(item),
            }
        )

    scored.sort(
        key=lambda payload: (
            -payload["score"],
            payload["item"].get("code") or "",
            payload["item"].get("concept_name") or "",
        )
    )
    return scored[:limit]


def find_candidates(
    field_name: str,
    statement_type: str,
    limit: int = 8,
    company_code: Optional[str] = None,
) -> List[Dict]:
    started_at = perf_counter()
    step_started_at = perf_counter()
    items = load_search_items(statement_type, company_code)
    print(
        f"[timing] account_title_matcher.load_search_items took {perf_counter() - step_started_at:.3f}s "
        f"(statement_type={statement_type}, company_code={company_code}, items={len(items)})"
    )

    step_started_at = perf_counter()
    mapped_items = map_query_to_dictionary(field_name, items, limit=5)
    print(
        f"[timing] account_title_matcher.map_query_to_dictionary took {perf_counter() - step_started_at:.3f}s "
        f"(field_name={field_name}, mapped_items={len(mapped_items)})"
    )
    mapped_role_items = [
        payload for payload in mapped_items
        if role_matches(payload["item"], statement_type)
    ]
    primary_mapped_items = (mapped_role_items[:1] or mapped_items[:1])
    mapping_queries = list(
        dict.fromkeys(
            query
            for payload in primary_mapped_items
            for query in payload["mapping_queries"]
        )
    )
    filtered = [item for item in items if role_matches(item, statement_type)]
    scored_by_concept = {}

    step_started_at = perf_counter()
    for payload in primary_mapped_items:
        item = payload["item"]
        scored_by_concept[item.get("concept_name")] = {
            "concept_name": item.get("concept_name"),
            "zh_tw": item.get("zh_tw"),
            "en": item.get("en"),
            "code": item.get("code"),
            "families": item.get("families", []),
            "roles": item.get("roles", []),
            "search_text": item.get("search_text"),
            "score": round(payload["score"] + 100.0, 3),
            "mapped_from": field_name,
            "mapping_queries": mapping_queries[:8],
        }

    for item in filtered:
        score = score_item_with_mapping(item, field_name, mapping_queries)
        if score <= 0:
            continue
        concept_name = item.get("concept_name")
        current = scored_by_concept.get(concept_name)
        candidate = {
            "concept_name": concept_name,
            "zh_tw": item.get("zh_tw"),
            "en": item.get("en"),
            "code": item.get("code"),
            "families": item.get("families", []),
            "roles": item.get("roles", []),
            "search_text": item.get("search_text"),
            "score": round(score, 3),
            "mapped_from": field_name,
            "mapping_queries": mapping_queries[:8],
        }
        if current is None or candidate["score"] > current["score"]:
            scored_by_concept[concept_name] = candidate
    print(
        f"[timing] account_title_matcher.score_and_filter_candidates took {perf_counter() - step_started_at:.3f}s "
        f"(filtered={len(filtered)}, scored={len(scored_by_concept)})"
    )

    scored = list(scored_by_concept.values())

    scored.sort(
        key=lambda item: (
            -item["score"],
            item.get("code") or "",
            item.get("concept_name") or "",
        )
    )
    print(
        f"[timing] account_title_matcher.find_candidates.total took {perf_counter() - started_at:.3f}s "
        f"(field_name={field_name}, statement_type={statement_type}, company_code={company_code}, limit={limit})"
    )
    return scored[:limit]
