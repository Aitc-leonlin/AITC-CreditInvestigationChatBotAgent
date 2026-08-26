from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConversationMessageCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    role: str = Field(min_length=1, max_length=40)
    content: Any = ""


class ExpertKnowledgeReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    anchorDescription: str = ""
    systemPrompt: str = ""
    createdAt: str = ""
    updatedAt: str = ""


class ExternalDataReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = ""
    response: str = ""


class ConversationUpsertCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="新對話", max_length=200)
    createdAt: str | None = None
    updatedAt: str | None = None
    messages: list[ConversationMessageCommand] = Field(default_factory=list)
    dataSourcesForMessages: dict[str, list[Any]] = Field(default_factory=dict)
    expertKnowledgeForMessages: dict[str, list[ExpertKnowledgeReference]] = Field(
        default_factory=dict
    )
    externalDataForMessages: dict[str, list[ExternalDataReference]] = Field(
        default_factory=dict
    )


class ConversationMessageResponse(BaseModel):
    id: str
    role: str
    content: Any


class ConversationResponse(BaseModel):
    id: str
    title: str
    createdAt: str
    updatedAt: str
    messages: list[ConversationMessageResponse]
    dataSourcesForMessages: dict[str, list[Any]]
    expertKnowledgeForMessages: dict[str, list[ExpertKnowledgeReference]]
    externalDataForMessages: dict[str, list[ExternalDataReference]]
