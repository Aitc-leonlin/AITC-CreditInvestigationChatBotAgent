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
from src.features.report_generator.services.docx.table_mapping import (
    COMPANY_EN_PROFILE_MAP,
    COMPANY_PROFILE_MAP,
    label,
)


PROFILE_COLUMNS = (
    "stock_code,full_name_zhtw,short_name_zhtw,gui_no,address_zhtw,phone,fax,"
    "website,email,industry_main,ceo,capital,"
    "founded_date,accountant_firm,accountants,"
    "listed_market,par_value,"
    "ipo_date"
)


def establish_company_profile(gui_no: str, db: Any, document: Any = None) -> Any:
    document = document or Document()
    profile_rows = execute_query(
        db,
        f"SELECT {PROFILE_COLUMNS} FROM company_profile WHERE gui_no = {gui_no};",
    )
    en_rows = execute_query(
        db,
        "SELECT short_name_enus,address_enus "
        f"FROM company_profile WHERE gui_no = {gui_no};",
    )
    other_rows = execute_query(
        db,
        "SELECT management_team,registration_change_record,investment_projects "
        f"FROM company_profile WHERE gui_no = {gui_no};",
    )

    profile = profile_rows[0] if profile_rows else {}
    en_profile = en_rows[0] if en_rows else {}
    other_profile = other_rows[0] if other_rows else {}

    add_heading(document, "公司基本資料", size=18)
    add_heading(document, "基本資料表", size=12)
    add_key_value_table(
        document,
        [(label(COMPANY_PROFILE_MAP, key), format_value(value)) for key, value in profile.items()],
        header=("項目", "中文資訊"),
    )
    add_spacer(document, 2)
    add_key_value_table(
        document,
        [(label(COMPANY_EN_PROFILE_MAP, key), value) for key, value in en_profile.items()],
        header=("項目", "英文資訊"),
    )
    add_spacer(document, 2)

    for title, key in (
        ("經營團隊", "management_team"),
        ("公司變更", "registration_change_record"),
        ("投資項目", "investment_projects"),
    ):
        paragraph = document.add_paragraph()
        add_text(paragraph, title, size=13, bold=True)
        content = document.add_paragraph()
        add_text(content, other_profile.get(key), size=12)
        add_spacer(document, 1)

    return document
