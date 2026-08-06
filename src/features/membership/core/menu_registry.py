from dataclasses import dataclass


@dataclass(frozen=True)
class MenuDefinition:
    id: str
    code: str
    title: str
    parentId: str | None
    routePath: str
    componentKey: str
    icon: str
    sortOrder: int
    requiredPermissionCode: str | None = None
    status: str = "ACTIVE"
    createdAt: str = ""
    updatedAt: str = ""


MENU_ITEMS: tuple[MenuDefinition, ...] = (
    MenuDefinition(
        id="menu-membership",
        code="MEMBERSHIP",
        title="會員權限管理",
        parentId=None,
        routePath="/membership",
        componentKey="MembershipLayout",
        icon="Security",
        sortOrder=10,
    ),
    MenuDefinition(
        id="menu-membership-dashboard",
        code="MEMBERSHIP_DASHBOARD",
        title="管理總覽",
        parentId="menu-membership",
        routePath="/membership/dashboard",
        componentKey="MembershipDashboardPage",
        icon="LayoutDashboard",
        sortOrder=10,
        requiredPermissionCode="membership.read",
    ),
    MenuDefinition(
        id="menu-users",
        code="MEMBERSHIP_USERS",
        title="會員帳號",
        parentId="menu-membership",
        routePath="/membership/users",
        componentKey="MembershipUsersPage",
        icon="Users",
        sortOrder=20,
        requiredPermissionCode="membership.read",
    ),
    MenuDefinition(
        id="menu-roles",
        code="MEMBERSHIP_ROLES",
        title="角色管理",
        parentId="menu-membership",
        routePath="/membership/roles",
        componentKey="MembershipRolesPage",
        icon="KeyRound",
        sortOrder=30,
        requiredPermissionCode="rbac.view",
    ),
    MenuDefinition(
        id="menu-user-roles",
        code="MEMBERSHIP_USER_ROLES",
        title="批次套用角色",
        parentId="menu-membership",
        routePath="/membership/user-roles",
        componentKey="MembershipUserRolesPage",
        icon="UserCog",
        sortOrder=40,
        requiredPermissionCode="membership.user-roles",
    ),
    MenuDefinition(
        id="menu-permissions",
        code="MEMBERSHIP_PERMISSIONS",
        title="權限管理",
        parentId="menu-membership",
        routePath="/membership/permissions",
        componentKey="MembershipPermissionsPage",
        icon="ShieldCheck",
        sortOrder=50,
        requiredPermissionCode="rbac.view",
    ),
    MenuDefinition(
        id="menu-organizations",
        code="MEMBERSHIP_ORGS",
        title="組織資料權限",
        parentId="menu-membership",
        routePath="/membership/organizations",
        componentKey="MembershipOrganizationsPage",
        icon="Building2",
        sortOrder=70,
        requiredPermissionCode="organization-scope.view",
    ),
    MenuDefinition(
        id="menu-audit",
        code="MEMBERSHIP_AUDIT",
        title="日誌安全",
        parentId="menu-membership",
        routePath="/membership/audit",
        componentKey="MembershipAuditPage",
        icon="FileSearch",
        sortOrder=80,
        requiredPermissionCode="audit.view",
    ),
    MenuDefinition(
        id="menu-notifications",
        code="MEMBERSHIP_NOTIFICATIONS",
        title="通知管理",
        parentId="menu-membership",
        routePath="/membership/notifications",
        componentKey="MembershipNotificationsPage",
        icon="FileSearch",
        sortOrder=90,
        requiredPermissionCode="notification.view",
    ),
)


def all_menu_rows() -> list[dict[str, object]]:
    return [_menu_row(menu) for menu in MENU_ITEMS]


def current_menu_rows(permission_codes: set[str]) -> list[dict[str, object]]:
    visible_ids = {
        menu.id
        for menu in MENU_ITEMS
        if menu.requiredPermissionCode is None or menu.requiredPermissionCode in permission_codes
    }
    child_parent_ids = {
        menu.parentId
        for menu in MENU_ITEMS
        if menu.parentId and menu.id in visible_ids
    }
    return [
        _menu_row(menu)
        for menu in MENU_ITEMS
        if menu.id in visible_ids and (menu.requiredPermissionCode is not None or menu.id in child_parent_ids)
    ]


def _menu_row(menu: MenuDefinition) -> dict[str, object]:
    return {
        "id": menu.id,
        "code": menu.code,
        "title": menu.title,
        "parentId": menu.parentId,
        "routePath": menu.routePath,
        "componentKey": menu.componentKey,
        "icon": menu.icon,
        "sortOrder": menu.sortOrder,
        "status": menu.status,
        "requiredPermissionCode": menu.requiredPermissionCode,
        "children": [],
        "createdAt": menu.createdAt,
        "updatedAt": menu.updatedAt,
    }
