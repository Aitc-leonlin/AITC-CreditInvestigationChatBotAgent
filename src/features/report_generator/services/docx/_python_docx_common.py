import ast
import json
from io import BytesIO
from typing import Any, Iterable

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.6f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def normalize_rows(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, tuple):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
            except (ValueError, SyntaxError, json.JSONDecodeError):
                continue
            return normalize_rows(parsed)
    return []


def execute_query(db: Any, sql: str) -> list[dict[str, Any]]:
    if hasattr(db, "_execute"):
        return normalize_rows(db._execute(sql))
    if hasattr(db, "run"):
        return normalize_rows(db.run(sql))
    if hasattr(db, "execute"):
        cursor = db.execute(sql)
        rows = cursor.fetchall()
        keys = [column[0] for column in cursor.description or []]
        return [dict(zip(keys, row)) for row in rows]
    if hasattr(db, "connection") and hasattr(db.connection, "execute"):
        cursor = db.connection.execute(sql)
        rows = cursor.fetchall()
        keys = [column[0] for column in cursor.description or []]
        return [dict(zip(keys, row)) for row in rows]
    raise TypeError("db must expose _execute(), run(), execute(), or connection.execute().")


def add_text(paragraph, text: Any, *, size: int = 12, bold: bool = False):
    run = paragraph.add_run(format_value(text))
    run.font.size = Pt(size)
    run.bold = bold
    return run


def add_heading(document: Document, text: str, *, size: int = 18, bold: bool = False):
    paragraph = document.add_paragraph()
    add_text(paragraph, text, size=size, bold=bold)
    return paragraph


def add_spacer(document: Document, lines: int = 1):
    paragraph = document.add_paragraph()
    for index in range(lines):
        if index:
            paragraph.add_run().add_break()
        else:
            paragraph.add_run().add_break()
    return paragraph


def set_cell_border(cell):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        tag = f"w:{edge}"
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "14")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")


def set_cell_width(cell, width_twips: int):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.first_child_found_in("w:tcW")
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(width_twips))
    tc_w.set(qn("w:type"), "dxa")


def set_table_width(table, width_twips: int = 8000):
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(width_twips))
    tbl_w.set(qn("w:type"), "dxa")


def fill_cell(cell, text: Any, *, width: int, size: int = 12, align: str = "left"):
    set_cell_width(cell, width)
    set_cell_border(cell)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    paragraph = cell.paragraphs[0]
    if align == "right":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif align == "center":
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(paragraph, text, size=size)


def add_key_value_table(
    document: Document,
    rows: Iterable[tuple[str, Any]],
    *,
    header: tuple[str, str] = ("項目", "資訊"),
    widths: tuple[int, int] = (2000, 7000),
):
    table = document.add_table(rows=1, cols=2)
    table.autofit = False
    set_table_width(table)
    fill_cell(table.rows[0].cells[0], header[0], width=widths[0], size=13)
    fill_cell(table.rows[0].cells[1], header[1], width=widths[1], size=13)
    for title, content in rows:
        cells = table.add_row().cells
        fill_cell(cells[0], title, width=widths[0], size=12)
        fill_cell(cells[1], content, width=widths[1], size=12)
    return table


def add_metric_table(
    document: Document,
    rows: Iterable[tuple[str, Any]],
    *,
    value_header: str = "數值",
):
    table = document.add_table(rows=1, cols=2)
    table.autofit = False
    set_table_width(table)
    fill_cell(table.rows[0].cells[0], "會計科目", width=5400, size=13)
    fill_cell(table.rows[0].cells[1], value_header, width=3600, size=13, align="right")
    for title, content in rows:
        cells = table.add_row().cells
        fill_cell(cells[0], title, width=5400, size=12)
        fill_cell(cells[1], content, width=3600, size=12, align="right")
    return table


def document_to_bytes(document: Document) -> bytes:
    output = BytesIO()
    document.save(output)
    return output.getvalue()
