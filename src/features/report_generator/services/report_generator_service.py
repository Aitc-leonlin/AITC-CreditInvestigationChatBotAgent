import json
import math
import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.shared.database.db_path import PROJECT_ROOT, resolve_sqlite_db_path
from src.shared.database.connection import (
    get_table_columns,
    is_postgresql,
    open_database_connection,
    table_exists,
)
from src.shared.database.serialization import database_json_dumps
from src.features.membership.services.bootstrap_service import apply_xbrl_migration
from src.features.report_generator.services.docx.document_merge_service import merge_all_chapters
from src.features.report_generator.services.report_llm_conclusion_service import generate_report_llm_conclusion


BALANCE_SHEET_FIELD_CODE_MAP = {
    "retained_earnings": ("ifrs-full_RetainedEarnings",),
    "other_accounts_receivable": ("ifrs-full_OtherCurrentReceivables", "ifrs-full_OtherReceivables"),
    "other_current_assets": ("ifrs-full_OtherCurrentAssets",),
    "inventory": ("ifrs-full_Inventories",),
    "accounts_receivable": ("tifrs-bsci-ci_AccountsReceivableNet",),
    "total_equity": ("ifrs-full_Equity",),
    "current_liabilities": ("ifrs-full_CurrentLiabilities",),
    "current_assets": ("ifrs-full_CurrentAssets",),
    "cash": ("ifrs-full_CashAndCashEquivalents",),
    "capital_stock": ("ifrs-full_IssuedCapital",),
    "total_liabilities_and_equity": ("ifrs-full_EquityAndLiabilities",),
    "capital_reserve": ("ifrs-full_CapitalReserve",),
    "total_assets": ("ifrs-full_Assets",),
    "non_current_liabilities": ("ifrs-full_NoncurrentLiabilities",),
    "non_current_assets": ("ifrs-full_NoncurrentAssets",),
}

INCOME_FIELD_MAP = {
    "revenue": ("ifrs-full_Revenue", "tifrs-bsci-ins_OperatingRevenue"),
    "gross_profit": ("tifrs-bsci-ci_GrossProfitLossFromOperations",),
    "operating_profit": ("ifrs-full_ProfitLossFromOperatingActivities",),
    "pre_tax_profit": ("ifrs-full_ProfitLossBeforeTax", "tifrs-SCF_ProfitLossBeforeTax"),
    "net_profit": (
        "ifrs-full_ProfitLossAttributableToOwnersOfParent",
        "ifrs-full_ProfitLoss",
    ),
    "eps": ("ifrs-full_BasicEarningsLossPerShare",),
}

CASH_FLOW_FIELD_MAP = {
    "cash_from_operations": ("ifrs-full_CashFlowsFromUsedInOperatingActivities",),
}

RATIO_FIELD_MAP = {
    "paid_in_capital": ("ifrs-full_IssuedCapital",),
    "net_fixed_assets": ("ifrs-full_PropertyPlantAndEquipment",),
    "prepayments": ("ifrs-full_CurrentPrepayments", "ifrs-full_Prepayments"),
    "cost_of_goods_sold": ("ifrs-full_CostOfSales", "tifrs-bsci-ci_CostOfSales-CostOfSales"),
    "interest_expense": ("tifrs-notes_InterestExpense_n", "ifrs-full_InterestExpense"),
}

REPORT_HISTORY_TABLE = "report_generator_history"
REPORT_DASHBOARD_TABLE = "report_generator_dashboard"
REPORT_GENERATOR_OUTPUT_DIR_ENV = "REPORT_GENERATOR_OUTPUT_DIR"
LEGACY_REPORT_GENERATOR_FILE_DIR_ENV = "REPORT_GENERATOR_FILE_DIR"
REPORT_GENERATED_BY = "張小明"
REPORT_PERIOD = "Q1 ~ Q4"
REPORT_TYPE = "標準徵審報告"
REPORT_STATUS_DONE = "已完成"
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XBRL_DICTIONARY_PATH = (
    PROJECT_ROOT / "src" / "features" / "chatbot" / "services" / "xbrl_data_dictionary_all.json"
)
BALANCE_SHEET_ROLE = "BalanceSheet"


class ReportGenerationError(RuntimeError):
    pass


def report_generator_log(event: str, **details: Any) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    detail_text = " ".join(
        f"{key}={value!r}" for key, value in details.items()
    )
    suffix = f" {detail_text}" if detail_text else ""
    print(f"[report-generator][{timestamp}] {event}{suffix}", flush=True)


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value.strip())
    return sanitized.strip("_") or "credit_report"


def first_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def is_xbrl_field_id(value: str) -> bool:
    return "_" in value and (
        value.startswith("ifrs-")
        or value.startswith("tifrs-")
    )


def normalize_module_name(value: str | None) -> str:
    return (value or "").replace("_", "-").lower()


@lru_cache(maxsize=1)
def load_xbrl_dictionary_by_code() -> dict[str, tuple[dict[str, Any], ...]]:
    if not XBRL_DICTIONARY_PATH.exists():
        return {}

    with XBRL_DICTIONARY_PATH.open(encoding="utf-8") as file:
        entries = json.load(file)

    by_code: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        code = str(entry.get("code") or "").strip()
        concept_name = str(entry.get("concept_name") or "").strip()
        if not code or not concept_name:
            continue
        if entry.get("abstract"):
            continue
        roles = " ".join(str(role) for role in entry.get("roles") or [])
        if BALANCE_SHEET_ROLE not in roles:
            continue
        by_code.setdefault(code, []).append(entry)

    return {code: tuple(values) for code, values in by_code.items()}


def dictionary_entry_matches_industry(entry: dict[str, Any], industry_type: str | None) -> bool:
    if not industry_type:
        return False

    industry_token = f"tifrs-bsci-{industry_type.lower()}"
    searchable_parts: list[str] = []
    searchable_parts.extend(str(value) for value in entry.get("source_files") or [])
    searchable_parts.extend(str(value) for value in entry.get("source_hrefs") or [])
    for presentation in entry.get("presentation") or []:
        path = presentation.get("path") or []
        searchable_parts.extend(str(value) for value in path)
        searchable_parts.append(str(presentation.get("source_file") or ""))

    return industry_token in " ".join(searchable_parts).lower()


def dictionary_entry_priority(entry: dict[str, Any], industry_type: str | None, module: str | None) -> tuple[int, int, int, str]:
    concept_name = str(entry.get("concept_name") or "")
    families = {normalize_module_name(value) for value in entry.get("families") or []}
    normalized_module = normalize_module_name(module)

    if dictionary_entry_matches_industry(entry, industry_type):
        industry_score = 0
    elif concept_name.startswith("ifrs-full_"):
        industry_score = 1
    else:
        industry_score = 2

    module_score = 0 if normalized_module and normalized_module in families else 1
    if concept_name.startswith("ifrs-full_"):
        taxonomy_score = 0
    elif industry_type and f"tifrs-bsci-{industry_type.lower()}_" in concept_name.lower():
        taxonomy_score = 1
    else:
        taxonomy_score = 2

    return (industry_score, module_score, taxonomy_score, concept_name)


