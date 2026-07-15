from typing import Any

from docx import Document

from src.features.report_generator.services.docx._python_docx_common import (
    add_heading,
    add_metric_table,
    add_spacer,
    execute_query,
    format_value,
)
from src.features.report_generator.services.docx.table_mapping import BALANCE_SHEET_MAP, label


BALANCE_SHEET_COLUMNS = (
    "year,quarter,retained_earnings,other_accounts_receivable,other_current_assets,"
    "inventory,accounts_receivable,total_equity,current_liabilities,current_assets,"
    "cash,capital_stock,total_liabilities_and_equity,capital_reserve,total_assets,"
    "non_current_liabilities,non_current_assets"
)


def format_thousand_unit(value: Any) -> str:
    if isinstance(value, (int, float)):
        return format_value(value / 1000)
    return format_value(value)


def establish_balance_sheet(
    year: int,
    gui_no: str,
    db: Any,
    document: Any = None,
) -> Any:
    document = document or Document()
    rows = execute_query(
        db,
        f"SELECT {BALANCE_SHEET_COLUMNS} FROM balance_sheet "
        f"WHERE year = {year} AND gui_no = {gui_no} ORDER BY quarter ASC;",
    )
    rows_by_quarter = {int(row.get("quarter")): row for row in rows if row.get("quarter") is not None}

    add_heading(document, "資產負債分析", size=18)
    for quarter in (1, 2, 3, 4):
        add_heading(document, f"{year}年第{quarter}季", size=12)
        row = rows_by_quarter.get(quarter, {})
        table_rows = [
            (label(BALANCE_SHEET_MAP, key), format_thousand_unit(value))
            for key, value in row.items()
            if key not in {"year", "quarter"}
        ]
        add_metric_table(document, table_rows, value_header="數值（仟元）")
        add_spacer(document, 2)

    return document
