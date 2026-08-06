"""Best-effort audit logging shared by membership and business features."""

import json
import logging
import uuid
from typing import Any

from src.features.membership.core.database import membership_transaction
from src.features.membership.core.time import utc_now_iso


logger = logging.getLogger(__name__)


class AuditService:
    def record(
        self,
        *,
        actor_user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str = "",
        outcome: str = "SUCCESS",
        ip_address: str = "",
        user_agent: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write an audit row without allowing audit failures to break the operation."""
        try:
            now = utc_now_iso()
            with membership_transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO membership_audit_log (
                        id, actor_user_id, action, resource_type, resource_id, outcome,
                        ip_address, user_agent, metadata_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        str(uuid.uuid4()),
                        actor_user_id,
                        action,
                        resource_type,
                        resource_id,
                        outcome.upper(),
                        ip_address,
                        user_agent,
                        json.dumps(metadata or {}, ensure_ascii=False),
                        now,
                        now,
                    ],
                )
        except Exception:
            logger.exception(
                "Audit log write failed: action=%s resource_type=%s resource_id=%s",
                action,
                resource_type,
                resource_id,
            )
