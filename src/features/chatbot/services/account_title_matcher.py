import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from src.shared.database.connection import database_storage_exists, open_database_connection
from src.shared.database.db_path import PROJECT_ROOT


XBRL_DATA_DIR = PROJECT_ROOT / "src" / "features" / "chatbot" / "services"
DICTIONARY_PATH = XBRL_DATA_DIR / "xbrl_data_dictionary_all.json"
MAPPING_PATH = XBRL_DATA_DIR / "xbrl_mapping" / "concept_mapping.json"
SPLIT_DIR = XBRL_DATA_DIR / "xbrl_dictionary_splits"
KNOWN_INDUSTRY_TYPES = ("basi", "bd", "ci", "fh", "ins", "mim")

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


@lru_cache(maxsize=1)
def load_concept_mapping_by_id() -> Dict[str, Dict]:
    if not MAPPING_PATH.exists():
        return {}
    records = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return {
        record["concept_id"]: record
        for record in records
        if isinstance(record, dict) and record.get("concept_id")
    }


def enrich_item_with_mapping(item: Dict) -> Dict:
    concept_name = item.get("concept_name")
    mapping = load_concept_mapping_by_id().get(concept_name)
    if not mapping:
        return item
    enriched = dict(item)
    enriched["mapping_canonical_zh"] = mapping.get("canonical_zh")
    enriched["mapping_canonical_en"] = mapping.get("canonical_en")
    enriched["mapping_aliases"] = mapping.get("aliases", [])
    enriched["mapping_statement_types"] = mapping.get("statement_types", [])
    enriched["mapping_industry_types"] = mapping.get("industry_types", [])
    return enriched


