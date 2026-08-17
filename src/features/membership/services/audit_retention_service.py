"""Daily audit-log archive job.

Rows older than the configured retention period are written to a UTF-8 TXT
archive before they are permanently removed from SQLite.
"""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.features.membership.core.database import get_membership_connection, membership_transaction
from src.features.membership.core.time import utc_now_iso
from src.features.membership.services.bootstrap_service import apply_membership_migration
from src.shared.database.db_path import PROJECT_ROOT
from src.shared.database.connection import is_postgresql


logger = logging.getLogger(__name__)
SCHEDULE_TIME_ZONE = ZoneInfo("Asia/Taipei")
DEFAULT_ARCHIVE_DIRECTORY = PROJECT_ROOT / "storage" / "audit_log_archives"
ARCHIVE_DIRECTORY_ENV = "AUDIT_LOG_ARCHIVE_DIR"
SCHEDULER_POLL_SECONDS = 60 * 60


def resolve_audit_archive_directory() -> Path:
    configured = os.getenv(ARCHIVE_DIRECTORY_ENV, "").strip()
    if not configured:
        return DEFAULT_ARCHIVE_DIRECTORY
    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


class AuditRetentionService:
    def run_daily_archive(self) -> dict[str, object]:
        """Run at most once per Taipei calendar day across app workers."""
        apply_membership_migration()
        local_date = datetime.now(SCHEDULE_TIME_ZONE).date().isoformat()
        connection = get_membership_connection()
        archive_path: Path | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            setting = connection.execute(
                "SELECT * FROM membership_audit_retention_setting WHERE id = 1"
            ).fetchone()
            if setting is None:
                raise RuntimeError("Audit retention setting is not initialized.")
            if setting["last_checked_date"] == local_date:
                connection.rollback()
                return {"status": "SKIPPED", "reason": "ALREADY_CHECKED_TODAY"}

            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=int(setting["retention_days"]))
            cutoff_iso = cutoff.isoformat()
            cutoff_expression = (
                "created_at::timestamptz < ?::timestamptz"
                if is_postgresql()
                else "datetime(created_at) < datetime(?)"
            )
            rows = connection.execute(
                f"""
                SELECT *
                FROM membership_audit_log
                WHERE {cutoff_expression}
                ORDER BY created_at ASC, id ASC
                """,
                [cutoff_iso],
            ).fetchall()

            filename = ""
            if rows:
                archive_path = self._write_archive(rows, cutoff=cutoff, archived_at=now)
                filename = archive_path.name
                connection.execute(
                    f"DELETE FROM membership_audit_log WHERE {cutoff_expression}",
                    [cutoff_iso],
                )

            run_at = utc_now_iso()
            connection.execute(
                """
                UPDATE membership_audit_retention_setting
                SET last_checked_date = ?, last_run_at = ?, last_archive_at = ?,
                    last_archived_count = ?, last_cutoff_at = ?,
                    last_archive_filename = ?, last_error = '', updated_at = ?
                WHERE id = 1
                """,
                [
                    local_date,
                    run_at,
                    run_at if rows else setting["last_archive_at"],
                    len(rows),
                    cutoff_iso,
                    filename if rows else setting["last_archive_filename"],
                    run_at,
                ],
            )
            connection.commit()
            logger.info(
                "Audit retention completed: retention_days=%s archived_count=%s archive=%s",
                setting["retention_days"],
                len(rows),
                filename,
            )
            return {
                "status": "COMPLETED",
                "archivedCount": len(rows),
                "archiveFilename": filename,
                "cutoffAt": cutoff_iso,
            }
        except Exception as exc:
            connection.rollback()
            if archive_path is not None:
                archive_path.unlink(missing_ok=True)
            self._record_error(str(exc))
            logger.exception("Daily audit retention failed")
            return {"status": "FAILED", "error": str(exc)}
        finally:
            connection.close()

    def _write_archive(self, rows: list, *, cutoff: datetime, archived_at: datetime) -> Path:
        archive_directory = resolve_audit_archive_directory()
        archive_directory.mkdir(parents=True, exist_ok=True)
        filename = (
            f"audit-log_{archived_at.strftime('%Y%m%dT%H%M%SZ')}"
            f"_before_{cutoff.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.txt"
        )
        final_path = archive_directory / filename
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".audit-log-",
            suffix=".tmp",
            dir=archive_directory,
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archive:
                archive.write("AITC Audit Log Archive\n")
                archive.write(f"archived_at_utc: {archived_at.isoformat()}\n")
                archive.write(f"records_created_before_utc: {cutoff.isoformat()}\n")
                archive.write(f"record_count: {len(rows)}\n")
                archive.write("format: one JSON object per line\n")
                archive.write("---\n")
                for row in rows:
                    payload = dict(row)
                    try:
                        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
                    except json.JSONDecodeError:
                        payload["metadata"] = payload.pop("metadata_json", "")
                    archive.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                    archive.write("\n")
                archive.flush()
                os.fsync(archive.fileno())
            os.replace(temporary_path, final_path)
            return final_path
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _record_error(self, message: str) -> None:
        try:
            now = utc_now_iso()
            with membership_transaction() as connection:
                connection.execute(
                    """
                    UPDATE membership_audit_retention_setting
                    SET last_run_at = ?, last_error = ?, updated_at = ?
                    WHERE id = 1
                    """,
                    [now, message[:2000], now],
                )
        except Exception:
            logger.exception("Unable to persist audit retention error")


async def run_audit_retention_scheduler() -> None:
    """Check hourly; the database guard allows one successful run per day."""
    service = AuditRetentionService()
    while True:
        try:
            await asyncio.to_thread(service.run_daily_archive)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Audit retention scheduler iteration failed")
        await asyncio.sleep(SCHEDULER_POLL_SECONDS)
