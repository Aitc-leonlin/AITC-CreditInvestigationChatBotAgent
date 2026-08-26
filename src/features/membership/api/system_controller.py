"""Membership 系統管理 API。

提供會員模組 metadata 查詢與 bootstrap 初始化入口，用來套用 membership
migration，並建立預設組織、角色、權限、選單與通知模板資料。
"""

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import InfrastructureStatus, ModuleMetadata, StandardResponse
from src.features.membership.services.bootstrap_service import ensure_membership_infrastructure


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


@membership_system_router.post(
    "/bootstrap",
    response_model=StandardResponse[InfrastructureStatus],
)
async def bootstrap_membership_module():
    return ok(ensure_membership_infrastructure())