def enrich_items_with_mapping(items: List[Dict]) -> List[Dict]:
    return [enrich_item_with_mapping(item) for item in items]


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
    if not company_code:
        return ()
    if not database_storage_exists():
        return ()
    connection = open_database_connection()
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT tc.taxonomy_id
            FROM financial_metric_value AS fmv
            JOIN report_instance AS ri
              ON ri.report_id = fmv.report_id
            JOIN taxonomy_concept AS tc
              ON tc.concept_id = fmv.concept_id
            WHERE ri.company_code = ?
              AND tc.taxonomy_id IS NOT NULL
              AND tc.taxonomy_id <> ''
            ORDER BY tc.taxonomy_id
            """,
            (company_code,),
        ).fetchall()
        families = {
            taxonomy_id.partition(":")[2] or taxonomy_id
            for row in rows
            if row and (taxonomy_id := str(row["taxonomy_id"] or ""))
        }
        return tuple(sorted(families))
    finally:
        connection.close()


@lru_cache(maxsize=512)
def get_company_available_concepts(
    company_code: str,
    statement_type: str,
    industry_type: Optional[str] = None,
) -> tuple[str, ...]:
    if not company_code:
        return ()
    if not database_storage_exists():
        return ()

    conditions = [
        "ri.company_code = ?",
        "fmv.concept_id IS NOT NULL",
        "fmv.concept_id <> ''",
        "(fd.statement_type = ? OR fd.statement_type IS NULL)",
    ]
    params: List[Optional[str]] = [company_code, statement_type]

    if industry_type:
        conditions.append("ri.industry_type = ?")
        params.append(industry_type)

    query = f"""
        SELECT DISTINCT fmv.concept_id
        FROM financial_metric_value AS fmv
        JOIN report_instance AS ri
          ON ri.report_id = fmv.report_id
        LEFT JOIN field_dictionary AS fd
          ON fd.field_id = fmv.field_id
        WHERE {' AND '.join(conditions)}
        ORDER BY fmv.concept_id
    """

    connection = open_database_connection()
    try:
        rows = connection.execute(query, params).fetchall()
        return tuple(row["concept_id"] for row in rows if row and row["concept_id"])
    finally:
        connection.close()


def dedupe_items(items: List[Dict]) -> List[Dict]:
    seen = {}
    for item in items:
        concept_name = item.get("concept_name")
        if concept_name and concept_name not in seen:
            seen[concept_name] = item
    return list(seen.values())


def normalize_profile_token(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.strip().lower().replace("_", "-")


def collect_item_source_texts(item: Dict) -> List[str]:
    texts: List[str] = []
    for key in ("source_files", "source_hrefs", "families"):
        value = item.get(key)
        if isinstance(value, list):
            texts.extend(str(entry) for entry in value if entry)
        elif value:
            texts.append(str(value))

    for presentation_item in item.get("presentation") or []:
        if not isinstance(presentation_item, dict):
            continue
        source_file = presentation_item.get("source_file")
        if source_file:
            texts.append(str(source_file))
        path = presentation_item.get("path")
        if isinstance(path, list):
            texts.extend(str(entry) for entry in path if entry)
        elif path:
            texts.append(str(path))
        parent_concept = presentation_item.get("parent_concept")
        if parent_concept:
            texts.append(str(parent_concept))
    return texts


def item_matches_industry_type(item: Dict, industry_type: Optional[str]) -> bool:
    token = normalize_profile_token(industry_type)
    if not token:
        return False

    sources = [text.lower() for text in collect_item_source_texts(item)]
    concept_name = str(item.get("concept_name") or "").lower()
    search_text = str(item.get("search_text") or "").lower()
    candidates = sources + [concept_name, search_text]

    patterns = (
        f"-{token}-",
        f"_{token}_",
        f"_{token}-",
        f"-{token}_",
        f"bsci-{token}",
        f"notes-{token}",
        f"/{token}/",
    )
    return any(pattern in text for text in candidates for pattern in patterns)


def detect_item_industry_types(item: Dict) -> List[str]:
    sources = [text.lower() for text in collect_item_source_texts(item)]
    concept_name = str(item.get("concept_name") or "").lower()
    search_text = str(item.get("search_text") or "").lower()
    candidates = sources + [concept_name, search_text]

    matched = []
    for token in KNOWN_INDUSTRY_TYPES:
        patterns = (
            f"-{token}-",
            f"_{token}_",
            f"_{token}-",
            f"-{token}_",
            f"bsci-{token}",
            f"notes-{token}",
            f"/{token}/",
        )
        if any(pattern in text for text in candidates for pattern in patterns):
            matched.append(token)
    return matched


def extract_profile_specific_queries(item: Dict, industry_type: Optional[str]) -> List[str]:
    token = normalize_profile_token(industry_type)
    if not token:
        return []

    queries: List[str] = []
    for presentation_item in item.get("presentation") or []:
        if not isinstance(presentation_item, dict):
            continue
        source_file = str(presentation_item.get("source_file") or "").lower()
        if f"bsci-{token}" not in source_file and f"/{token}/" not in source_file and f"scf-{token}" not in source_file:
            continue

        path = presentation_item.get("path")
        if isinstance(path, list):
            queries.extend(str(entry) for entry in path if entry)
        elif path:
            queries.append(str(path))

        parent_concept = presentation_item.get("parent_concept")
        if parent_concept:
            queries.append(str(parent_concept))

    # Some items have no presentation path but still expose source markers in source_files.
    if not queries and item_matches_industry_type(item, industry_type):
        for value in (item.get("zh_tw"), item.get("en"), item.get("name"), item.get("concept_name")):
            if isinstance(value, str) and value.strip():
                queries.append(value.strip())

    return list(dict.fromkeys(query for query in queries if query))


def load_search_items(statement_type: str, company_code: Optional[str] = None) -> List[Dict]:
    if statement_type not in STATEMENT_FILTERS:
        return enrich_items_with_mapping(load_dictionary())

    loaded_items: List[Dict] = []
    families = get_company_families(company_code) if company_code else ()
    for family in families:
        for family_variant in family_variants(family):
            family_path = split_file_path(statement_type, family_variant)
            loaded_items.extend(load_dictionary_file(str(family_path)))

    if loaded_items:
        return enrich_items_with_mapping(dedupe_items(loaded_items))

    statement_all_path = split_file_path(statement_type)
    statement_items = load_dictionary_file(str(statement_all_path))
    if statement_items:
        return enrich_items_with_mapping(dedupe_items(statement_items))

    return enrich_items_with_mapping(load_dictionary())


def filter_items_by_industry_type(items: List[Dict], industry_type: Optional[str]) -> List[Dict]:
    target_token = normalize_profile_token(industry_type)
    if not target_token:
        return items

    filtered_items = []
    for item in items:
        matched_tokens = set(detect_item_industry_types(item))
        if not matched_tokens or target_token in matched_tokens:
            filtered_items.append(item)
    return filtered_items


def search_item_source_paths(statement_type: str, company_code: Optional[str] = None) -> List[str]:
    if statement_type not in STATEMENT_FILTERS:
        return [str(DICTIONARY_PATH)]

    source_paths: List[str] = []
    families = get_company_families(company_code) if company_code else ()
    for family in families:
        for family_variant in family_variants(family):
            family_path = split_file_path(statement_type, family_variant)
            if load_dictionary_file(str(family_path)):
                source_paths.append(str(family_path))

    if source_paths:
        return list(dict.fromkeys(source_paths))

    statement_all_path = split_file_path(statement_type)
    if load_dictionary_file(str(statement_all_path)):
        return [str(statement_all_path)]

    return [str(DICTIONARY_PATH)]


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
    return score_item_details(item, query)["total"]


def score_item_details(item: Dict, query: str) -> Dict[str, object]:
    query_norm = normalize_text(query)
    if not query_norm:
        return {
            "query": query,
            "query_norm": query_norm,
            "base_match": 0.0,
            "best_text": None,
            "best_match_type": None,
            "token_overlap_bonus": 0.0,
            "prefix_bonus": 0.0,
            "code_bonus": 0.0,
            "total": 0.0,
        }

    texts = [
        item.get("zh_tw"),
        item.get("en"),
        item.get("mapping_canonical_zh"),
        item.get("mapping_canonical_en"),
        item.get("name"),
        item.get("concept_name"),
    ]
    for alias in item.get("mapping_aliases", []):
        if isinstance(alias, str) and alias.strip():
            texts.append(alias.strip())
    normalized_texts = [normalize_text(text) for text in texts if text]
    if not normalized_texts:
        return {
            "query": query,
            "query_norm": query_norm,
            "base_match": 0.0,
            "best_text": None,
            "best_match_type": None,
            "token_overlap_bonus": 0.0,
            "prefix_bonus": 0.0,
            "code_bonus": 0.0,
            "total": 0.0,
        }

    score = 0.0
    best_text = None
    best_match_type = None
    has_exact_match = False
    for raw_text, text in zip([text for text in texts if text], normalized_texts):
        candidate_score = SequenceMatcher(None, query_norm, text).ratio() * 70.0
        match_type = "sequence_matcher"
        if query_norm == text:
            candidate_score = 100.0
            match_type = "exact_match"
            has_exact_match = True
        elif query_norm and query_norm in text:
            candidate_score = 90.0
            match_type = "query_in_text"
        elif text and text in query_norm:
            candidate_score = 85.0
            match_type = "text_in_query"
        if candidate_score > score:
            score = candidate_score
            best_text = raw_text
            best_match_type = match_type

    query_tokens = set(extract_tokens(query))
    token_overlap_bonus = 0.0
    for text in texts:
        item_tokens = set(extract_tokens(text))
        if query_tokens and item_tokens:
            overlap = len(query_tokens & item_tokens)
            token_overlap_bonus += overlap * 8.0
    score += token_overlap_bonus

    prefix_bonus = 0.0
    if item.get("zh_tw") and normalize_text(item["zh_tw"]).startswith(query_norm[: min(len(query_norm), 4)]):
        prefix_bonus = 5.0
        score += prefix_bonus

    code_bonus = 0.0
    if item.get("code") and re.search(r"\d", item["code"]):
        code_bonus = 1.0
        score += code_bonus

    if not has_exact_match:
        score = min(score, 99.0)

    return {
        "query": query,
        "query_norm": query_norm,
        "base_match": round(score - token_overlap_bonus - prefix_bonus - code_bonus, 3),
        "best_text": best_text,
        "best_match_type": best_match_type,
        "token_overlap_bonus": round(token_overlap_bonus, 3),
        "prefix_bonus": round(prefix_bonus, 3),
        "code_bonus": round(code_bonus, 3),
        "total": round(score, 3),
    }


def score_query_against_texts(query: str, texts: List[str]) -> float:
    return score_query_against_texts_details(query, texts)["total"]


def score_query_against_texts_details(query: str, texts: List[str]) -> Dict[str, object]:
    query_norm = normalize_text(query)
    if not query_norm:
        return {
            "query": query,
            "query_norm": query_norm,
            "base_match": 0.0,
            "best_text": None,
            "best_match_type": None,
            "token_overlap_bonus": 0.0,
            "total": 0.0,
        }

    normalized_texts = [normalize_text(text) for text in texts if text]
    if not normalized_texts:
        return {
            "query": query,
            "query_norm": query_norm,
            "base_match": 0.0,
            "best_text": None,
            "best_match_type": None,
            "token_overlap_bonus": 0.0,
            "total": 0.0,
        }

    score = 0.0
    query_tokens = set(extract_tokens(query))
    token_overlap_bonus = 0.0
    best_text = None
    best_match_type = None
    has_exact_match = False
    raw_texts = [text for text in texts if text]
    for raw_text, text in zip(raw_texts, normalized_texts):
        candidate_score = SequenceMatcher(None, query_norm, text).ratio() * 70.0
        match_type = "sequence_matcher"
        if query_norm == text:
            candidate_score = 100.0
            match_type = "exact_match"
            has_exact_match = True
        elif query_norm in text:
            candidate_score = 90.0
            match_type = "query_in_text"
        elif text in query_norm:
            candidate_score = 85.0
            match_type = "text_in_query"
        if candidate_score > score:
            score = candidate_score
            best_text = raw_text
            best_match_type = match_type

        item_tokens = set(extract_tokens(text))
        if query_tokens and item_tokens:
            token_overlap_bonus += len(query_tokens & item_tokens) * 8.0
    score += token_overlap_bonus
    if not has_exact_match:
        score = min(score, 99.0)
    return {
        "query": query,
        "query_norm": query_norm,
        "base_match": round(score - token_overlap_bonus, 3),
        "best_text": best_text,
        "best_match_type": best_match_type,
        "token_overlap_bonus": round(token_overlap_bonus, 3),
        "total": round(score, 3),
    }


def score_component_summary(details: Optional[Dict[str, object]]) -> Optional[Dict[str, float]]:
    if details is None:
        return None
    component_keys = (
        "base_match",
        "token_overlap_bonus",
        "prefix_bonus",
        "code_bonus",
        "total",
    )
    return {
        key: round(float(details.get(key) or 0.0), 3)
        for key in component_keys
        if key in details
    }


def score_item_with_mapping(item: Dict, original_query: str, mapping_queries: List[str]) -> float:
    return score_item_with_mapping_details(item, original_query, mapping_queries)["total"]


def score_item_with_mapping_details(item: Dict, original_query: str, mapping_queries: List[str]) -> Dict[str, object]:
    base_details = score_item_details(item, original_query)
    score = float(base_details["total"])
    best_mapping_score = 0.0
    if mapping_queries:
        mapping_details = [score_item_details(item, query) for query in mapping_queries if query]
        if mapping_details:
            best_mapping = max(mapping_details, key=lambda detail: float(detail["total"]))
            best_mapping_score = float(best_mapping["total"])
            score = max(score, best_mapping_score)
            score += best_mapping_score * 0.1
    return {
        "base_query_score": score_component_summary(base_details),
        "best_mapping_score": round(best_mapping_score, 3),
        "mapping_bonus": round(best_mapping_score * 0.1 if best_mapping_score else 0.0, 3),
        "total": round(score, 3),
    }


def score_item_with_profile(
    item: Dict,
    original_query: str,
    mapping_queries: List[str],
    industry_type: Optional[str] = None,
) -> float:
    return score_item_with_profile_details(
        item,
        original_query,
        mapping_queries,
        industry_type=industry_type,
    )["total"]


def score_item_with_profile_details(
    item: Dict,
    original_query: str,
    mapping_queries: List[str],
    industry_type: Optional[str] = None,
) -> Dict[str, object]:
    mapping_details = score_item_with_mapping_details(item, original_query, mapping_queries)
    score = float(mapping_details["total"])
    target_token = normalize_profile_token(industry_type)
    if not target_token:
        return {
            "base_query_score": mapping_details["base_query_score"],
            "best_mapping_score": mapping_details["best_mapping_score"],
            "mapping_bonus": mapping_details["mapping_bonus"],
            "profile_query_score": None,
            "profile_query_bonus": 0.0,
            "industry_bonus": 0.0,
            "industry_penalty": 0.0,
            "total": round(score, 3),
        }

    profile_queries = extract_profile_specific_queries(item, industry_type)
    profile_details = None
    profile_query_bonus = 0.0
    if profile_queries:
        profile_details = score_query_against_texts_details(original_query, profile_queries)
        profile_score = float(profile_details["total"])
        if profile_score > 0:
            score = max(score, profile_score)
            profile_query_bonus = profile_score * 0.15
            score += profile_query_bonus

    matched_tokens = detect_item_industry_types(item)
    industry_bonus = 0.0
    industry_penalty = 0.0
    if target_token in matched_tokens:
        industry_bonus = 12.0
        score += industry_bonus
    elif matched_tokens:
        industry_penalty = 18.0
        score -= industry_penalty
    return {
        "base_query_score": mapping_details["base_query_score"],
        "best_mapping_score": mapping_details["best_mapping_score"],
        "mapping_bonus": mapping_details["mapping_bonus"],
        "profile_query_score": score_component_summary(profile_details),
        "profile_query_bonus": round(profile_query_bonus, 3),
        "industry_bonus": round(industry_bonus, 3),
        "industry_penalty": round(industry_penalty, 3),
        "total": round(score, 3),
    }


def profile_sort_key(payload: Dict, field_name: str, industry_type: Optional[str]) -> tuple:
    item = payload["item"]
    profile_score = score_item_with_profile(
        item,
        field_name,
        payload.get("mapping_queries", []),
        industry_type=industry_type,
    )
    return (
        -round(profile_score, 3),
        item.get("code") or "",
        item.get("concept_name") or "",
    )


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
    industry_type: Optional[str] = None,
) -> List[Dict]:
    items = load_search_items(statement_type, company_code)
    items = filter_items_by_industry_type(items, industry_type)

    mapped_items = map_query_to_dictionary(field_name, items, limit=5)
    mapped_role_items = [
        payload for payload in mapped_items
        if role_matches(payload["item"], statement_type)
    ]
    mapped_role_items.sort(
        key=lambda payload: profile_sort_key(payload, field_name, industry_type)
    )
    mapped_items.sort(
        key=lambda payload: profile_sort_key(payload, field_name, industry_type)
    )
    primary_mapped_items = []
    mapping_queries: List[str] = []
    filtered = [item for item in items if role_matches(item, statement_type)]

    available_concepts = set(
        get_company_available_concepts(
            company_code or "",
            statement_type,
            industry_type=industry_type,
        )
    ) if company_code else set()
    if available_concepts:
        filtered = [
            item for item in filtered
            if item.get("concept_name") in available_concepts
        ]
        mapped_role_items = [
            payload for payload in mapped_role_items
            if payload["item"].get("concept_name") in available_concepts
        ]
        mapped_items = [
            payload for payload in mapped_items
            if payload["item"].get("concept_name") in available_concepts
        ]

    scored_by_concept = {}

    for payload in primary_mapped_items:
        item = payload["item"]
        score_details = score_item_with_profile_details(
            item,
            field_name,
            mapping_queries,
            industry_type=industry_type,
        )
        scored_by_concept[item.get("concept_name")] = {
            "concept_name": item.get("concept_name"),
            "zh_tw": item.get("zh_tw"),
            "en": item.get("en"),
            "mapping_canonical_zh": item.get("mapping_canonical_zh"),
            "mapping_canonical_en": item.get("mapping_canonical_en"),
            "mapping_aliases": item.get("mapping_aliases", []),
            "code": item.get("code"),
            "families": item.get("families", []),
            "roles": item.get("roles", []),
            "search_text": item.get("search_text"),
            "score": round(float(score_details["total"]) + 100.0, 3),
            "score_breakdown": {
                **score_details,
                "primary_mapping_boost": 100.0,
                "total": round(float(score_details["total"]) + 100.0, 3),
            },
            "mapped_from": field_name,
            "mapping_queries": mapping_queries[:8],
        }

    for item in filtered:
        score_details = score_item_with_profile_details(
            item,
            field_name,
            mapping_queries,
            industry_type=industry_type,
        )
        score = float(score_details["total"])
        if score <= 0:
            continue
        concept_name = item.get("concept_name")
        current = scored_by_concept.get(concept_name)
        candidate = {
            "concept_name": concept_name,
            "zh_tw": item.get("zh_tw"),
            "en": item.get("en"),
            "mapping_canonical_zh": item.get("mapping_canonical_zh"),
            "mapping_canonical_en": item.get("mapping_canonical_en"),
            "mapping_aliases": item.get("mapping_aliases", []),
            "code": item.get("code"),
            "families": item.get("families", []),
            "roles": item.get("roles", []),
            "search_text": item.get("search_text"),
            "score": round(score, 3),
            "score_breakdown": score_details,
            "mapped_from": field_name,
            "mapping_queries": mapping_queries[:8],
        }
        if current is None or candidate["score"] > current["score"]:
            scored_by_concept[concept_name] = candidate

    scored = list(scored_by_concept.values())

    scored.sort(
        key=lambda item: (
            -item["score"],
            item.get("code") or "",
            item.get("concept_name") or "",
        )
    )
    return scored[:limit]
