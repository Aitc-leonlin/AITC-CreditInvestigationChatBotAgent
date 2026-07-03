from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.services.expert_knowledge_service import (
    create_expert_knowledge_entry,
    delete_expert_knowledge_entry,
    get_expert_knowledge_entry,
    list_applied_expert_knowledge_entries,
    list_expert_knowledge_entries,
    update_expert_knowledge_entry,
)


expert_knowledge_entries_router = APIRouter(tags=["expert-knowledge"])


class ExpertKnowledgeEntryPayload(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1)
    dataSource: str = Field(min_length=1)
    industry: str = Field(min_length=1)
    companyLabel: str = Field(min_length=1)
    companyPromptValue: str = ""
    sourceSchemaKey: str = ""
    anchorDescription: str = Field(min_length=1)
    systemPrompt: str = Field(min_length=1)


class ExpertKnowledgeEntryResponse(BaseModel):
    id: str
    title: str
    dataSource: str
    industry: str
    companyLabel: str
    companyPromptValue: str
    sourceSchemaKey: str
    anchorDescription: str
    systemPrompt: str
    createdAt: str
    updatedAt: str


class ExpertKnowledgeListResponse(BaseModel):
    entries: list[ExpertKnowledgeEntryResponse]
    total: int
    page: int
    pageSize: int
    offset: int


@expert_knowledge_entries_router.get(
    "/api/expert-knowledge",
    response_model=ExpertKnowledgeListResponse,
)
async def list_expert_knowledge(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=100),
    offset: int | None = Query(default=None, ge=0),
    keyword: str = Query(default=""),
):
    return list_expert_knowledge_entries(
        page=page,
        page_size=pageSize,
        offset=offset,
        keyword=keyword,
    )


@expert_knowledge_entries_router.get(
    "/api/expert-knowledge/applied",
    response_model=list[ExpertKnowledgeEntryResponse],
)
async def list_applied_expert_knowledge(
    companyLabel: str = Query(default=""),
    companyPromptValue: str = Query(default=""),
    industry: str = Query(default=""),
    dataSource: str = Query(default=""),
):
    return list_applied_expert_knowledge_entries(
        company_label=companyLabel,
        company_prompt_value=companyPromptValue,
        industry=industry,
        data_source=dataSource,
    )


@expert_knowledge_entries_router.get(
    "/api/expert-knowledge/{entry_id}",
    response_model=ExpertKnowledgeEntryResponse,
)
async def get_expert_knowledge(entry_id: str):
    entry = get_expert_knowledge_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Expert knowledge entry not found.")
    return entry


@expert_knowledge_entries_router.post(
    "/api/expert-knowledge",
    response_model=ExpertKnowledgeEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_expert_knowledge(payload: ExpertKnowledgeEntryPayload):
    try:
        return create_expert_knowledge_entry(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@expert_knowledge_entries_router.put(
    "/api/expert-knowledge/{entry_id}",
    response_model=ExpertKnowledgeEntryResponse,
)
async def update_expert_knowledge(entry_id: str, payload: ExpertKnowledgeEntryPayload):
    try:
        entry = update_expert_knowledge_entry(entry_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="Expert knowledge entry not found.")
    return entry


@expert_knowledge_entries_router.patch(
    "/api/expert-knowledge/{entry_id}",
    response_model=ExpertKnowledgeEntryResponse,
)
async def patch_expert_knowledge(entry_id: str, payload: ExpertKnowledgeEntryPayload):
    return await update_expert_knowledge(entry_id, payload)


@expert_knowledge_entries_router.delete(
    "/api/expert-knowledge/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_expert_knowledge(entry_id: str) -> None:
    deleted = delete_expert_knowledge_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Expert knowledge entry not found.")
