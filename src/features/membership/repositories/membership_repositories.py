from src.features.membership.models.entities import OrganizationUnit, Role, User
from src.features.membership.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[OrganizationUnit]):
    table_name = "membership_organization_unit"
    model_class = OrganizationUnit


class UserRepository(BaseRepository[User]):
    table_name = "membership_user"
    model_class = User


class RoleRepository(BaseRepository[Role]):
    table_name = "membership_role"
    model_class = Role
