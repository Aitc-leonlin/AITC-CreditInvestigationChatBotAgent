from typing import Any

from docx import Document

from src.features.report_generator.services.docx._python_docx_common import (
    add_heading,
    add_key_value_table,
    add_spacer,
    add_text,
    execute_query,
    format_value,
)
from src.features.report_generator.services.report_section_analysis_service import generate_report_section_analysis


INDUSTRY_FINANCIAL_KEYS = {
    "revenue": "營業收入",
    "gross_margin": "毛利率",
    "net_profit_margin": "純益率",
    "inventory_turnover": "存貨週轉率",
    "accounts_receivable_turnover": "應收款項週轉率",
    "total_asset_turnover": "總資產週轉率",
    "cash_flow_ratio": "現金流量比率",
    "debt_to_asset_ratio": "負債佔資產比率",
}


def connection_rows(db: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    connection = getattr(db, "connection", None)
    if connection is None:
        return []
    try:
        cursor = connection.execute(sql, params)
    except Exception:
        return []
    rows = cursor.fetchall()
    if rows and isinstance(rows[0], dict):
        return [dict(row) for row in rows]
    keys = [column[0] for column in cursor.description or []]
    return [dict(zip(keys, row)) for row in rows]


def company_profile_context(gui_no: str, db: Any) -> dict[str, Any]:
    rows = connection_rows(
        db,
        """
        SELECT company_code, company_name, company_short_name, industry_code,
               paid_in_capital, incorporation_date, listing_date,
               financial_statement_type, cpa_firm
        FROM company_profile
        WHERE company_code = ? OR tax_id = ?
        LIMIT 1
        """,
        (gui_no, gui_no),
    )
    if rows:
        return rows[0]

    fallback_rows = execute_query(
        db,
        "SELECT stock_code, full_name_zhtw, short_name_zhtw, industry_main, "
        f"capital, founded_date, listed_market FROM company_profile WHERE gui_no = {gui_no};",
    )
    return fallback_rows[0] if fallback_rows else {}


def latest_report_context(gui_no: str, db: Any) -> dict[str, Any]:
    rows = connection_rows(
        db,
        """
        SELECT company_code, year, quarter, industry_type, module,
               report_scope, period_start, period_end
        FROM report_instance
        WHERE company_code = ?
        ORDER BY year DESC, CAST(REPLACE(quarter, 'Q', '') AS INTEGER) DESC
        LIMIT 1
        """,
        (gui_no,),
    )
    return rows[0] if rows else {}


def knowledge_rows(gui_no: str, company_profile: dict[str, Any], db: Any) -> dict[str, Any]:
    company_name = str(company_profile.get("company_name") or company_profile.get("full_name_zhtw") or "")
    company_short_name = str(
        company_profile.get("company_short_name") or company_profile.get("short_name_zhtw") or ""
    )
    like_terms = [term for term in (gui_no, company_name, company_short_name) if term]

    if not like_terms:
        return {"warehouse_data": [], "expert_knowledge": []}

    where_clause = " OR ".join("company_label LIKE ?" for _ in like_terms)
    params = tuple(f"%{term}%" for term in like_terms)
    warehouse_data = connection_rows(
        db,
        f"""
        SELECT category, title, industry, company_label, summary, source,
               url, record_updated_at
        FROM warehouse_data_entry
        WHERE deleted_at IS NULL
          AND (({where_clause}) OR company_label = 'All')
        ORDER BY COALESCE(record_updated_at, updated_at, created_at) DESC
        LIMIT 5
        """,
        params,
    )
    expert_knowledge = connection_rows(
        db,
        f"""
        SELECT title, data_source, industry, company_label,
               anchor_description, system_prompt
        FROM expert_knowledge_entry
        WHERE deleted_at IS NULL
          AND (({where_clause}) OR company_label = 'All')
        ORDER BY updated_at DESC
        LIMIT 5
        """,
        params,
    )
    return {
        "warehouse_data": warehouse_data,
        "expert_knowledge": expert_knowledge,
    }


def build_industry_environment_context(gui_no: str, db: Any) -> dict[str, Any]:
    profile = company_profile_context(gui_no, db)
    report_context = latest_report_context(gui_no, db)
    knowledge_context = knowledge_rows(gui_no, profile, db)
    year = report_context.get("year")

    ratio_row: dict[str, Any] = {}
    financial_trends: list[dict[str, Any]] = []
    if year:
        ratio_rows = execute_query(
            db,
            f"SELECT * FROM financial_ratios WHERE year = {year} AND gui_no = {gui_no};",
        )
        ratio_row = ratio_rows[0] if ratio_rows else {}
        financial_trends = (
            db._query_financial_trends(int(year))
            if hasattr(db, "_query_financial_trends")
            else []
        )

    return {
        "company_profile": profile,
        "report_context": report_context,
        "industry_knowledge": knowledge_context,
        "financial_indicators": {
            key: {"label": label, "value": ratio_row.get(key)}
            for key, label in INDUSTRY_FINANCIAL_KEYS.items()
        },
        "financial_trends": financial_trends,
    }


def add_analysis_text(document: Any, text: str) -> None:
    paragraph = document.add_paragraph()
    for index, line in enumerate((text or "").splitlines()):
        if index:
            paragraph.add_run().add_break()
        add_text(paragraph, line, size=12)


def establish_industry_environment_analysis(
    gui_no: str,
    db: Any,
    document: Any = None,
) -> Any:
    document = document or Document()
    context = build_industry_environment_context(gui_no, db)
    profile = context["company_profile"]
    report_context = context["report_context"]
    knowledge_context = context["industry_knowledge"]

    analysis_text = generate_report_section_analysis(
        section_title="產業環境分析",
        analysis_goal=(
            "結合公司所屬產業、內部知識庫與倉儲資料、營收與毛利/週轉/現金流指標，"
            "評估產業環境對授信風險與未來營運的影響。"
        ),
        context=context,
    )

    add_heading(document, "產業環境分析", size=18)
    add_key_value_table(
        document,
        [
            ("公司名稱", format_value(profile.get("company_name") or profile.get("full_name_zhtw"))),
            ("股票代號", format_value(profile.get("company_code") or profile.get("stock_code") or gui_no)),
            ("產業代碼", format_value(profile.get("industry_code") or profile.get("industry_main"))),
            ("XBRL 產業類型", format_value(report_context.get("industry_type"))),
            ("財報模組", format_value(report_context.get("module"))),
            ("倉儲資料筆數", format_value(len(knowledge_context.get("warehouse_data") or []))),
            ("專家知識筆數", format_value(len(knowledge_context.get("expert_knowledge") or []))),
        ],
        header=("項目", "內容"),
    )
    add_spacer(document, 1)

    add_heading(document, "AI 產業環境分析", size=12)
    add_analysis_text(document, analysis_text)
    add_spacer(document, 2)
    return document
