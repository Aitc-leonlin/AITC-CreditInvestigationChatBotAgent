from typing import Any

from docx import Document

from src.services.docx._python_docx_common import (
    add_heading,
    add_key_value_table,
    add_spacer,
    add_text,
    execute_query,
    format_value,
)
from src.services.report_section_analysis_service import generate_report_section_analysis


REPAYMENT_RATIO_LABELS = {
    "current_ratio": "流動比率",
    "quick_ratio": "速動比率",
    "interest_coverage_ratio": "利息保障倍數",
    "debt_to_asset_ratio": "負債佔資產比率",
    "cash_flow_ratio": "現金流量比率",
    "roe": "權益報酬率",
    "roa": "資產報酬率",
    "net_profit_margin": "純益率",
}

REPAYMENT_SOURCE_METRICS = (
    ("cash", "現金及約當現金", "balance_sheet", ("ifrs-full_CashAndCashEquivalents",)),
    ("current_assets", "流動資產", "balance_sheet", ("ifrs-full_CurrentAssets",)),
    ("current_liabilities", "流動負債", "balance_sheet", ("ifrs-full_CurrentLiabilities",)),
    ("total_liabilities", "負債總額", "balance_sheet", ("ifrs-full_Liabilities",)),
    ("non_current_liabilities", "非流動負債", "balance_sheet", ("ifrs-full_NoncurrentLiabilities",)),
    ("total_equity", "權益總額", "balance_sheet", ("ifrs-full_Equity",)),
    ("bank_loan", "銀行借款", "balance_sheet", ("tifrs-bsci-ci_BankLoan",)),
    (
        "current_portion_longterm_borrowings",
        "一年內到期長期借款",
        "balance_sheet",
        ("ifrs-full_CurrentPortionOfLongtermBorrowings",),
    ),
    (
        "long_term_bank_loans",
        "銀行長期借款",
        "balance_sheet",
        ("ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived",),
    ),
    ("revenue", "營業收入", "comprehensive_income_statement", ("ifrs-full_Revenue", "tifrs-bsci-ins_OperatingRevenue")),
    ("net_profit", "稅後淨利", "comprehensive_income_statement", ("ifrs-full_ProfitLossAttributableToOwnersOfParent", "ifrs-full_ProfitLoss")),
    ("pre_tax_profit", "稅前淨利", "comprehensive_income_statement", ("ifrs-full_ProfitLossBeforeTax", "tifrs-SCF_ProfitLossBeforeTax")),
    ("interest_expense", "利息費用", "comprehensive_income_statement", ("tifrs-notes_InterestExpense_n", "ifrs-full_InterestExpense")),
    (
        "cash_from_operations",
        "營業活動現金流量",
        "statement_of_cash_flows",
        ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
    ),
)


def metric_value(db: Any, year: int, statement_type: str, field_ids: tuple[str, ...]) -> Any:
    if not hasattr(db, "_year_metric_value"):
        return None
    return db._year_metric_value(statement_type, year, field_ids)


def build_repayment_ability_context(year: int, gui_no: str, db: Any) -> dict[str, Any]:
    rows = execute_query(
        db,
        f"SELECT * FROM financial_ratios WHERE year = {year} AND gui_no = {gui_no};",
    )
    ratio_row = rows[0] if rows else {}

    source_metrics = {
        key: {
            "label": label,
            "value": metric_value(db, year, statement_type, field_ids),
        }
        for key, label, statement_type, field_ids in REPAYMENT_SOURCE_METRICS
    }
    ratio_metrics = {
        key: {
            "label": label,
            "value": ratio_row.get(key),
            "calculation_reason": ratio_row.get(f"{key}_calculation_reason", ""),
        }
        for key, label in REPAYMENT_RATIO_LABELS.items()
    }
    financial_trends = (
        db._query_financial_trends(year)
        if hasattr(db, "_query_financial_trends")
        else []
    )

    return {
        "company_code": gui_no,
        "year": year,
        "repayment_ratio_metrics": ratio_metrics,
        "source_financial_metrics": source_metrics,
        "financial_trends": financial_trends,
    }


def add_analysis_text(document: Any, text: str) -> None:
    paragraph = document.add_paragraph()
    for index, line in enumerate((text or "").splitlines()):
        if index:
            paragraph.add_run().add_break()
        add_text(paragraph, line, size=12)


def establish_repayment_ability_analysis(
    year: int,
    gui_no: str,
    db: Any,
    document: Any = None,
) -> Any:
    document = document or Document()
    context = build_repayment_ability_context(year, gui_no, db)
    ratio_metrics = context["repayment_ratio_metrics"]

    analysis_text = generate_report_section_analysis(
        section_title="還款能力分析",
        analysis_goal=(
            "評估公司以本業獲利、營業現金流、短期流動性、借款結構與利息負擔"
            "支應授信還款的能力。"
        ),
        context=context,
    )

    add_heading(document, "還款能力分析", size=18)
    add_key_value_table(
        document,
        [
            (item["label"], format_value(item["value"]))
            for item in ratio_metrics.values()
        ],
        header=("指標", f"{year}年數值"),
    )
    add_spacer(document, 1)

    add_heading(document, "AI 還款能力分析", size=12)
    add_analysis_text(document, analysis_text)
    add_spacer(document, 2)
    return document
