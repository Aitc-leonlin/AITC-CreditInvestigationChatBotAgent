from time import perf_counter
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.services.report_generator_service import (
    DOCX_MIME_TYPE,
    generate_and_store_credit_report,
    get_report_download_path,
    list_report_history,
)


report_generator_router = APIRouter(tags=["report-generator"])


class ReportGeneratorRequest(BaseModel):
    companyCode: str = Field(min_length=1)
    companyLabel: str = ""
    year: int


def content_disposition(filename: str) -> str:
    encoded_filename = quote(filename)
    return f"attachment; filename=\"credit_report.docx\"; filename*=UTF-8''{encoded_filename}"


@report_generator_router.post("/api/report-generator/generate")
async def generate_report(request: ReportGeneratorRequest):
    started_at = perf_counter()
    try:
        report_bytes, filename, history_item = generate_and_store_credit_report(
            company_code=request.companyCode.strip(),
            company_label=request.companyLabel.strip(),
            year=request.year,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    print(
        f"[timing] report_generator.generate.total took "
        f"{perf_counter() - started_at:.3f}s"
    )
    return Response(
        content=report_bytes,
        media_type=DOCX_MIME_TYPE,
        headers={
            "Content-Disposition": content_disposition(filename),
            "X-Report-History-Id": str(history_item.get("id", "")),
        },
    )


@report_generator_router.get("/api/report-generator/history")
async def get_report_history():
    return {"reports": list_report_history()}


@report_generator_router.get("/api/report-generator/history/{public_id}/download")
async def download_report(public_id: str):
    try:
        file_path, filename = get_report_download_path(public_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return FileResponse(
        path=file_path,
        media_type=DOCX_MIME_TYPE,
        headers={"Content-Disposition": content_disposition(filename)},
    )
