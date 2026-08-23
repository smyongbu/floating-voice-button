from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config_store import APP_DATA_DIR


HISTORY_PATH = APP_DATA_DIR / "history.db"


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    operation_id: str
    created_at: str
    text: str
    status: str = "completed"
    batch_id: str = ""
    preview_text: str = ""
    error_message: str = ""
    queue_position: int = 0


class HistoryRevisionMismatch(RuntimeError):
    """确认清空后数据库又发生变化。"""


class HistoryStore:
    """本机识别历史。正文只写入数据库，不接入任何日志。"""

    def __init__(self, path: Path = HISTORY_PATH, limit: int = 500) -> None:
        self.path = Path(path)
        self.limit = max(1, int(limit))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=3.0)
        try:
            connection.execute("PRAGMA busy_timeout = 3000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recognition_history (
                    operation_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    text TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row[1]) for row in connection.execute(
                    "PRAGMA table_info(recognition_history)"
                ).fetchall()
            }
            migrations = {
                "status": "TEXT NOT NULL DEFAULT 'completed'",
                "batch_id": "TEXT NOT NULL DEFAULT ''",
                "preview_text": "TEXT NOT NULL DEFAULT ''",
                "error_message": "TEXT NOT NULL DEFAULT ''",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE recognition_history ADD COLUMN {name} {definition}"
                    )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS history_meta (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO history_meta(key, value) VALUES ('revision', 0)"
            )

    @staticmethod
    def _bump_revision(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE history_meta SET value = value + 1 WHERE key = 'revision'"
        )

    def add(self, operation_id: str, text: str) -> HistoryEntry:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("不能保存空白历史记录。")
        safe_operation_id = str(operation_id).strip()
        if not safe_operation_id:
            raise ValueError("历史记录缺少操作编号。")
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO recognition_history(operation_id, created_at, text) "
                "VALUES (?, ?, ?)",
                (safe_operation_id, created_at, text),
            )
            prune_cursor = connection.execute(
                """
                DELETE FROM recognition_history
                WHERE operation_id NOT IN (
                    SELECT operation_id FROM recognition_history
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT ?
                )
                """,
                (self.limit,),
            )
            if cursor.rowcount > 0 or prune_cursor.rowcount > 0:
                self._bump_revision(connection)
        return HistoryEntry(safe_operation_id, created_at, text)

    def reserve(self, operation_id: str, batch_id: str) -> HistoryEntry:
        safe_operation_id = str(operation_id).strip()
        safe_batch_id = str(batch_id).strip()
        if not safe_operation_id or not safe_batch_id:
            raise ValueError("待处理历史记录缺少操作编号或批次编号。")
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO recognition_history"
                "(operation_id, created_at, text, status, batch_id, preview_text, error_message) "
                "VALUES (?, ?, '', 'queued', ?, '', '')",
                (safe_operation_id, created_at, safe_batch_id),
            )
            prune_cursor = connection.execute(
                """
                DELETE FROM recognition_history
                WHERE operation_id NOT IN (
                    SELECT operation_id FROM recognition_history
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT ?
                )
                """,
                (self.limit,),
            )
            if cursor.rowcount > 0 or prune_cursor.rowcount > 0:
                self._bump_revision(connection)
        return HistoryEntry(safe_operation_id, created_at, "", "queued", safe_batch_id)

    def mark_recognizing(self, operation_id: str, preview_text: str = "") -> bool:
        return self._update_pending(
            operation_id, "recognizing", preview_text=str(preview_text or "")
        )

    def complete(self, operation_id: str, text: str) -> bool:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("不能用空白文字完成历史记录。")
        return self._update_pending(
            operation_id, "completed", text=text, preview_text="", error_message=""
        )

    def fail(self, operation_id: str, message: str) -> bool:
        return self._update_pending(
            operation_id, "failed", preview_text="", error_message=str(message or "识别失败")
        )

    def _update_pending(self, operation_id: str, status: str, **values: str) -> bool:
        allowed = {"text", "preview_text", "error_message"}
        assignments = ["status = ?"]
        parameters: list[object] = [status]
        for name, value in values.items():
            if name not in allowed:
                continue
            assignments.append(f"{name} = ?")
            parameters.append(value)
        parameters.append(str(operation_id))
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE recognition_history SET {', '.join(assignments)} "
                "WHERE operation_id = ? AND status IN ('queued', 'recognizing')",
                tuple(parameters),
            )
            changed = cursor.rowcount > 0
            if changed:
                self._bump_revision(connection)
            return changed

    @staticmethod
    def _search_parts(query: str) -> tuple[str, tuple[object, ...]]:
        search = str(query).strip()
        parameters: tuple[object, ...] = ()
        where = ""
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where = "WHERE text LIKE ? ESCAPE '\\' OR preview_text LIKE ? ESCAPE '\\'"
            parameters = (f"%{escaped}%", f"%{escaped}%")
        return where, parameters

    def snapshot(self, query: str = "") -> tuple[list[HistoryEntry], tuple[int, int]]:
        """在同一 SQLite 读事务中取得列表与变化签名。"""
        where, parameters = self._search_parts(query)
        with self._connect() as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                f"SELECT operation_id, created_at, text, status, batch_id, preview_text, error_message "
                f"FROM recognition_history {where} "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (*parameters, self.limit),
            ).fetchall()
            signature_row = connection.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM recognition_history), "
                "(SELECT value FROM history_meta WHERE key = 'revision')"
            ).fetchone()
        queue_positions: dict[str, int] = {}
        for row in reversed(rows):
            if str(row[3]) == "queued":
                batch_id = str(row[4])
                queue_positions[batch_id] = queue_positions.get(batch_id, 0) + 1
        seen_positions: dict[str, int] = {}
        entries = []
        for row in rows:
            batch_id = str(row[4])
            queue_position = 0
            if str(row[3]) == "queued":
                queue_position = queue_positions.get(batch_id, 0) - seen_positions.get(batch_id, 0)
                seen_positions[batch_id] = seen_positions.get(batch_id, 0) + 1
            entries.append(HistoryEntry(
                str(row[0]), str(row[1]), str(row[2]), str(row[3]), batch_id,
                str(row[5]), str(row[6]), queue_position,
            ))
        signature = (
            int(signature_row[0]),
            int(signature_row[1]) if signature_row and signature_row[1] is not None else 0,
        )
        return entries, signature

    def list_entries(self, query: str = "") -> list[HistoryEntry]:
        return self.snapshot(query)[0]

    def get(self, operation_id: str) -> HistoryEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT operation_id, created_at, text, status, batch_id, preview_text, error_message "
                "FROM recognition_history "
                "WHERE operation_id = ?",
                (str(operation_id),),
            ).fetchone()
        if row is None:
            return None
        return HistoryEntry(
            str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]),
            str(row[5]), str(row[6]), 0,
        )

    def delete(self, operation_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM recognition_history WHERE operation_id = ?", (str(operation_id),)
            )
            deleted = cursor.rowcount > 0
            if deleted:
                self._bump_revision(connection)
            return deleted

    def delete_pending(self, operation_id: str) -> bool:
        """只删除尚未完成的队列占位，避免覆盖退出恢复或已完成记录。"""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM recognition_history WHERE operation_id = ? "
                "AND status IN ('queued', 'recognizing')",
                (str(operation_id),),
            )
            deleted = cursor.rowcount > 0
            if deleted:
                self._bump_revision(connection)
            return deleted

    def clear(self, expected_revision: int | None = None) -> int:
        with self._connect() as connection:
            if expected_revision is not None:
                row = connection.execute(
                    "SELECT value FROM history_meta WHERE key = 'revision'"
                ).fetchone()
                current_revision = int(row[0]) if row else 0
                if current_revision != int(expected_revision):
                    raise HistoryRevisionMismatch("历史记录在确认后发生了变化。")
            cursor = connection.execute("DELETE FROM recognition_history")
            count = max(0, int(cursor.rowcount))
            if count > 0:
                self._bump_revision(connection)
            return count

    def signature(self) -> tuple[int, int]:
        """返回条数与持久修订号，不读取或暴露正文。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM recognition_history), "
                "(SELECT value FROM history_meta WHERE key = 'revision')"
            ).fetchone()
        return int(row[0]), int(row[1]) if row and row[1] is not None else 0

    def pending_count(self) -> int:
        """返回全部排队中与识别中的记录数，不受搜索条件影响。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM recognition_history "
                "WHERE status IN ('queued', 'recognizing')"
            ).fetchone()
        return int(row[0]) if row else 0

    def fail_pending(self, message: str) -> int:
        """主程序启动时把上次异常退出遗留的待处理记录转为失败。"""
        safe_message = str(message or "程序上次退出前未完成识别，请重新录制。")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE recognition_history "
                "SET status = 'failed', preview_text = '', error_message = ? "
                "WHERE status IN ('queued', 'recognizing')",
                (safe_message,),
            )
            count = max(0, int(cursor.rowcount))
            if count:
                self._bump_revision(connection)
            return count
