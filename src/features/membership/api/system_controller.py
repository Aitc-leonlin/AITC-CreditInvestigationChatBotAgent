"""Membership 系統管理 API。

提供會員模組 metadata 查詢。Migration 與預設資料初始化統一由應用程式啟動流程執行，
不再由 API request 觸發。
"""

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import ModuleMetadata, StandardResponse


membership_system_router = create_membership_router(
    prefix="/api/membership/system",
    tags=["membership-system"],
)


@membership_system_router.get(
    "/metadata",
    response_model=StandardResponse[ModuleMetadata],
)
async def get_membership_module_metadata():
    return ok(
        {
            "module": "Enterprise Membership & Authorization",
            "phase": "Phase 5 - Dynamic Menu and Frontend Authorization",
            "capabilities": [
                "folder-structure",
                "database-schema",
                "migration",
                "orm-models",
                "repository-base-class",
                "service-base-class",
                "controller-base-structure",
                "api-response-format",
                "error-handling",
                "validation-structure",
                "seed-data",
                "member-management",
                "authentication",
                "rbac",
                "dynamic-menu",
                "frontend-authorization",
            ],
            "nextPhases": [
                "Phase 2 - member-management",
                "Phase 3 - authentication",
                "Phase 4 - rbac",
                "Phase 5 - menu-authorization",
                "Phase 6 - organization-data-scope",
                "Phase 7 - audit-security",
                "Phase 8 - notification-testing",
            ],
        }
    )
