import math
import os
import re
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.services.db_path import PROJECT_ROOT, resolve_sqlite_db_path
from src.services.docx.document_merge_service import merge_all_chapters


BALANCE_SHEET_FIELD_CODE_MAP = {
    "retained_earnings": "3300",
    "other_accounts_receivable": "1210",
    "other_current_assets": "1470",
    "inventory": "130X",
    "accounts_receivable": "1170",
    "total_equity": "3XXX",
    "current_liabilities": "21XX",
    "current_assets": "11XX",
    "cash": "1100",
    "capital_stock": "3100",
    "total_liabilities_and_equity": "1XXX",
    "capital_reserve": "3200",
    "total_assets": "1XXX",
    "non_current_liabilities": "25XX",
    "non_current_assets": "15XX",
}

REPORT_HISTORY_TABLE = "report_generator_history"
REPORT_GENERATOR_OUTPUT_DIR_ENV = "REPORT_GENERATOR_OUTPUT_DIR"
LEGACY_REPORT_GENERATOR_FILE_DIR_ENV = "REPORT_GENERATOR_FILE_DIR"
REPORT_GENERATED_BY = "張小明"
REPORT_PERIOD = "Q1 ~ Q4"
REPORT_TYPE = "標準徵審報告"
REPORT_STATUS_DONE = "已完成"
DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ReportGenerationError(RuntimeError):
    pass


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


def safe_divide(numerator: Any, denominator: Any, multiplier: float = 1.0) -> float | None:
    left = first_number(numerator)
    right = first_number(denominator)
    if left is None or right in (None, 0):
        return None
    return round((left / right) * multiplier, 4)


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


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
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def report_history_db_path() -> Path:
    return resolve_sqlite_db_path()


def connect_report_history_db() -> sqlite3.Connection:
    db_path = report_history_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    ensure_report_history_table(connection)
    return connection


def ensure_report_history_table(connection: sqlite3.Connection) -> None:
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
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({REPORT_HISTORY_TABLE})").fetchall()
    }
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
    connection.commit()


class FinancialStatementsDocxAdapter:
    def __init__(self, db_path: Path, company_code: str, company_label: str):
        self.db_path = db_path
        self.company_code = company_code
        self.company_label = company_label
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

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
        row = self.connection.execute(
            """
            SELECT company
            FROM balance_sheet
            WHERE company_code = ?
            ORDER BY year DESC, quarter DESC
            LIMIT 1
            """,
            (self.company_code,),
        ).fetchone()
        return str(row["company"]) if row and row["company"] else self.company_label

    def _query_company_profile(self, sql: str) -> list[dict[str, Any]]:
        selected_columns = self._extract_selected_columns(sql)
        company_name = self._company_name()
        short_name = (
            self.company_label.split("/")[-1].strip()
            if "/" in self.company_label
            else company_name
        )
        profile = {
            "stock_code": self.company_code,
            "full_name_zhtw": company_name,
            "short_name_zhtw": short_name,
            "gui_no": self.company_code,
            "address_zhtw": "",
            "phone": "",
            "fax": "",
            "website": "",
            "email": "",
            "industry_main": "",
            "industry_sub": "",
            "industry_national": "",
            "ceo": "",
            "capital": "",
            "employee_count": "",
            "founded_date": "",
            "business_scope": "",
            "accountant_firm": "",
            "accountants": "",
            "board_shareholding_ratio": "",
            "board_pledge_ratio": "",
            "listed_market": "",
            "par_value": "",
            "ipo_date": "",
            "avg_60d_price": "",
            "avg_60d_volume": "",
            "full_name_enus": "",
            "short_name_enus": "",
            "address_enus": "",
            "management_team": "",
            "registration_change_record": "",
            "investment_projects": "",
        }
        return [{column: profile.get(column, "") for column in selected_columns}]

    def _metric_value(self, table: str, year: int, quarter: int, code: str) -> float | None:
        row = self.connection.execute(
            f"""
            SELECT value
            FROM {table}
            WHERE company_code = ? AND year = ? AND quarter = ? AND account_title_code = ?
            LIMIT 1
            """,
            (self.company_code, year, quarter, code),
        ).fetchone()
        return first_number(row["value"]) if row else None

    def _year_metric_value(self, table: str, year: int, code: str) -> float | None:
        row = self.connection.execute(
            f"""
            SELECT value
            FROM {table}
            WHERE company_code = ? AND year = ? AND account_title_code = ?
            ORDER BY quarter DESC
            LIMIT 1
            """,
            (self.company_code, year, code),
        ).fetchone()
        return first_number(row["value"]) if row else None

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

    def _query_financial_ratios(self, sql: str) -> list[dict[str, Any]]:
        year = self._extract_year(sql)
        if year is None:
            return []

        revenue = self._year_metric_value("comprehensive_income_statement", year, "4000")
        gross_profit = self._year_metric_value("comprehensive_income_statement", year, "5900")
        operating_profit = self._year_metric_value("comprehensive_income_statement", year, "6900")
        pre_tax_profit = self._year_metric_value("comprehensive_income_statement", year, "7900")
        net_profit = self._year_metric_value("comprehensive_income_statement", year, "8200")
        eps = self._year_metric_value("comprehensive_income_statement", year, "9750")
        total_assets = self._year_metric_value("balance_sheet", year, "1XXX")
        total_equity = self._year_metric_value("balance_sheet", year, "3XXX")
        total_liabilities = self._year_metric_value("balance_sheet", year, "2XXX")
        current_assets = self._year_metric_value("balance_sheet", year, "11XX")
        current_liabilities = self._year_metric_value("balance_sheet", year, "21XX")
        inventory = self._year_metric_value("balance_sheet", year, "130X")
        accounts_receivable = self._year_metric_value("balance_sheet", year, "1170")
        cash_from_operations = self._year_metric_value("statement_of_cash_flows", year, "AAAA")

        quick_assets = None
        if first_number(current_assets) is not None:
            quick_assets = current_assets - (inventory or 0)

        return [
            {
                "year": year,
                "gui_no": self.company_code,
                "average_collection_period": safe_divide(accounts_receivable, revenue, 365),
                "total_asset_turnover": safe_divide(revenue, total_assets),
                "roe": safe_divide(net_profit, total_equity, 100),
                "average_days_sales_outstanding": safe_divide(accounts_receivable, revenue, 365),
                "net_profit_margin": safe_divide(net_profit, revenue, 100),
                "debt_to_asset_ratio": safe_divide(total_liabilities, total_assets, 100),
                "pre_tax_profit_to_capital_ratio": safe_divide(pre_tax_profit, total_equity, 100),
                "long_term_capital_to_fixed_assets_ratio": None,
                "current_ratio": safe_divide(current_assets, current_liabilities, 100),
                "interest_coverage_ratio": None,
                "roa": safe_divide(net_profit, total_assets, 100),
                "cash_reinvestment_ratio": safe_divide(cash_from_operations, total_assets, 100),
                "cash_adequacy_ratio": None,
                "quick_ratio": safe_divide(quick_assets, current_liabilities, 100),
                "accounts_receivable_turnover": safe_divide(revenue, accounts_receivable),
                "fixed_assets_turnover": None,
                "inventory_turnover": safe_divide(gross_profit or operating_profit, inventory),
                "cash_flow_ratio": safe_divide(cash_from_operations, current_liabilities, 100),
                "eps": eps,
            }
        ]


