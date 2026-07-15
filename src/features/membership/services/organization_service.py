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
        if parent and current["path"] and parent["path"].startswith(current["path"]):
            raise ValidationFailureError("Organization unit cannot be moved under its child.")
        self._ensure_unique_code("membership_organization_unit", payload["code"], exclude_id=unit_id)
        updated = self.repository.update_unit(unit_id, payload)
        if updated is None:
            raise ResourceNotFoundError("Organization unit not found.", {"id": unit_id})
        return updated

    def delete_unit(self, unit_id: str) -> None:
        self.get_unit(unit_id)
        if not self.repository.delete_unit(unit_id):
            raise ResourceNotFoundError("Organization unit not found.", {"id": unit_id})

    def list_positions(self, *, keyword: str = "", status_filter: str = "") -> list[dict[str, Any]]:
        return self.repository.list_positions(keyword=keyword, status_filter=status_filter)

    def create_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_unique_code("membership_position", payload["code"])
        try:
            return self.repository.create_position(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Position code already exists.") from exc

    def update_position(self, position_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.repository.get_position(position_id) is None:
            raise ResourceNotFoundError("Position not found.", {"id": position_id})
        self._ensure_unique_code("membership_position", payload["code"], exclude_id=position_id)
        updated = self.repository.update_position(position_id, payload)
        if updated is None:
            raise ResourceNotFoundError("Position not found.", {"id": position_id})
        return updated

    def delete_position(self, position_id: str) -> None:
        if not self.repository.delete_position(position_id):
            raise ResourceNotFoundError("Position not found.", {"id": position_id})

    def list_user_department_mappings(self, *, user_id: str = "", organization_id: str = "") -> list[dict[str, Any]]:
        return self.repository.list_user_department_mappings(user_id=user_id, organization_id=organization_id)

    def create_user_department_mapping(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_user(payload["userId"])
        self._validate_organization(payload["organizationId"])
        self._validate_position(payload.get("positionId"))
        try:
            return self.repository.upsert_user_department_mapping(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("User department mapping already exists.") from exc

    def delete_user_department_mapping(self, mapping_id: str) -> None:
        if not self.repository.delete_user_department_mapping(mapping_id):
            raise ResourceNotFoundError("User department mapping not found.", {"id": mapping_id})

    def list_manager_relations(self, *, manager_user_id: str = "", employee_user_id: str = "") -> list[dict[str, Any]]:
        return self.repository.list_manager_relations(manager_user_id=manager_user_id, employee_user_id=employee_user_id)

    def create_manager_relation(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["managerUserId"] == payload["employeeUserId"]:
            raise ValidationFailureError("Manager and employee cannot be the same user.")
        self._validate_user(payload["managerUserId"])
        self._validate_user(payload["employeeUserId"])
        self._validate_organization(payload.get("organizationId"))
        try:
            return self.repository.create_manager_relation(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Manager relation already exists.") from exc

    def delete_manager_relation(self, relation_id: str) -> None:
        if not self.repository.delete_manager_relation(relation_id):
            raise ResourceNotFoundError("Manager relation not found.", {"id": relation_id})

    def list_data_policies(self, *, subject_type: str = "", subject_id: str = "", resource_code: str = "") -> list[dict[str, Any]]:
        return self.repository.list_data_policies(subject_type=subject_type, subject_id=subject_id, resource_code=resource_code)

    def upsert_data_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_subject(payload["subjectType"], payload["subjectId"])
        if payload.get("dataScope") == "CUSTOM":
            for organization_id in payload.get("customScope", []):
                self._validate_organization(organization_id)
        return self.repository.upsert_data_policy(payload)

    def delete_data_policy(self, policy_id: str) -> None:
        if not self.repository.delete_data_policy(policy_id):
            raise ResourceNotFoundError("Data permission policy not found.", {"id": policy_id})

    def list_row_rules(self, policy_id: str = "") -> list[dict[str, Any]]:
        return self.repository.list_row_rules(policy_id)

    def create_row_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_policy(payload["policyId"])
        return self.repository.create_row_rule(payload)

    def delete_row_rule(self, rule_id: str) -> None:
        if not self.repository.delete_row_rule(rule_id):
            raise ResourceNotFoundError("Row permission rule not found.", {"id": rule_id})

    def list_field_rules(self, policy_id: str = "") -> list[dict[str, Any]]:
        return self.repository.list_field_rules(policy_id)

    def upsert_field_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_policy(payload["policyId"])
        try:
            return self.repository.upsert_field_rule(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Field permission rule already exists.") from exc

    def delete_field_rule(self, rule_id: str) -> None:
        if not self.repository.delete_field_rule(rule_id):
            raise ResourceNotFoundError("Field permission rule not found.", {"id": rule_id})

    def list_masking_rules(self, policy_id: str = "") -> list[dict[str, Any]]:
        return self.repository.list_masking_rules(policy_id)

    def upsert_masking_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_policy(payload["policyId"])
        try:
            return self.repository.upsert_masking_rule(payload)
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Sensitive masking rule already exists.") from exc

    def delete_masking_rule(self, rule_id: str) -> None:
        if not self.repository.delete_masking_rule(rule_id):
            raise ResourceNotFoundError("Sensitive masking rule not found.", {"id": rule_id})

    def _validate_unit_references(self, payload: dict[str, Any]) -> None:
        self._validate_organization(payload.get("parentId"))
        self._validate_organization(payload.get("companyId"))
        self._validate_user(payload.get("managerUserId"))

    def _validate_user(self, user_id: str | None) -> None:
        if not self.repository.entity_exists("membership_user", user_id):
            raise ValidationFailureError("User does not exist.", {"userId": user_id})

    def _validate_organization(self, organization_id: str | None) -> None:
        if not self.repository.entity_exists("membership_organization_unit", organization_id):
            raise ValidationFailureError("Organization unit does not exist.", {"organizationId": organization_id})

    def _validate_position(self, position_id: str | None) -> None:
        if not self.repository.entity_exists("membership_position", position_id):
            raise ValidationFailureError("Position does not exist.", {"positionId": position_id})

    def _validate_policy(self, policy_id: str) -> None:
        if not self.repository.entity_exists("membership_data_permission_policy", policy_id):
            raise ValidationFailureError("Data permission policy does not exist.", {"policyId": policy_id})

    def _validate_subject(self, subject_type: str, subject_id: str) -> None:
        table_name = "membership_role" if subject_type == "ROLE" else "membership_user"
        if not self.repository.entity_exists(table_name, subject_id):
            raise ValidationFailureError("Policy subject does not exist.", {"subjectId": subject_id})

    def _ensure_unique_code(self, table_name: str, code: str, exclude_id: str | None = None) -> None:
        if self.repository.code_exists(table_name, code, exclude_id=exclude_id):
            raise ConflictError("Code already exists.", {"code": code})
