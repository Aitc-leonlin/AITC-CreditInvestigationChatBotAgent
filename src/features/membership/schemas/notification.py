from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


NotificationStatus = Literal["PENDING", "SENT", "FAILED"]


class NotificationTemplateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=2, max_length=120)
    channel: str = "EMAIL"
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=1)
    status: str = "ACTIVE"


class NotificationDispatchCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    status: NotificationStatus = "SENT"
    errorMessage: str = ""


class NotificationTemplateResponse(BaseModel):
    id: str
    code: str
    channel: str
    subject: str
    body: str
    status: str
    createdAt: str
    updatedAt: str


class NotificationOutboxResponse(BaseModel):
    id: str
    templateCode: str
    recipientUserId: str | None
    recipientEmail: str | None
    recipientDisplayName: str | None
    channel: str
    payload: dict
    status: str
    scheduledAt: str | None
    sentAt: str | None
    errorMessage: str
    createdAt: str
    updatedAt: str


class AuditLogResponse(BaseModel):
    id: str
    actorUserId: str | None
    actorDisplayName: str | None
    actorEmail: str | None
    action: str
    resourceType: str
    resourceId: str
    outcome: str
    ipAddress: str
    userAgent: str
    metadata: dict
    createdAt: str


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogResponse]
    total: int
    page: int
    pageSize: int
    offset: int


class AuditRetentionUpdateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retentionDays: int = Field(ge=1, le=3650)


class AuditRetentionResponse(BaseModel):
    retentionDays: int
    scheduleTimeZone: str
    lastRunAt: str | None
    lastArchiveAt: str | None
    lastArchivedCount: int
    lastCutoffAt: str | None
    lastArchiveFilename: str
    lastError: str
    updatedAt: str


class AdminDashboardResponse(BaseModel):
    userStats: dict
    permissionOverview: dict
    loginStats: dict
    notificationStats: dict
    recentAuditLogs: list[AuditLogResponse]
