"""Membership 組織與資料權限 API。

管理組織單位樹、職位、使用者部門關聯、主管關係，以及資料權限 policy、row rule、
field rule、masking rule。資料權限規則目前是設定資料，尚未套用到其他業務 API 的查詢
或遮罩 enforcement。
"""

from fastapi import Depends, Query, status

from src.features.membership.api.base import create_membership_router
from src.features.membership.core.auth_middleware import require_any_permission, require_authenticated_user, require_permission
from src.features.membership.core.responses import ok
from src.features.membership.schemas.common import StandardResponse
from src.features.membership.schemas.organization import (
    DataPermissionPolicyCommand,
    DataPermissionPolicyResponse,
    FieldPermissionRuleCommand,
    FieldPermissionRuleResponse,
    ManagerRelationCommand,
    ManagerRelationResponse,
    MaskingRuleCommand,
    MaskingRuleResponse,
    OrganizationUnitCommand,
    OrganizationUnitResponse,
    PositionCommand,
    PositionResponse,
    RowPermissionRuleCommand,
    RowPermissionRuleResponse,
    UserDepartmentMappingCommand,
    UserDepartmentMappingResponse,
)
from src.features.membership.services.organization_service import OrganizationService


organization_router = create_membership_router(
    prefix="/api/membership/organizations",
    tags=["membership-organizations"],
    dependencies=[Depends(require_authenticated_user)],
)


def organization_service() -> OrganizationService:
    return OrganizationService()


ORG_SCOPE_VIEW = "organization-scope.view"
ORG_SCOPE_ADD = "organization-scope.add"
ORG_SCOPE_EDIT = "organization-scope.edit"
ORG_SCOPE_DELETE = "organization-scope.delete"


@organization_router.get("/units", response_model=StandardResponse[list[OrganizationUnitResponse]])
async def list_units(
    keyword: str = Query(default=""),
    unitType: str = Query(default=""),
    status: str = Query(default=""),
    _: dict = Depends(require_any_permission([ORG_SCOPE_VIEW, "membership.write"])),
):
    return ok(organization_service().list_units(keyword=keyword, unit_type=unitType, status_filter=status))


@organization_router.get("/tree", response_model=StandardResponse[list[OrganizationUnitResponse]])
async def organization_tree(_: dict = Depends(require_permission(ORG_SCOPE_VIEW))):
    return ok(organization_service().organization_tree())


@organization_router.post(
    "/units",
    response_model=StandardResponse[OrganizationUnitResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_unit(
    payload: OrganizationUnitCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().create_unit(payload.model_dump()))


@organization_router.put("/units/{unit_id}", response_model=StandardResponse[OrganizationUnitResponse])
async def update_unit(
    unit_id: str,
    payload: OrganizationUnitCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_EDIT)),
):
    return ok(organization_service().update_unit(unit_id, payload.model_dump()))


