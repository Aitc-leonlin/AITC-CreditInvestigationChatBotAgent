from typing import Any

from docx import Document

from src.features.report_generator.services.docx._python_docx_common import (
    add_heading,
    add_metric_table,
    add_spacer,
    add_text,
    execute_query,
    format_value,
)
from src.features.report_generator.services.docx.table_mapping import FINANCIAL_RATIOS_MAP, label


GENERAL_FINANCIAL_RATIO_COLUMNS = (
    "year,gui_no,average_collection_period,total_asset_turnover,roe,"
    "average_days_sales_outstanding,net_profit_margin,debt_to_asset_ratio,"
    "pre_tax_profit_to_capital_ratio,long_term_capital_to_fixed_assets_ratio,"
    "current_ratio,interest_coverage_ratio,roa,cash_reinvestment_ratio,"
    "cash_adequacy_ratio,quick_ratio,accounts_receivable_turnover,"
    "fixed_assets_turnover,inventory_turnover,cash_flow_ratio,eps"
)

GENERAL_FINANCIAL_RATIO_DISPLAY_KEYS = tuple(
    key
    for key in GENERAL_FINANCIAL_RATIO_COLUMNS.split(",")
    if key not in {"year", "gui_no"}
)

INSURANCE_FINANCIAL_RATIO_DISPLAY_KEYS = (
    "debt_to_asset_ratio",
    "insurance_liabilities_to_assets_ratio",
    "insurance_liabilities_change_rate",
    "net_worth_ratio",
    "roa",
    "roe",
    "net_profit_margin",
    "operating_profit_margin",
    "pre_tax_profit_margin",
    "net_profit_growth_rate",
    "equity_growth_rate",
    "eps",
)


def ratio_display_value(ratio_row: dict[str, Any], key: str) -> str:
    value = ratio_row.get(key)
    if value is not None and value != "":
        return format_value(value)
    return str(
        ratio_row.get(f"{key}_calculation_reason")
        or "缺乏計算所需資料。"
    )


def establish_financial_ratios(
    year: int,
    gui_no: str,
    ai_summary_text: str,
    db: Any,
    document: Any = None,
) -> Any:
    document = document or Document()
    rows = execute_query(
        db,
        f"SELECT * FROM financial_ratios WHERE year = {year} AND gui_no = {gui_no};",
    )
    ratio_row = rows[0] if rows else {}
    display_keys = (
        INSURANCE_FINANCIAL_RATIO_DISPLAY_KEYS
        if str(ratio_row.get("industry_type") or "").strip().upper() == "INS"
        else GENERAL_FINANCIAL_RATIO_DISPLAY_KEYS
    )

    add_heading(document, "財務比率分析", size=18)
    add_metric_table(
        document,
        [
            (label(FINANCIAL_RATIOS_MAP, key), ratio_display_value(ratio_row, key))
            for key in display_keys
        ],
        value_header=f"{year}年",
    )
    add_spacer(document, 2)

    add_heading(document, "基於資產負債表得出結論", size=18)
    summary = document.add_paragraph()
    for index, line in enumerate((ai_summary_text or "").splitlines()):
        if index:
            summary.add_run().add_break()
        add_text(summary, line, size=12)
    return document