def safe_divide(numerator: Any, denominator: Any, multiplier: float = 1.0) -> float | None:
    left = first_number(numerator)
    right = first_number(denominator)
    if left is None or right in (None, 0):
        return None
    return round((left / right) * multiplier, 2)


def safe_add(*values: Any) -> float | None:
    numbers = [first_number(value) for value in values]
    if any(value is None for value in numbers):
        return None
    return sum(numbers)


def safe_subtract(value: Any, *subtract_values: Any) -> float | None:
    base = first_number(value)
    numbers = [first_number(item) for item in subtract_values]
    if base is None or any(item is None for item in numbers):
        return None
    return base - sum(numbers)


def safe_average(left: Any, right: Any) -> float | None:
    left_number = first_number(left)
    right_number = first_number(right)
    if left_number is None or right_number is None:
        return None
    return (left_number + right_number) / 2




def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def format_metric_value(value: Any, suffix: str = "", decimals: int = 2) -> str:
    number = first_number(value)
    if number is None:
        return "-"
    if number == int(number):
        text = str(int(number))
    else:
        text = f"{number:.{decimals}f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def amount_to_100_million(value: Any) -> float | None:
    number = first_number(value)
    if number is None:
        return None
    return round(number / 100_000_000, 2)


def missing_formula_reason(
    *,
    value: Any,
    formula: str,
    required_values: dict[str, Any],
    denominator_values: dict[str, Any] | None = None,
) -> str:
    if first_number(value) is not None:
        return ""

    missing_labels = [
        label
        for label, item in required_values.items()
        if first_number(item) is None
    ]
    if missing_labels:
        return f"無法完整計算：{formula}，缺少{', '.join(missing_labels)}。"

    zero_denominator_labels = [
        label
        for label, item in (denominator_values or {}).items()
        if first_number(item) == 0
    ]
    if zero_denominator_labels:
        return f"無法完整計算：{formula}，{', '.join(zero_denominator_labels)}為 0。"

    return f"無法完整計算：{formula}。"


def dashboard_metric(
    *,
    label: str,
    value: Any,
    trend: str,
    icon_key: str,
    suffix: str = "",
    calculation_reason: str = "",
) -> dict[str, Any]:
    metric = {
        "label": label,
        "value": format_metric_value(value, suffix),
        "trend": trend,
        "iconKey": icon_key,
        "calculationStatus": "complete" if first_number(value) is not None else "incomplete",
    }
    if calculation_reason:
        metric["calculationReason"] = calculation_reason
    return metric


def normalize_summary_items(ai_summary_text: str, company_name: str, year: int) -> list[str]:
    cleaned = " ".join(ai_summary_text.split())
    parts = [
        part.strip(" 　。；;")
        for part in re.split(r"[。；;]\s*", cleaned)
        if part.strip(" 　。；;")
    ]
    summary_items = [f"{part}。" for part in parts[:4]]
    if summary_items:
        return summary_items

    return [
        f"{company_name} {year} 年度徵審報告已完成產製。",
        "財務報表、現金流量與關鍵比率已完成彙整。",
        "AI 徵審結論已依最新可用財務資料產生。",
        "完整分析內容請下載 Word 報告檢視。",
    ]


def build_report_progress_items() -> list[dict[str, str]]:
    return [
        {"label": "基本資料生成", "status": "完成"},
        {"label": "資產負債分析生成", "status": "完成"},
        {"label": "財務比率分析生成", "status": "完成"},
        {"label": "還款能力分析生成", "status": "完成"},
        {"label": "產業環境分析生成", "status": "完成"},
        {"label": "AI 徵審結論生成", "status": "完成"},
    ]


def build_dashboard_metrics(ratio_row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dashboard_metric(
            label="ROE",
            value=ratio_row.get("roe"),
            suffix="%",
            trend="依年度財報計算",
            icon_key="barChart",
            calculation_reason=ratio_row.get("roe_calculation_reason", ""),
        ),
        dashboard_metric(
            label="流動比率",
            value=ratio_row.get("current_ratio"),
            suffix="%",
            trend="流動資產 / 流動負債",
            icon_key="trendingUp",
            calculation_reason=ratio_row.get("current_ratio_calculation_reason", ""),
        ),
        dashboard_metric(
            label="負債比率",
            value=ratio_row.get("debt_to_asset_ratio"),
            suffix="%",
            trend="負債總額 / 資產總額",
            icon_key="scale",
            calculation_reason=ratio_row.get("debt_to_asset_ratio_calculation_reason", ""),
        ),
        dashboard_metric(
            label="利息保障倍數",
            value=ratio_row.get("interest_coverage_ratio"),
            trend="稅前淨利加利息費用 / 利息費用",
            icon_key="shieldCheck",
            calculation_reason=ratio_row.get("interest_coverage_ratio_calculation_reason", ""),
        ),
        dashboard_metric(
            label="純益率",
            value=ratio_row.get("net_profit_margin"),
            suffix="%",
            trend="稅後淨利 / 營業收入",
            icon_key="trendingUp",
            calculation_reason=ratio_row.get("net_profit_margin_calculation_reason", ""),
        ),
        dashboard_metric(
            label="每股盈餘 (EPS)",
            value=ratio_row.get("eps"),
            trend="XBRL EPS 欄位",
            icon_key="dollarSign",
            calculation_reason=ratio_row.get("eps_calculation_reason", ""),
        ),
    ]


def build_dashboard_financial_trends(
    trend_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "period": str(row.get("period") or ""),
            "revenue": amount_to_100_million(row.get("revenue")),
            "netIncome": amount_to_100_million(row.get("net_profit")),
            "grossMargin": first_number(row.get("gross_margin")),
        }
        for row in trend_rows
    ]


