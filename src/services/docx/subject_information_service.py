from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from src.services.docx._python_docx_common import (
    add_heading,
    add_key_value_table,
    add_spacer,
    add_text,
    execute_query,
    format_value,
)
from src.services.docx.table_mapping import SUBJECT_MAP, label


def establish_subject_info(gui_no: str, db: Any, document: Any = None) -> Any:
    document = document or Document()
    sql = f"SELECT full_name_zhtw FROM company_profile WHERE gui_no = {gui_no};"
    rows = execute_query(db, sql)
    subject = rows[0] if rows else {}
    company_name = format_value(subject.get("full_name_zhtw"))

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(title, f"{company_name}授信報告" if company_name else "授信報告", size=24)

    add_heading(document, "項目資訊", size=18)
    mapped_rows = [
        (label(SUBJECT_MAP, key), value)
        for key, value in subject.items()
    ]
    mapped_rows.append(("生成項目", "基本資料、資產負債分析、財務比率分析"))
    add_key_value_table(document, mapped_rows, header=("項目", "資訊"))
    add_spacer(document, 2)
    return document