def get_financial_statements_db_path() -> Path:
    configured_path = os.getenv("REPORT_GENERATOR_DB_PATH")
    if configured_path:
        return Path(configured_path).resolve()
    return PROJECT_ROOT / "FinancialStatements.db"


def generate_credit_report_docx(
    *,
    company_code: str,
    company_label: str,
    year: int,
) -> bytes:
    db_path = get_financial_statements_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    adapter = FinancialStatementsDocxAdapter(
        db_path=db_path,
        company_code=company_code,
        company_label=company_label,
    )
    try:
        ai_summary_text = (
            "本報告由後端 docx service 依據資料庫財務資料產生。"
            "財務比率目前依既有財報科目試算，部分需額外資料之指標可能留白。"
        )
        report_bytes = merge_all_chapters(
            year,
            company_code,
            ai_summary_text,
            adapter,
        )
    finally:
        adapter.close()

    if isinstance(report_bytes, dict):
        raise ReportGenerationError(
            report_bytes.get("error") or "Backend docx service returned an error"
        )

    return report_bytes


def insert_report_history(
    *,
    title: str,
    company: str,
    company_code: str,
    company_label: str,
    year: int,
    generated_at: datetime,
    file_path: Path,
) -> dict[str, Any]:
    file_size = format_file_size(file_path.stat().st_size)
    generated_at_iso = generated_at.isoformat(timespec="seconds")
    generated_at_display = generated_at.strftime("%Y/%m/%d %H:%M")

    with connect_report_history_db() as connection:
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
                REPORT_GENERATED_BY,
                REPORT_STATUS_DONE,
                file_size,
                file_path.name,
                str(file_path),
                DOCX_MIME_TYPE,
                generated_at_iso,
            ),
        )
        connection.commit()
        report_id = int(cursor.lastrowid)

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


def get_report_history_item(report_id: int) -> dict[str, Any] | None:
    with connect_report_history_db() as connection:
        row = connection.execute(
            f"SELECT * FROM {REPORT_HISTORY_TABLE} WHERE id = ?",
            (report_id,),
        ).fetchone()
    return row_to_history_item(row) if row else None


def list_report_history() -> list[dict[str, Any]]:
    with connect_report_history_db() as connection:
        rows = connection.execute(
            f"SELECT * FROM {REPORT_HISTORY_TABLE} ORDER BY id DESC",
        ).fetchall()
    return [row_to_history_item(row) for row in rows]


def get_report_download_path(public_id: str) -> tuple[Path, str]:
    with connect_report_history_db() as connection:
        row = connection.execute(
            f"SELECT file_name, file_path FROM {REPORT_HISTORY_TABLE} WHERE public_id = ?",
            (public_id,),
        ).fetchone()

    if not row:
        raise FileNotFoundError("歷史報告不存在")

    configured_path = Path(row["file_path"])
    candidates = [configured_path, generated_reports_dir() / row["file_name"]]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate, row["file_name"]

    raise FileNotFoundError(f"找不到歷史報告檔案：{row['file_name']}")


def generate_and_store_credit_report(
    *,
    company_code: str,
    company_label: str,
    year: int,
) -> tuple[bytes, str, dict[str, Any]]:
    report_bytes = generate_credit_report_docx(
        company_code=company_code,
        company_label=company_label,
        year=year,
    )
    generated_at = datetime.now()
    company_name = company_full_name_from_label(company_label, company_code)
    title = f"{year} 年度徵審報告"
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    file_stem = sanitize_filename(f"{company_name}{year}徵審報告_{timestamp}_{REPORT_GENERATED_BY}")
    file_name = f"{file_stem}.docx"
    file_path = generated_reports_dir() / file_name
    file_path.write_bytes(report_bytes)

    history_item = insert_report_history(
        title=title,
        company=f"{company_name}（{company_code}）",
        company_code=company_code,
        company_label=company_label,
        year=year,
        generated_at=generated_at,
        file_path=file_path,
    )
    return report_bytes, file_name, history_item