@organization_router.delete("/units/{unit_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_unit(unit_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_unit(unit_id)
    return ok({"deleted": True})


@organization_router.get("/positions", response_model=StandardResponse[list[PositionResponse]])
async def list_positions(
    keyword: str = Query(default=""),
    status: str = Query(default=""),
    _: dict = Depends(require_permission(ORG_SCOPE_VIEW)),
):
    return ok(organization_service().list_positions(keyword=keyword, status_filter=status))


@organization_router.post(
    "/positions",
    response_model=StandardResponse[PositionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_position(
    payload: PositionCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().create_position(payload.model_dump()))


@organization_router.put("/positions/{position_id}", response_model=StandardResponse[PositionResponse])
async def update_position(
    position_id: str,
    payload: PositionCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_EDIT)),
):
    return ok(organization_service().update_position(position_id, payload.model_dump()))


@organization_router.delete("/positions/{position_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_position(position_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_position(position_id)
    return ok({"deleted": True})


@organization_router.get("/user-departments", response_model=StandardResponse[list[UserDepartmentMappingResponse]])
async def list_user_departments(
    userId: str = Query(default=""),
    organizationId: str = Query(default=""),
    _: dict = Depends(require_permission(ORG_SCOPE_VIEW)),
):
    return ok(organization_service().list_user_department_mappings(user_id=userId, organization_id=organizationId))


@organization_router.post(
    "/user-departments",
    response_model=StandardResponse[UserDepartmentMappingResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_user_department(
    payload: UserDepartmentMappingCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().create_user_department_mapping(payload.model_dump()))


@organization_router.delete("/user-departments/{mapping_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_user_department(mapping_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_user_department_mapping(mapping_id)
    return ok({"deleted": True})


@organization_router.get("/manager-relations", response_model=StandardResponse[list[ManagerRelationResponse]])
async def list_manager_relations(
    managerUserId: str = Query(default=""),
    employeeUserId: str = Query(default=""),
    _: dict = Depends(require_permission(ORG_SCOPE_VIEW)),
):
    return ok(organization_service().list_manager_relations(manager_user_id=managerUserId, employee_user_id=employeeUserId))


@organization_router.post(
    "/manager-relations",
    response_model=StandardResponse[ManagerRelationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_manager_relation(
    payload: ManagerRelationCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().create_manager_relation(payload.model_dump()))


@organization_router.delete("/manager-relations/{relation_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_manager_relation(relation_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_manager_relation(relation_id)
    return ok({"deleted": True})


# NOTE: 以下資料權限 policy / row rule / field rule / masking rule 目前只提供管理與儲存。
# 尚未串接到其他業務 API 的查詢過濾、欄位遮罩或寫入限制；後續導入時需在資料存取層套用這些規則。
@organization_router.get("/data-policies", response_model=StandardResponse[list[DataPermissionPolicyResponse]])
async def list_data_policies(
    subjectType: str = Query(default=""),
    subjectId: str = Query(default=""),
    resourceCode: str = Query(default=""),
    _: dict = Depends(require_permission(ORG_SCOPE_VIEW)),
):
    return ok(organization_service().list_data_policies(subject_type=subjectType, subject_id=subjectId, resource_code=resourceCode))


@organization_router.post("/data-policies", response_model=StandardResponse[DataPermissionPolicyResponse])
async def upsert_data_policy(
    payload: DataPermissionPolicyCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().upsert_data_policy(payload.model_dump()))


@organization_router.delete("/data-policies/{policy_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_data_policy(policy_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_data_policy(policy_id)
    return ok({"deleted": True})


@organization_router.get("/row-rules", response_model=StandardResponse[list[RowPermissionRuleResponse]])
async def list_row_rules(
    policyId: str = Query(default=""),
    _: dict = Depends(require_permission(ORG_SCOPE_VIEW)),
):
    return ok(organization_service().list_row_rules(policyId))


@organization_router.post("/row-rules", response_model=StandardResponse[RowPermissionRuleResponse])
async def create_row_rule(
    payload: RowPermissionRuleCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().create_row_rule(payload.model_dump()))


@organization_router.delete("/row-rules/{rule_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_row_rule(rule_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_row_rule(rule_id)
    return ok({"deleted": True})


@organization_router.get("/field-rules", response_model=StandardResponse[list[FieldPermissionRuleResponse]])
async def list_field_rules(
    policyId: str = Query(default=""),
    _: dict = Depends(require_permission(ORG_SCOPE_VIEW)),
):
    return ok(organization_service().list_field_rules(policyId))


@organization_router.post("/field-rules", response_model=StandardResponse[FieldPermissionRuleResponse])
async def upsert_field_rule(
    payload: FieldPermissionRuleCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().upsert_field_rule(payload.model_dump()))


@organization_router.delete("/field-rules/{rule_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_field_rule(rule_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_field_rule(rule_id)
    return ok({"deleted": True})


@organization_router.get("/masking-rules", response_model=StandardResponse[list[MaskingRuleResponse]])
async def list_masking_rules(
    policyId: str = Query(default=""),
    _: dict = Depends(require_permission(ORG_SCOPE_VIEW)),
):
    return ok(organization_service().list_masking_rules(policyId))


@organization_router.post("/masking-rules", response_model=StandardResponse[MaskingRuleResponse])
async def upsert_masking_rule(
    payload: MaskingRuleCommand,
    _: dict = Depends(require_permission(ORG_SCOPE_ADD)),
):
    return ok(organization_service().upsert_masking_rule(payload.model_dump()))


@organization_router.delete("/masking-rules/{rule_id}", response_model=StandardResponse[dict[str, bool]])
async def delete_masking_rule(rule_id: str, _: dict = Depends(require_permission(ORG_SCOPE_DELETE))):
    organization_service().delete_masking_rule(rule_id)
    return ok({"deleted": True})
