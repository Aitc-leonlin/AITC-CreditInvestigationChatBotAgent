from time import perf_counter
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.features.membership.core.auth_middleware import require_any_permission, require_permission
from src.features.report_generator.services.report_generator_service import (
    DOCX_MIME_TYPE,
    ReportGenerationError,
    generate_and_store_credit_report,
    get_report_dashboard,
    get_report_download_path,
    list_report_history,
)


report_generator_router = APIRouter(
    tags=["report-generator"],
)


class ReportGeneratorRequest(BaseModel):
    companyCode: str = Field(min_length=1)
    companyLabel: str = ""
    year: int


def content_disposition(filename: str) -> str:
    encoded_filename = quote(filename)
    return f"attachment; filename=\"credit_report.docx\"; filename*=UTF-8''{encoded_filename}"


@report_generator_router.post(
    "/api/report-generator/generate",
    dependencies=[Depends(require_permission("report-generator.create"))],
)
async def generate_report(request: ReportGeneratorRequest):
    started_at = perf_counter()
    try:
        report_bytes, filename, history_item, dashboard_item = generate_and_store_credit_report(
            company_code=request.companyCode.strip(),
            company_label=request.companyLabel.strip(),
            year=request.year,
        )
    except ReportGenerationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
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
            "X-Report-Dashboard-Id": str(dashboard_item.get("id", "")),
            "X-Report-Dashboard-Path": f"/api/report-generator/history/{history_item.get('id', '')}/dashboard",
        },
    )


@report_generator_router.get(
    "/api/report-generator/history",
    dependencies=[Depends(require_permission("report-generator.history"))],
)
async def get_report_history(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
    offset: int | None = Query(default=None, ge=0),
    keyword: str = Query(default=""),
    status: str = Query(default=""),
):
    return list_report_history(
        page=page,
        page_size=pageSize,
        offset=offset,
        keyword=keyword,
        status=status,
    )


@report_generator_router.get(
    "/api/report-generator/history/{history_id}/dashboard",
    dependencies=[
        Depends(
            require_any_permission(
                ["report-generator.create", "report-generator.history"]
            )
        )
    ],
)
async def get_report_dashboard_item(history_id: int):
    dashboard = get_report_dashboard(history_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="歷史報告儀表板資料不存在")
    return {"dashboard": dashboard}


@report_generator_router.get(
    "/api/report-generator/history/{public_id}/download",
    dependencies=[Depends(require_permission("report-generator.history"))],
)
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
