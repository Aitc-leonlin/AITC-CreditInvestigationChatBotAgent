import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.shared.database.db_path import resolve_sqlite_db_path


JSON_TO_COLUMNS = {
    "出表日期": "publication_date",
    "公司代號": "company_code",
    "公司名稱": "company_name",
    "公司簡稱": "company_short_name",
    "外國企業註冊地國": "foreign_registration_country",
    "產業別": "industry_code",
    "住址": "address",
    "營利事業統一編號": "tax_id",
    "董事長": "chairman",
    "總經理": "general_manager",
    "發言人": "spokesperson",
    "發言人職稱": "spokesperson_title",
    "代理發言人": "acting_spokesperson",
    "總機電話": "telephone",
    "成立日期": "incorporation_date",
    "上市日期": "listing_date",
    "普通股每股面額": "par_value",
    "實收資本額": "paid_in_capital",
    "私募股數": "private_placement_shares",
    "特別股": "preferred_shares",
    "編制財務報表類型": "financial_statement_type",
    "股票過戶機構": "stock_transfer_agent",
    "過戶電話": "transfer_agent_phone",
    "過戶地址": "transfer_agent_address",
    "簽證會計師事務所": "cpa_firm",
    "簽證會計師1": "cpa_1",
    "簽證會計師2": "cpa_2",
    "英文簡稱": "english_short_name",
    "英文通訊地址": "english_mailing_address",
    "傳真機號碼": "fax",
    "電子郵件信箱": "email",
    "網址": "website",
    "已發行普通股數或TDR原股發行股數": "issued_common_shares_or_tdr_shares",
}


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_rows(json_path: Path) -> list[dict[str, str]]:
    raw_rows = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_rows, list):
        raise ValueError("JSON root must be a list of company profile objects")

    rows: list[dict[str, str]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        row = {
            column: compact_text(raw_row.get(json_key))
            for json_key, column in JSON_TO_COLUMNS.items()
        }
        row["source_json"] = json.dumps(raw_row, ensure_ascii=False, sort_keys=True)
        rows.append(row)
    return rows


def import_rows(connection: sqlite3.Connection, rows: list[dict[str, str]]) -> int:
    columns = [*JSON_TO_COLUMNS.values(), "source_json"]
    placeholders = ", ".join(f":{column}" for column in columns)
    assignments = ", ".join(
        f"{column} = excluded.{column}"
        for column in columns
        if column != "company_code"
    )
    sql = f"""
        INSERT INTO company_profile ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(company_code) DO UPDATE SET
            {assignments},
            updated_at = CURRENT_TIMESTAMP
    """
    connection.executemany(sql, rows)
    connection.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--db", type=Path, default=resolve_sqlite_db_path())
    args = parser.parse_args()

    rows = load_rows(args.json_path)
    with sqlite3.connect(args.db) as connection:
        count = import_rows(connection, rows)
    print(f"Imported {count} listed company profiles into {args.db}")


if __name__ == "__main__":
    main()