def row_to_dashboard_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "historyId": str(row["history_id"]),
        "summaryItems": json.loads(row["summary_items_json"] or "[]"),
        "progressItems": json.loads(row["progress_items_json"] or "[]"),
        "progressPercent": row["progress_percent"],
        "metricsTitle": row["metrics_title"],
        "metrics": json.loads(row["metrics_json"] or "[]"),
        "financialTrends": json.loads(row["financial_trends_json"] or "[]"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def company_full_name_from_label(company_label: str, fallback: str) -> str:
    return company_label.split("/")[0].strip() if "/" in company_label else fallback


def generate_report_public_id() -> str:
    return secrets.token_urlsafe(32)[:43]


def generated_reports_dir() -> Path:
    configured_path = (
        os.getenv(REPORT_GENERATOR_OUTPUT_DIR_ENV, "").strip()
        or os.getenv(LEGACY_REPORT_GENERATOR_FILE_DIR_ENV, "").strip()
    )
    directory = Path(configured_path) if configured_path else PROJECT_ROOT / "generated-reports" / "credit-reports"
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    report_generator_log(
        "output_directory.create.start",
        configured=bool(configured_path),
        path=str(directory),
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        resolved_directory = directory.resolve()
    except Exception as error:
        report_generator_log(
            "output_directory.create.error",
            path=str(directory),
            error_type=type(error).__name__,
            error=str(error),
        )
        raise
    report_generator_log(
        "output_directory.create.done",
        path=str(resolved_directory),
        exists=resolved_directory.exists(),
        writable=os.access(resolved_directory, os.W_OK),
    )
    return resolved_directory


def report_history_db_path() -> Path | None:
    if is_postgresql():
        return None
    return resolve_sqlite_db_path()


def connect_report_history_db() -> Any:
    db_path = report_history_db_path()
    report_generator_log(
        "history_db.connect.start",
        engine="postgresql" if is_postgresql() else "sqlite",
        path=str(db_path) if db_path is not None else "",
    )
    if db_path is not None:
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as error:
            report_generator_log(
                "history_db.directory.error",
                path=str(db_path.parent),
                error_type=type(error).__name__,
                error=str(error),
            )
            raise
    else:
        apply_xbrl_migration()
    try:
        connection = open_database_connection()
        ensure_report_history_table(connection)
    except Exception as error:
        report_generator_log(
            "history_db.connect.error",
            engine="postgresql" if is_postgresql() else "sqlite",
            path=str(db_path) if db_path is not None else "",
            error_type=type(error).__name__,
            error=str(error),
        )
        raise
    report_generator_log("history_db.connect.done")
    return connection


def ensure_report_history_table(connection: Any) -> None:
    if is_postgresql():
        return
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REPORT_HISTORY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            company_code TEXT NOT NULL,
            company_label TEXT NOT NULL,
            year TEXT NOT NULL,
            period TEXT NOT NULL,
            report_type TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            generated_at_display TEXT NOT NULL,
            generated_by TEXT NOT NULL,
            status TEXT NOT NULL,
            file_size TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    columns = get_table_columns(connection, REPORT_HISTORY_TABLE)
    if "public_id" not in columns:
        connection.execute(f"ALTER TABLE {REPORT_HISTORY_TABLE} ADD COLUMN public_id TEXT")

    rows_without_public_id = connection.execute(
        f"SELECT id FROM {REPORT_HISTORY_TABLE} WHERE public_id IS NULL OR public_id = ''"
    ).fetchall()
    for row in rows_without_public_id:
        connection.execute(
            f"UPDATE {REPORT_HISTORY_TABLE} SET public_id = ? WHERE id = ?",
            (generate_report_public_id(), row["id"]),
        )

    connection.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{REPORT_HISTORY_TABLE}_public_id "
        f"ON {REPORT_HISTORY_TABLE}(public_id)"
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REPORT_DASHBOARD_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id INTEGER NOT NULL,
            summary_items_json TEXT NOT NULL,
            progress_items_json TEXT NOT NULL,
            progress_percent INTEGER NOT NULL,
            metrics_title TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            financial_trends_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (history_id) REFERENCES {REPORT_HISTORY_TABLE}(id) ON DELETE CASCADE
        )
        """
    )
    dashboard_columns = get_table_columns(connection, REPORT_DASHBOARD_TABLE)
    if "financial_trends_json" not in dashboard_columns:
        connection.execute(
            f"ALTER TABLE {REPORT_DASHBOARD_TABLE} "
            "ADD COLUMN financial_trends_json TEXT NOT NULL DEFAULT '[]'"
        )
    connection.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{REPORT_DASHBOARD_TABLE}_history_id "
        f"ON {REPORT_DASHBOARD_TABLE}(history_id)"
    )
    connection.commit()


class FinancialStatementsDocxAdapter:
    def __init__(self, db_path: Path | None, company_code: str, company_label: str):
        self.db_path = db_path
        self.company_code = company_code
        self.company_label = company_label
        self.connection = open_database_connection()
        self._report_context_cache: dict[tuple[int, str | None], sqlite3.Row | None] = {}

    def close(self) -> None:
        self.connection.close()

    def has_source_data(self, year: int) -> bool:
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM report_instance
            WHERE company_code = ? AND year = ?
            """,
            (self.company_code, year),
        ).fetchone()
        return bool(row and row["count"])

    def _execute(self, sql: str) -> list[dict[str, Any]]:
        normalized_sql = " ".join(sql.lower().split())
        if "from company_profile" in normalized_sql:
            return self._query_company_profile(sql)
        if "from balance_sheet" in normalized_sql:
            return self._query_balance_sheet(sql)
        if "from financial_ratios" in normalized_sql:
            return self._query_financial_ratios(sql)
        return []

    def _extract_selected_columns(self, sql: str) -> list[str]:
        match = re.search(r"select\s+(.*?)\s+from\s+", sql, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        return [
            column.strip().split()[-1]
            for column in match.group(1).split(",")
            if column.strip()
        ]

    def _extract_year(self, sql: str) -> int | None:
        match = re.search(r"\byear\s*=\s*(\d{4})", sql, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _company_name(self) -> str:
        profile_row = self._listed_company_profile_row()
        if profile_row and profile_row["company_name"]:
            return str(profile_row["company_name"])

        row = self.connection.execute(
            """
            SELECT xf.value_text AS company_name
            FROM financial_metric_value AS fmv
            JOIN xbrl_fact AS xf
              ON xf.fact_id = fmv.fact_id
            WHERE fmv.company_code = ?
              AND fmv.field_id = 'tifrs-notes_CompanyChineseName'
              AND xf.value_text IS NOT NULL
              AND xf.value_text <> ''
            ORDER BY fmv.year DESC, fmv.quarter DESC
            LIMIT 1
            """,
            (self.company_code,),
        ).fetchone()
        return str(row["company_name"]) if row and row["company_name"] else self.company_label

    def _listed_company_profile_row(self) -> sqlite3.Row | None:
        if not table_exists(self.connection, "company_profile"):
            return None
        return self.connection.execute(
            """
            SELECT *
            FROM company_profile
            WHERE company_code = ?
            LIMIT 1
            """,
            (self.company_code,),
        ).fetchone()

    def _format_yyyymmdd(self, value: Any) -> str:
        text = str(value or "").strip()
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return text

    def _query_company_profile(self, sql: str) -> list[dict[str, Any]]:
        selected_columns = self._extract_selected_columns(sql)
        row = self._listed_company_profile_row()
        company_name = str(row["company_name"]) if row and row["company_name"] else self._company_name()
        short_name = str(row["company_short_name"]) if row and row["company_short_name"] else (
            self.company_label.split("/")[-1].strip()
            if "/" in self.company_label
            else company_name
        )
        accountants = ""
        if row:
            accountants = "、".join(
                item
                for item in (str(row["cpa_1"] or "").strip(), str(row["cpa_2"] or "").strip())
                if item
            )
        management_team = ""
        if row:
            management_team = "\n".join(
                item
                for item in (
                    f"董事長：{row['chairman']}" if row["chairman"] else "",
                    f"總經理：{row['general_manager']}" if row["general_manager"] else "",
                    f"發言人：{row['spokesperson']}（{row['spokesperson_title']}）"
                    if row["spokesperson"] and row["spokesperson_title"]
                    else f"發言人：{row['spokesperson']}" if row["spokesperson"] else "",
                    f"代理發言人：{row['acting_spokesperson']}" if row["acting_spokesperson"] else "",
                )
                if item
            )
        profile = {
            "stock_code": self.company_code,
            "full_name_zhtw": company_name,
            "short_name_zhtw": short_name,
            "gui_no": str(row["tax_id"]) if row and row["tax_id"] else "",
            "address_zhtw": str(row["address"]) if row else "",
            "phone": str(row["telephone"]) if row else "",
            "fax": str(row["fax"]) if row else "",
            "website": str(row["website"]) if row else "",
            "email": str(row["email"]) if row else "",
            "industry_main": str(row["industry_code"]) if row else "",

            "ceo": str(row["chairman"]) if row else "",
            "capital": str(row["paid_in_capital"]) if row else "",
            "founded_date": self._format_yyyymmdd(row["incorporation_date"]) if row else "",
            "accountant_firm": str(row["cpa_firm"]) if row else "",
            "accountants": accountants,

            "listed_market": "上市" if row and row["listing_date"] else "",
            "par_value": str(row["par_value"]) if row else "",
            "ipo_date": self._format_yyyymmdd(row["listing_date"]) if row else "",
            "short_name_enus": str(row["english_short_name"]) if row else "",
            "address_enus": str(row["english_mailing_address"]) if row else "",
            "management_team": management_team,
            "registration_change_record": "",
            "investment_projects": "",
        }
        return [{column: profile.get(column, "") for column in selected_columns}]

    def _quarter_label(self, quarter: int | str) -> str:
        text = str(quarter).strip().upper()
        return text if text.startswith("Q") else f"Q{text}"

    def _report_context(self, year: int, quarter: int | str | None = None) -> sqlite3.Row | None:
        quarter_label = self._quarter_label(quarter) if quarter is not None else None
        cache_key = (year, quarter_label)
        if cache_key in self._report_context_cache:
            return self._report_context_cache[cache_key]

        if quarter_label is None:
            row = self.connection.execute(
                """
                SELECT industry_type, module
                FROM report_instance
                WHERE company_code = ? AND year = ?
                ORDER BY CAST(REPLACE(quarter, 'Q', '') AS INTEGER) DESC
                LIMIT 1
                """,
                (self.company_code, year),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT industry_type, module
                FROM report_instance
                WHERE company_code = ? AND year = ? AND quarter = ?
                LIMIT 1
                """,
                (self.company_code, year, quarter_label),
            ).fetchone()

        self._report_context_cache[cache_key] = row
        return row

    def _resolve_field_ids(
        self,
        identifiers: tuple[str, ...],
        year: int,
        quarter: int | str | None = None,
    ) -> tuple[str, ...]:
        if all(is_xbrl_field_id(identifier) for identifier in identifiers):
            return identifiers

        context = self._report_context(year, quarter)
        industry_type = str(context["industry_type"]) if context and context["industry_type"] else None
        module = str(context["module"]) if context and context["module"] else None
        dictionary_by_code = load_xbrl_dictionary_by_code()

        field_ids: list[str] = []
        for identifier in identifiers:
            if is_xbrl_field_id(identifier):
                candidates = ({"concept_name": identifier},)
            else:
                candidates = dictionary_by_code.get(identifier, ())

            sorted_candidates = sorted(
                candidates,
                key=lambda entry: dictionary_entry_priority(entry, industry_type, module),
            )
            for candidate in sorted_candidates:
                concept_name = str(candidate.get("concept_name") or "").strip()
                if concept_name and concept_name not in field_ids:
                    field_ids.append(concept_name)

        return tuple(field_ids)

    def _xbrl_metric_value(
        self,
        year: int,
        quarter: int | str,
        field_ids: tuple[str, ...],
    ) -> float | None:
        if not field_ids:
            return None

        placeholders = ",".join("?" for _ in field_ids)
        row = self.connection.execute(
            f"""
            SELECT fmv.value
            FROM financial_metric_value AS fmv
            JOIN report_instance AS ri
              ON ri.report_id = fmv.report_id
            LEFT JOIN xbrl_fact AS xf
              ON xf.fact_id = fmv.fact_id
            WHERE fmv.company_code = ?
              AND fmv.year = ?
              AND fmv.quarter = ?
              AND fmv.field_id IN ({placeholders})
              AND fmv.value IS NOT NULL
              AND (
                    xf.segment_json IS NULL
                    OR xf.segment_json = ''
                  )
              AND (
                    xf.instant_date = ri.period_end
                    OR (
                        xf.period_start = ri.period_start
                        AND xf.period_end = ri.period_end
                    )
                  )
            ORDER BY
              CASE fmv.field_id
                {' '.join(f"WHEN ? THEN {index}" for index, _ in enumerate(field_ids))}
                ELSE 999
              END
            LIMIT 1
            """,
            (
                self.company_code,
                year,
                self._quarter_label(quarter),
                *field_ids,
                *field_ids,
            ),
        ).fetchone()
        return first_number(row["value"]) if row else None

    def _metric_value(
        self,
        table: str,
        year: int,
        quarter: int,
        code: str | tuple[str, ...],
    ) -> float | None:
        del table
        identifiers = code if isinstance(code, tuple) else (code,)
        field_ids = self._resolve_field_ids(identifiers, year, quarter)
        return self._xbrl_metric_value(year, quarter, field_ids)

    def _year_metric_value(
        self,
        table: str,
        year: int,
        code: str | tuple[str, ...],
    ) -> float | None:
        del table
        identifiers = code if isinstance(code, tuple) else (code,)
        field_ids = self._resolve_field_ids(identifiers, year)
        if not field_ids:
            return None

        row = self.connection.execute(
            f"""
            SELECT fmv.value
            FROM financial_metric_value AS fmv
            JOIN report_instance AS ri
              ON ri.report_id = fmv.report_id
            LEFT JOIN xbrl_fact AS xf
              ON xf.fact_id = fmv.fact_id
            WHERE fmv.company_code = ?
              AND fmv.year = ?
              AND fmv.field_id IN ({",".join("?" for _ in field_ids)})
              AND fmv.value IS NOT NULL
              AND (
                    xf.segment_json IS NULL
                    OR xf.segment_json = ''
                  )
              AND (
                    xf.instant_date = ri.period_end
                    OR (
                        xf.period_start = ri.period_start
                        AND xf.period_end = ri.period_end
                    )
                  )
            ORDER BY
              CAST(REPLACE(fmv.quarter, 'Q', '') AS INTEGER) DESC,
              CASE fmv.field_id
                {' '.join(f"WHEN ? THEN {index}" for index, _ in enumerate(field_ids))}
                ELSE 999
              END
            LIMIT 1
            """,
            (self.company_code, year, *field_ids, *field_ids),
        ).fetchone()
        return first_number(row["value"]) if row else None

    def _average_year_metric_value(
        self,
        table: str,
        year: int,
        code: str | tuple[str, ...],
    ) -> float | None:
        current_value = self._year_metric_value(table, year, code)
        previous_value = self._year_metric_value(table, year - 1, code)
        return safe_average(previous_value, current_value)

    def _query_balance_sheet(self, sql: str) -> list[dict[str, Any]]:
        year = self._extract_year(sql)
        if year is None:
            return []

        rows: list[dict[str, Any]] = []
        for quarter in (1, 2, 3, 4):
            row: dict[str, Any] = {"year": year, "quarter": quarter}
            for field, code in BALANCE_SHEET_FIELD_CODE_MAP.items():
                row[field] = self._metric_value("balance_sheet", year, quarter, code)
            rows.append(row)
        return rows

    def _query_financial_trends(self, year: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        def quarter_value(
            cumulative_value: Any,
            previous_value: Any,
            quarter: int,
        ) -> float | None:
            current = first_number(cumulative_value)
            if current is None:
                return None
            if quarter == 1:
                return current
            previous = first_number(previous_value)
            if previous is None:
                return None
            return current - previous

        for trend_year in (year - 1, year):
            previous_revenue: float | None = None
            previous_net_profit: float | None = None
            previous_gross_profit: float | None = None

            for quarter in (1, 2, 3, 4):
                cumulative_revenue = self._metric_value(
                    "comprehensive_income_statement",
                    trend_year,
                    quarter,
                    INCOME_FIELD_MAP["revenue"],
                )
                cumulative_net_profit = self._metric_value(
                    "comprehensive_income_statement",
                    trend_year,
                    quarter,
                    INCOME_FIELD_MAP["net_profit"],
                )
                cumulative_gross_profit = self._metric_value(
                    "comprehensive_income_statement",
                    trend_year,
                    quarter,
                    INCOME_FIELD_MAP["gross_profit"],
                )
                cumulative_cost_of_goods_sold = self._metric_value(
                    "comprehensive_income_statement",
                    trend_year,
                    quarter,
                    RATIO_FIELD_MAP["cost_of_goods_sold"],
                )
                if cumulative_gross_profit is None:
                    cumulative_gross_profit = safe_subtract(
                        cumulative_revenue,
                        cumulative_cost_of_goods_sold,
                    )

                revenue = quarter_value(cumulative_revenue, previous_revenue, quarter)
                net_profit = quarter_value(cumulative_net_profit, previous_net_profit, quarter)
                gross_profit = quarter_value(cumulative_gross_profit, previous_gross_profit, quarter)

                rows.append(
                    {
                        "period": f"{trend_year} Q{quarter}",
                        "revenue": revenue,
                        "net_profit": net_profit,
                        "gross_margin": safe_divide(gross_profit, revenue, 100),
                    }
                )
                previous_revenue = cumulative_revenue
                previous_net_profit = cumulative_net_profit
                previous_gross_profit = cumulative_gross_profit
        return rows

    def _query_financial_ratios(self, sql: str) -> list[dict[str, Any]]:
        year = self._extract_year(sql)
        if year is None:
            return []

        revenue = self._year_metric_value("comprehensive_income_statement", year, INCOME_FIELD_MAP["revenue"])
        pre_tax_profit = self._year_metric_value("comprehensive_income_statement", year, INCOME_FIELD_MAP["pre_tax_profit"])
        net_profit = self._year_metric_value("comprehensive_income_statement", year, INCOME_FIELD_MAP["net_profit"])
        eps = self._year_metric_value("comprehensive_income_statement", year, INCOME_FIELD_MAP["eps"])
        gross_profit = self._year_metric_value("comprehensive_income_statement", year, INCOME_FIELD_MAP["gross_profit"])
        total_assets = self._year_metric_value("balance_sheet", year, BALANCE_SHEET_FIELD_CODE_MAP["total_assets"])
        total_equity = self._year_metric_value("balance_sheet", year, BALANCE_SHEET_FIELD_CODE_MAP["total_equity"])
        total_liabilities = self._year_metric_value("balance_sheet", year, ("ifrs-full_Liabilities",))
        current_assets = self._year_metric_value("balance_sheet", year, BALANCE_SHEET_FIELD_CODE_MAP["current_assets"])
        current_liabilities = self._year_metric_value("balance_sheet", year, BALANCE_SHEET_FIELD_CODE_MAP["current_liabilities"])
        inventory = self._year_metric_value("balance_sheet", year, BALANCE_SHEET_FIELD_CODE_MAP["inventory"])
        accounts_receivable = self._year_metric_value("balance_sheet", year, BALANCE_SHEET_FIELD_CODE_MAP["accounts_receivable"])
        paid_in_capital = self._year_metric_value("balance_sheet", year, RATIO_FIELD_MAP["paid_in_capital"])
        net_fixed_assets = self._year_metric_value("balance_sheet", year, RATIO_FIELD_MAP["net_fixed_assets"])
        prepayments = self._year_metric_value("balance_sheet", year, RATIO_FIELD_MAP["prepayments"])
        cost_of_goods_sold = self._year_metric_value(
            "comprehensive_income_statement",
            year,
            RATIO_FIELD_MAP["cost_of_goods_sold"],
        )
        interest_expense = self._year_metric_value(
            "comprehensive_income_statement",
            year,
            RATIO_FIELD_MAP["interest_expense"],
        )
        cash_from_operations = self._year_metric_value(
            "statement_of_cash_flows",
            year,
            CASH_FLOW_FIELD_MAP["cash_from_operations"],
        )

        average_accounts_receivable = self._average_year_metric_value(
            "balance_sheet",
            year,
            BALANCE_SHEET_FIELD_CODE_MAP["accounts_receivable"],
        )
        average_total_assets = self._average_year_metric_value(
            "balance_sheet",
            year,
            BALANCE_SHEET_FIELD_CODE_MAP["total_assets"],
        )
        previous_total_equity = self._year_metric_value(
            "balance_sheet",
            year - 1,
            BALANCE_SHEET_FIELD_CODE_MAP["total_equity"],
        )
        average_total_equity = safe_average(previous_total_equity, total_equity)
        average_inventory = self._average_year_metric_value(
            "balance_sheet",
            year,
            BALANCE_SHEET_FIELD_CODE_MAP["inventory"],
        )
        average_net_fixed_assets = self._average_year_metric_value(
            "balance_sheet",
            year,
            RATIO_FIELD_MAP["net_fixed_assets"],
        )
        quick_assets = safe_subtract(current_assets, inventory, prepayments)
        non_current_liabilities = self._year_metric_value(
            "balance_sheet",
            year,
            BALANCE_SHEET_FIELD_CODE_MAP["non_current_liabilities"],
        )
        long_term_capital = safe_add(total_equity, non_current_liabilities)
        interest_coverage_numerator = safe_add(pre_tax_profit, interest_expense)
        average_collection_period = safe_divide(average_accounts_receivable, revenue, 365)
        total_asset_turnover = safe_divide(revenue, average_total_assets)
        roe = safe_divide(net_profit, average_total_equity, 100)
        average_days_sales_outstanding = safe_divide(average_accounts_receivable, revenue, 365)
        net_profit_margin = safe_divide(net_profit, revenue, 100)
        debt_to_asset_ratio = safe_divide(total_liabilities, total_assets, 100)
        pre_tax_profit_to_capital_ratio = safe_divide(pre_tax_profit, paid_in_capital, 100)
        long_term_capital_to_fixed_assets_ratio = safe_divide(long_term_capital, net_fixed_assets, 100)
        current_ratio = safe_divide(current_assets, current_liabilities, 100)
        interest_coverage_ratio = safe_divide(interest_coverage_numerator, interest_expense)
        roa = safe_divide(net_profit, average_total_assets, 100)
        cash_reinvestment_ratio = None
        cash_adequacy_ratio = None
        quick_ratio = safe_divide(quick_assets, current_liabilities, 100)
        accounts_receivable_turnover = safe_divide(revenue, average_accounts_receivable)
        fixed_assets_turnover = safe_divide(revenue, average_net_fixed_assets)
        inventory_turnover = safe_divide(cost_of_goods_sold, average_inventory)
        cash_flow_ratio = safe_divide(cash_from_operations, current_liabilities, 100)
        if gross_profit is None:
            gross_profit = safe_subtract(revenue, cost_of_goods_sold)
        gross_margin = safe_divide(gross_profit, revenue, 100)
        roe_calculation_reason = missing_formula_reason(
            value=roe,
            formula="稅後淨利 / 平均權益總額 * 100；平均權益總額 = (前一年權益總額 + 當年度權益總額) / 2",
            required_values={
                "稅後淨利": net_profit,
                f"{year - 1} 年權益總額": previous_total_equity,
                f"{year} 年權益總額": total_equity,
            },
            denominator_values={"平均權益總額": average_total_equity},
        )
        current_ratio_calculation_reason = missing_formula_reason(
            value=current_ratio,
            formula="流動資產 / 流動負債 * 100",
            required_values={"流動資產": current_assets, "流動負債": current_liabilities},
            denominator_values={"流動負債": current_liabilities},
        )
        debt_to_asset_ratio_calculation_reason = missing_formula_reason(
            value=debt_to_asset_ratio,
            formula="負債總額 / 資產總額 * 100",
            required_values={"負債總額": total_liabilities, "資產總額": total_assets},
            denominator_values={"資產總額": total_assets},
        )
        interest_coverage_ratio_calculation_reason = missing_formula_reason(
            value=interest_coverage_ratio,
            formula="(稅前淨利 + 利息費用) / 利息費用",
            required_values={"稅前淨利": pre_tax_profit, "利息費用": interest_expense},
            denominator_values={"利息費用": interest_expense},
        )
        net_profit_margin_calculation_reason = missing_formula_reason(
            value=net_profit_margin,
            formula="稅後淨利 / 營業收入 * 100",
            required_values={"稅後淨利": net_profit, "營業收入": revenue},
            denominator_values={"營業收入": revenue},
        )
        eps_calculation_reason = missing_formula_reason(
            value=eps,
            formula="XBRL 每股盈餘欄位",
            required_values={"每股盈餘": eps},
        )

        return [
            {
                "year": year,
                "gui_no": self.company_code,
                "revenue": revenue,
                "net_profit": net_profit,
                "gross_margin": gross_margin,
                # 平均收現期間 = 平均應收帳款 / 營業收入 * 365。
                "average_collection_period": average_collection_period,
                # 總資產週轉率 = 營業收入 / 平均資產總額。
                "total_asset_turnover": total_asset_turnover,
                # 股東權益報酬率 = 稅後淨利 / 平均權益總額 * 100。
                "roe": roe,
                "roe_calculation_reason": roe_calculation_reason,
                # 應收帳款收現天數 = 平均應收帳款 / 營業收入 * 365。
                "average_days_sales_outstanding": average_days_sales_outstanding,
                # 純益率 = 稅後淨利 / 營業收入 * 100。
                "net_profit_margin": net_profit_margin,
                "net_profit_margin_calculation_reason": net_profit_margin_calculation_reason,
                # 負債佔資產比率 = 負債總額 / 資產總額 * 100。
                "debt_to_asset_ratio": debt_to_asset_ratio,
                "debt_to_asset_ratio_calculation_reason": debt_to_asset_ratio_calculation_reason,
                # 稅前純益佔實收資本比率 = 稅前淨利 / 實收資本額 * 100。
                "pre_tax_profit_to_capital_ratio": pre_tax_profit_to_capital_ratio,
                # 長期資金佔固定資產比率 = (權益總額 + 非流動負債) / 固定資產淨額 * 100。
                "long_term_capital_to_fixed_assets_ratio": long_term_capital_to_fixed_assets_ratio,
                # 流動比率 = 流動資產 / 流動負債 * 100。
                "current_ratio": current_ratio,
                "current_ratio_calculation_reason": current_ratio_calculation_reason,
                # 利息保障倍數 = (稅前淨利 + 利息費用) / 利息費用。
                "interest_coverage_ratio": interest_coverage_ratio,
                "interest_coverage_ratio_calculation_reason": interest_coverage_ratio_calculation_reason,
                # 資產報酬率 = 稅後淨利 / 平均資產總額 * 100。
                "roa": roa,
                # XXX現金再投資比率目前無法組成：缺少可穩定對應的現金股利、固定資產毛額、長期投資與其他資產等組成欄位。
                "cash_reinvestment_ratio": cash_reinvestment_ratio,
                # XXX現金流量允當比率目前無法組成：需要近五年營業活動現金流量、資本支出、存貨增加額與現金股利等期間資料。
                "cash_adequacy_ratio": cash_adequacy_ratio,
                # 速動比率 = (流動資產 - 存貨 - 預付款項) / 流動負債 * 100。
                "quick_ratio": quick_ratio,
                # 應收帳款週轉率 = 營業收入 / 平均應收帳款。
                "accounts_receivable_turnover": accounts_receivable_turnover,
                # 固定資產週轉率 = 營業收入 / 平均固定資產淨額。
                "fixed_assets_turnover": fixed_assets_turnover,
                # 存貨週轉率 = 銷貨成本 / 平均存貨。
                "inventory_turnover": inventory_turnover,
                # 現金流量比率 = 營業活動現金流量 / 流動負債 * 100。
                "cash_flow_ratio": cash_flow_ratio,
                # 每股盈餘直接取 XBRL 中可對應的 EPS 欄位。
                "eps": eps,
                "eps_calculation_reason": eps_calculation_reason,
            }
        ]


def get_financial_statements_db_path() -> Path | None:
    if is_postgresql():
        return None
    configured_path = os.getenv("REPORT_GENERATOR_DB_PATH")
    if configured_path:
        return Path(configured_path).resolve()
    return resolve_sqlite_db_path()


def generate_credit_report_docx(
    *,
    company_code: str,
    company_label: str,
    year: int,
) -> dict[str, Any]:
    db_path = get_financial_statements_db_path()
    report_generator_log(
        "docx.generate.start",
        company_code=company_code,
        year=year,
        database_engine="postgresql" if is_postgresql() else "sqlite",
        database_path=str(db_path) if db_path is not None else "",
    )
    if db_path is not None and not db_path.exists():
        report_generator_log("docx.source_database.missing", path=str(db_path))
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    report_generator_log("docx.adapter.create.start")
    adapter = FinancialStatementsDocxAdapter(
        db_path=db_path,
        company_code=company_code,
        company_label=company_label,
    )
    report_generator_log("docx.adapter.create.done")
    try:
        if not adapter.has_source_data(year):
            report_generator_log(
                "docx.source_data.missing",
                company_code=company_code,
                year=year,
            )
            raise ReportGenerationError(
                f"FinancialStatementXBRL.db 查無公司代號 {company_code} 的 {year} 年財報資料"
            )
        report_generator_log("docx.source_data.found")
        ratio_rows = adapter._query_financial_ratios(
            f"SELECT * FROM financial_ratios WHERE year = {year};"
        )
        financial_trend_rows = adapter._query_financial_trends(year)
        report_generator_log(
            "docx.financial_data.loaded",
            ratio_count=len(ratio_rows),
            trend_count=len(financial_trend_rows),
        )
        report_generator_log("docx.ai_conclusion.start")
        ai_summary_text = generate_report_llm_conclusion(
            ratio_rows[0] if ratio_rows else {}
        )
        report_generator_log(
            "docx.ai_conclusion.done",
            summary_length=len(ai_summary_text),
        )
        report_generator_log("docx.chapters.merge.start")
        report_bytes = merge_all_chapters(
            year,
            company_code,
            ai_summary_text,
            adapter,
        )
        report_generator_log(
            "docx.chapters.merge.done",
            result_type=type(report_bytes).__name__,
            byte_size=len(report_bytes) if isinstance(report_bytes, bytes) else 0,
        )
    finally:
        adapter.close()
        report_generator_log("docx.adapter.closed")

    if isinstance(report_bytes, dict):
        report_generator_log(
            "docx.generate.error",
            error=report_bytes.get("error") or "Backend docx service returned an error",
        )
        raise ReportGenerationError(
            report_bytes.get("error") or "Backend docx service returned an error"
        )

    report_generator_log("docx.generate.done", byte_size=len(report_bytes))
    return {
        "report_bytes": report_bytes,
        "ai_summary_text": ai_summary_text,
        "ratio_row": ratio_rows[0] if ratio_rows else {},
        "financial_trend_rows": financial_trend_rows,
    }


def insert_report_history(
    *,
    title: str,
    company: str,
    company_code: str,
    company_label: str,
    year: int,
    generated_at: datetime,
    generated_by: str,
    file_name: str,
    file_size_bytes: int,
    file_path: str = "",
) -> dict[str, Any]:
    file_size = format_file_size(file_size_bytes)
    generated_at_iso = generated_at.isoformat(timespec="seconds")
    generated_at_display = generated_at.strftime("%Y/%m/%d %H:%M")

    report_generator_log(
        "history.insert.start",
        company_code=company_code,
        year=year,
        file_name=file_name,
        file_path=file_path,
        file_size=file_size,
    )
    with connect_report_history_db() as connection:
        returning_sql = " RETURNING id" if is_postgresql() else ""
        cursor = connection.execute(
            f"""
            INSERT INTO {REPORT_HISTORY_TABLE} (
                public_id,
                title,
                company,
                company_code,
                company_label,
                year,
                period,
                report_type,
                generated_at,
                generated_at_display,
                generated_by,
                status,
                file_size,
                file_name,
                file_path,
                mime_type,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            {returning_sql}
            """,
            (
                generate_report_public_id(),
                title,
                company,
                company_code,
                company_label,
                str(year),
                REPORT_PERIOD,
                REPORT_TYPE,
                generated_at_iso,
                generated_at_display,
                generated_by,
                REPORT_STATUS_DONE,
                file_size,
                file_name,
                file_path,
                DOCX_MIME_TYPE,
                generated_at_iso,
            ),
        )
        returned_row = cursor.fetchone() if is_postgresql() else None
        connection.commit()
        report_id = (
            int(returned_row["id"])
            if is_postgresql()
            else int(cursor.lastrowid)
        )

    report_generator_log("history.insert.done", history_id=report_id)
    return get_report_history_item(report_id) or {}


def row_to_history_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "publicId": row["public_id"],
        "title": row["title"],
        "company": row["company"],
        "year": row["year"],
        "period": row["period"],
        "reportType": row["report_type"],
        "generatedAt": row["generated_at_display"],
        "generatedBy": row["generated_by"],
        "status": row["status"],
        "fileSize": row["file_size"],
        "fileName": row["file_name"],
    }


def upsert_report_dashboard(
    *,
    history_id: int,
    company_name: str,
    year: int,
    generated_at: datetime,
    ai_summary_text: str,
    ratio_row: dict[str, Any],
    financial_trend_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    report_generator_log(
        "dashboard.upsert.start",
        history_id=history_id,
        company_name=company_name,
        year=year,
    )
    now_iso = generated_at.isoformat(timespec="seconds")
    dashboard_payload = {
        "summary_items_json": database_json_dumps(
            normalize_summary_items(ai_summary_text, company_name, year),
            ensure_ascii=False,
        ),
        "progress_items_json": database_json_dumps(
            build_report_progress_items(),
            ensure_ascii=False,
        ),
        "progress_percent": 100,
        "metrics_title": f"關鍵財務指標（{year} Q1-Q4）",
        "metrics_json": database_json_dumps(
            build_dashboard_metrics(ratio_row),
            ensure_ascii=False,
        ),
        "financial_trends_json": database_json_dumps(
            build_dashboard_financial_trends(financial_trend_rows),
            ensure_ascii=False,
        ),
    }

    with connect_report_history_db() as connection:
        connection.execute(
            f"""
            INSERT INTO {REPORT_DASHBOARD_TABLE} (
                history_id,
                summary_items_json,
                progress_items_json,
                progress_percent,
                metrics_title,
                metrics_json,
                financial_trends_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(history_id) DO UPDATE SET
                summary_items_json = excluded.summary_items_json,
                progress_items_json = excluded.progress_items_json,
                progress_percent = excluded.progress_percent,
                metrics_title = excluded.metrics_title,
                metrics_json = excluded.metrics_json,
                financial_trends_json = excluded.financial_trends_json,
                updated_at = excluded.updated_at
            """,
            (
                history_id,
                dashboard_payload["summary_items_json"],
                dashboard_payload["progress_items_json"],
                dashboard_payload["progress_percent"],
                dashboard_payload["metrics_title"],
                dashboard_payload["metrics_json"],
                dashboard_payload["financial_trends_json"],
                now_iso,
                now_iso,
            ),
        )
        connection.commit()

    dashboard_item = get_report_dashboard(history_id) or {}
    report_generator_log(
        "dashboard.upsert.done",
        history_id=history_id,
        dashboard_id=dashboard_item.get("id", ""),
    )
    return dashboard_item


def get_report_dashboard(history_id: int) -> dict[str, Any] | None:
    with connect_report_history_db() as connection:
        row = connection.execute(
            f"SELECT * FROM {REPORT_DASHBOARD_TABLE} WHERE history_id = ?",
            (history_id,),
        ).fetchone()

    return row_to_dashboard_item(row) if row else None


def get_report_history_item(report_id: int) -> dict[str, Any] | None:
    with connect_report_history_db() as connection:
        row = connection.execute(
            f"SELECT * FROM {REPORT_HISTORY_TABLE} WHERE id = ?",
            (report_id,),
        ).fetchone()
    return row_to_history_item(row) if row else None


def build_report_history_search_clause(
    keyword: str,
    status: str,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    trimmed_keyword = keyword.strip()
    if trimmed_keyword:
        like_keyword = f"%{trimmed_keyword}%"
        clauses.append(
            """
            (
                file_name LIKE ?
                OR title LIKE ?
                OR company LIKE ?
                OR year LIKE ?
                OR period LIKE ?
                OR report_type LIKE ?
                OR generated_by LIKE ?
                OR status LIKE ?
            )
            """
        )
        params.extend([like_keyword] * 8)

    trimmed_status = status.strip()
    if trimmed_status:
        clauses.append("status = ?")
        params.append(trimmed_status)

    if not clauses:
        return "", []

    return "WHERE " + " AND ".join(clauses), params


def list_report_history(
    *,
    page: int,
    page_size: int,
    offset: int | None,
    keyword: str,
    status: str,
) -> dict[str, Any]:
    normalized_page_size = max(1, min(page_size, 100))
    normalized_page = max(1, page)
    normalized_offset = max(
        0,
        offset if offset is not None else (normalized_page - 1) * normalized_page_size,
    )
    where_sql, search_params = build_report_history_search_clause(keyword, status)

    with connect_report_history_db() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM {REPORT_HISTORY_TABLE}
            {where_sql}
            """,
            search_params,
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT *
            FROM {REPORT_HISTORY_TABLE}
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*search_params, normalized_page_size, normalized_offset],
        ).fetchall()

    return {
        "reports": [row_to_history_item(row) for row in rows],
        "total": total,
        "page": normalized_page,
        "pageSize": normalized_page_size,
        "offset": normalized_offset,
    }


# TODO: 歷史報告下載功能尚未完成。
# 雲端部署不再依賴 Server 本機檔案，待串接物件儲存後再恢復下載路徑查找。
# def get_report_download_path(public_id: str) -> tuple[Path, str]:
#     with connect_report_history_db() as connection:
#         row = connection.execute(
#             f"SELECT file_name, file_path FROM {REPORT_HISTORY_TABLE} WHERE public_id = ?",
#             (public_id,),
#         ).fetchone()
#
#     if not row:
#         raise FileNotFoundError("歷史報告不存在")
#
#     configured_path = Path(row["file_path"])
#     candidates = [configured_path, generated_reports_dir() / row["file_name"]]
#     for candidate in candidates:
#         if candidate.exists() and candidate.is_file():
#             return candidate, row["file_name"]
#
#     raise FileNotFoundError(f"找不到歷史報告檔案：{row['file_name']}")


def generate_and_store_credit_report(
    *,
    company_code: str,
    company_label: str,
    year: int,
    generated_by: str = "",
) -> tuple[bytes, str, dict[str, Any], dict[str, Any]]:
    report_generator_log(
        "generate_and_store.start",
        company_code=company_code,
        year=year,
    )
    report_result = generate_credit_report_docx(
        company_code=company_code,
        company_label=company_label,
        year=year,
    )
    report_bytes = report_result["report_bytes"]
    generated_at = datetime.now()
    company_name = company_full_name_from_label(company_label, company_code)
    report_generated_by = generated_by.strip() or REPORT_GENERATED_BY
    title = f"{year} 年度徵審報告"
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    file_stem = sanitize_filename(f"{company_name}{year}徵審報告_{timestamp}_{report_generated_by}")
    file_name = f"{file_stem}.docx"

    # TODO: 雲端報告儲存尚未完成。
    # Local 開發原本會把 DOCX 寫入 REPORT_GENERATOR_OUTPUT_DIR；雲端環境沒有固定目錄，
    # 因此先停用實體檔案寫入，只保留本次 API 回傳的 report_bytes。
    # file_path = generated_reports_dir() / file_name
    # file_path.write_bytes(report_bytes)
    report_generator_log(
        "report_file.write.skipped",
        reason="cloud_storage_not_implemented",
        file_name=file_name,
        byte_size=len(report_bytes),
    )

    try:
        history_item = insert_report_history(
            title=title,
            company=f"{company_name}（{company_code}）",
            company_code=company_code,
            company_label=company_label,
            year=year,
            generated_at=generated_at,
            generated_by=report_generated_by,
            file_name=file_name,
            file_size_bytes=len(report_bytes),
            file_path="",
        )
    except Exception as error:
        report_generator_log(
            "history.insert.error",
            file_name=file_name,
            error_type=type(error).__name__,
            error=str(error),
        )
        raise
    try:
        dashboard_item = upsert_report_dashboard(
            history_id=int(history_item["id"]),
            company_name=company_name,
            year=year,
            generated_at=generated_at,
            ai_summary_text=report_result["ai_summary_text"],
            ratio_row=report_result["ratio_row"],
            financial_trend_rows=report_result["financial_trend_rows"],
        )
    except Exception as error:
        report_generator_log(
            "dashboard.upsert.error",
            history_id=history_item.get("id", ""),
            error_type=type(error).__name__,
            error=str(error),
        )
        raise
    report_generator_log(
        "generate_and_store.done",
        history_id=history_item.get("id", ""),
        dashboard_id=dashboard_item.get("id", ""),
        file_name=file_name,
    )
    return report_bytes, file_name, history_item, dashboard_item
