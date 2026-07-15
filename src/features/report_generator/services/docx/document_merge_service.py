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
        document = Document()
        establish_subject_info(gui_no, db, document)
        establish_company_profile(gui_no, db, document)
        establish_balance_sheet(year, gui_no, db, document)
        establish_financial_ratios(year, gui_no, ai_summary_text, db, document)
        establish_repayment_ability_analysis(year, gui_no, db, document)
        establish_industry_environment_analysis(gui_no, db, document)
        return document_to_bytes(document)
    except Exception as error:
        return {
            "status": "error",
            "error": str(error),
        }
