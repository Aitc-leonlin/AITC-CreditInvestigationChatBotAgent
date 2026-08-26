import sqlite3
from typing import Any

from src.features.membership.core.exceptions import ConflictError, ResourceNotFoundError, ValidationFailureError
from src.features.membership.repositories.organization_repository import OrganizationRepository
from src.features.membership.services.bootstrap_service import apply_membership_migration


class OrganizationService:
    def __init__(self, repository: OrganizationRepository | None = None):
        apply_membership_migration()
        self.repository = repository or OrganizationRepository()

    def list_units(self, *, keyword: str = "", unit_type: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        return self.repository.list_units(keyword=keyword, unit_type=unit_type, status_filter=status_filter)

    def organization_tree(self) -> list[dict[str, Any]]:
        units = self.list_units()
        by_id = {unit["id"]: {**unit, "children": []} for unit in units}
        roots: list[dict[str, Any]] = []
        for unit in by_id.values():
            parent_id = unit["parentId"]
            if parent_id and parent_id in by_id:
                by_id[parent_id]["children"].append(unit)
            else:
                roots.append(unit)
        return roots

    def get_unit(self, unit_id: str) -> dict[str, Any]:
        unit = self.repository.get_unit(unit_id)
        if unit is None:
            raise ResourceNotFoundError("Organization unit not found.", {"id": unit_id})
        return unit

    def create_unit(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_unit_references(payload)
        self._ensure_unique_code("membership_organization_unit", payload["code"])
        try:
            return self.repository.create_unit(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Organization unit code already exists.") from exc

    def update_unit(self, unit_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_unit(unit_id)
        if payload.get("parentId") == unit_id:
            raise ValidationFailureError("Organization unit cannot be its own parent.")
        self._validate_unit_references(payload)
        parent = self.repository.get_unit(payload["parentId"]) if payload.get("parentId") else None
        if parent and current["path"] and (
            parent["path"] == current["path"]
            or parent["path"].startswith(f"{current['path']}/")
        ):
            raise ValidationFailureError("Organization unit cannot be moved under its child.")
        self._ensure_unique_code("membership_organization_unit", payload["code"], exclude_id=unit_id)
        updated = self.repository.update_unit(unit_id, payload)
        if updated is None:
            raise ResourceNotFoundError("Organization unit not found.", {"id": unit_id})
        return updated

    def delete_unit(self, unit_id: str) -> dict[str, int]:
        self.get_unit(unit_id)
        result = self.repository.delete_unit_tree(unit_id)
        if result["deletedCount"] == 0:
            raise ResourceNotFoundError("Organization unit not found.", {"id": unit_id})
        return result

    def list_positions(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        return self.repository.list_positions(keyword=keyword, status_filter=status_filter)

    def create_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.repository.create_position(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Unable to create position.") from exc

    def update_position(self, position_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.repository.get_position(position_id) is None:
            raise ResourceNotFoundError("Position not found.", {"id": position_id})
        updated = self.repository.update_position(position_id, payload)
        if updated is None:
            raise ResourceNotFoundError("Position not found.", {"id": position_id})
        return updated

    def delete_position(self, position_id: str) -> None:
        if not self.repository.delete_position(position_id):
            raise ResourceNotFoundError("Position not found.", {"id": position_id})

    def _validate_unit_references(self, payload: dict[str, Any]) -> None:
        self._validate_organization(payload.get("parentId"))
        self._validate_user(payload.get("managerUserId"))

    def _validate_user(self, user_id: str | None) -> None:
        if not self.repository.entity_exists("membership_user", user_id):
            raise ValidationFailureError("User does not exist.", {"userId": user_id})

    def _validate_organization(self, organization_id: str | None) -> None:
        if not self.repository.entity_exists("membership_organization_unit", organization_id):
            raise ValidationFailureError("Organization unit does not exist.", {"organizationId": organization_id})

    def _ensure_unique_code(self, table_name: str, code: str, exclude_id: str | None = None) -> None:
        if self.repository.code_exists(table_name, code, exclude_id=exclude_id):
            raise ConflictError("Code already exists.", {"code": code})
