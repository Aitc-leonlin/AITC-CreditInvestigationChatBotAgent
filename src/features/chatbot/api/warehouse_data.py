from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.features.membership.core.auth_middleware import require_permission
from src.features.chatbot.services.warehouse_data_service import (
    create_warehouse_data_entry,
    delete_warehouse_data_entry,
    get_warehouse_data_entry,
    list_applied_warehouse_data_entries,
    list_warehouse_data_entries,
    update_warehouse_data_entry,
)


warehouse_data_router = APIRouter(tags=["warehouse-data"])


class WarehouseDataEntryPayload(BaseModel):
    id: str | None = None
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    companyLabel: str = Field(min_length=1)
    companyPromptValue: str = ""
    summary: str = Field(min_length=1)
    source: str = Field(min_length=1)
    url: str = ""


class WarehouseDataEntryResponse(BaseModel):
    id: str
    category: str
    title: str
    industry: str
    companyLabel: str
    companyPromptValue: str
    summary: str
    source: str
    url: str
    recordUpdatedAt: str
    createdAt: str
    updatedAt: str


class WarehouseDataListResponse(BaseModel):
    entries: list[WarehouseDataEntryResponse]
    total: int
    page: int
    pageSize: int
    offset: int


@warehouse_data_router.get(
    "/api/warehouse-data",
    response_model=WarehouseDataListResponse,
    dependencies=[Depends(require_permission("credit-ai.warehouse-data.view"))],
)
async def list_warehouse_data(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
    offset: int | None = Query(default=None, ge=0),
    keyword: str = Query(default=""),
    category: str = Query(default=""),
):
    return list_warehouse_data_entries(
        page=page,
        page_size=pageSize,
        offset=offset,
        keyword=keyword,
        category=category,
    )


@warehouse_data_router.get(
    "/api/warehouse-data/applied",
    response_model=list[WarehouseDataEntryResponse],
    dependencies=[Depends(require_permission("credit-ai.chat"))],
)
async def list_applied_warehouse_data(
    companyLabel: str = Query(default=""),
    companyPromptValue: str = Query(default=""),
    industry: str = Query(default=""),
    category: str = Query(default=""),
):
    return list_applied_warehouse_data_entries(
        company_label=companyLabel,
        company_prompt_value=companyPromptValue,
        industry=industry,
        category=category,
    )


@warehouse_data_router.get(
    "/api/warehouse-data/{entry_id}",
    response_model=WarehouseDataEntryResponse,
    dependencies=[Depends(require_permission("credit-ai.warehouse-data.view"))],
)
async def get_warehouse_data(entry_id: str):
    entry = get_warehouse_data_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Warehouse data entry not found.")
    return entry


@warehouse_data_router.post(
    "/api/warehouse-data",
    response_model=WarehouseDataEntryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("credit-ai.warehouse-data.add"))],
)
async def create_warehouse_data(payload: WarehouseDataEntryPayload):
    try:
        return create_warehouse_data_entry(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@warehouse_data_router.put(
    "/api/warehouse-data/{entry_id}",
    response_model=WarehouseDataEntryResponse,
    dependencies=[Depends(require_permission("credit-ai.warehouse-data.edit"))],
)
async def update_warehouse_data(entry_id: str, payload: WarehouseDataEntryPayload):
    try:
        entry = update_warehouse_data_entry(entry_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="Warehouse data entry not found.")
    return entry


@warehouse_data_router.patch(
    "/api/warehouse-data/{entry_id}",
    response_model=WarehouseDataEntryResponse,
    dependencies=[Depends(require_permission("credit-ai.warehouse-data.edit"))],
)
async def patch_warehouse_data(entry_id: str, payload: WarehouseDataEntryPayload):
    return await update_warehouse_data(entry_id, payload)


@warehouse_data_router.delete(
    "/api/warehouse-data/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("credit-ai.warehouse-data.delete"))],
)
async def delete_warehouse_data(entry_id: str) -> None:
    deleted = delete_warehouse_data_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Warehouse data entry not found.")
