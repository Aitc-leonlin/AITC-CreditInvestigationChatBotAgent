import traceback
from typing import Any

from docx import Document

from src.features.report_generator.services.docx._python_docx_common import document_to_bytes
from src.features.report_generator.services.docx.balance_sheet_analysis_service import establish_balance_sheet
from src.features.report_generator.services.docx.company_profile_service import establish_company_profile
from src.features.report_generator.services.docx.financial_ratio_analysis_service import establish_financial_ratios
from src.features.report_generator.services.docx.industry_environment_analysis_service import (
    establish_industry_environment_analysis,
)
from src.features.report_generator.services.docx.repayment_ability_analysis_service import (
    establish_repayment_ability_analysis,
)
from src.features.report_generator.services.docx.subject_information_service import establish_subject_info


def merge_all_chapters(year: int, gui_no: str, ai_summary_text: str, db: Any) -> bytes | dict[str, str]:
    try:
        print("[report-generator] docx.document.create.start", flush=True)
        document = Document()
        print("[report-generator] docx.document.create.done", flush=True)
        print("[report-generator] docx.chapter.subject_info.start", flush=True)
        establish_subject_info(gui_no, db, document)
        print("[report-generator] docx.chapter.subject_info.done", flush=True)
        print("[report-generator] docx.chapter.company_profile.start", flush=True)
        establish_company_profile(gui_no, db, document)
        print("[report-generator] docx.chapter.company_profile.done", flush=True)
        print("[report-generator] docx.chapter.balance_sheet.start", flush=True)
        establish_balance_sheet(year, gui_no, db, document)
        print("[report-generator] docx.chapter.balance_sheet.done", flush=True)
        print("[report-generator] docx.chapter.financial_ratios.start", flush=True)
        establish_financial_ratios(year, gui_no, ai_summary_text, db, document)
        print("[report-generator] docx.chapter.financial_ratios.done", flush=True)
        print("[report-generator] docx.chapter.repayment_ability.start", flush=True)
        establish_repayment_ability_analysis(year, gui_no, db, document)
        print("[report-generator] docx.chapter.repayment_ability.done", flush=True)
        print("[report-generator] docx.chapter.industry_environment.start", flush=True)
        establish_industry_environment_analysis(gui_no, db, document)
        print("[report-generator] docx.chapter.industry_environment.done", flush=True)
        print("[report-generator] docx.serialize.start", flush=True)
        report_bytes = document_to_bytes(document)
        print(
            f"[report-generator] docx.serialize.done byte_size={len(report_bytes)}",
            flush=True,
        )
        return report_bytes
    except Exception as error:
        print(
            "[report-generator] docx.merge.error "
            f"error_type={type(error).__name__!r} error={str(error)!r}",
            flush=True,
        )
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(error),
        }
