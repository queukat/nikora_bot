from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .utils import to_iso_now


@dataclass(frozen=True)
class Subscription:
    chat_id: int
    item_id: str
    created_at: str
    last_hash_sent: Optional[str]
    last_seen_at: Optional[str]
    last_end_reminder_sent: Optional[str]
    is_active: bool


class Storage:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def init_schema(self, schema_sql: str) -> None:
        self._conn.executescript(schema_sql)
        self._conn.commit()

    # --- settings ---

    def get_remind_days(self, chat_id: int) -> int:
        cur = self._conn.execute(
            "SELECT remind_days FROM chat_settings WHERE chat_id = ?",
            (chat_id,),
        )
        row = cur.fetchone()
        if row is None:
            return 3
        try:
            return int(row["remind_days"])
        except Exception:
            return 3

    def set_remind_days(self, chat_id: int, days: int) -> None:
        days = max(0, int(days))
        self._conn.execute(
            """
            INSERT INTO chat_settings(chat_id, remind_days) VALUES(?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET remind_days = excluded.remind_days
            """,
            (chat_id, days),
        )
        self._conn.commit()

    # --- subscriptions ---

    def list_subs(self, chat_id: int) -> List[Subscription]:
        cur = self._conn.execute(
            """
            SELECT chat_id, item_id, created_at, last_hash_sent, last_seen_at, last_end_reminder_sent, is_active
            FROM subscriptions
            WHERE chat_id = ?
            ORDER BY created_at DESC
            """,
            (chat_id,),
        )
        return [self._row_to_sub(r) for r in cur.fetchall()]

    def is_subscribed(self, chat_id: int, item_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM subscriptions WHERE chat_id = ? AND item_id = ?",
            (chat_id, item_id),
        )
        return cur.fetchone() is not None

    def upsert_subscribe(self, chat_id: int, item_id: str) -> None:
        now = to_iso_now()
        self._conn.execute(
            """
            INSERT INTO subscriptions(chat_id, item_id, created_at, last_hash_sent, last_seen_at, last_end_reminder_sent, is_active)
            VALUES(?, ?, ?, NULL, NULL, NULL, 1)
            ON CONFLICT(chat_id, item_id) DO UPDATE SET
              is_active = 1
            """,
            (chat_id, item_id, now),
        )
        self._conn.commit()

    def unsubscribe(self, chat_id: int, item_id: str) -> None:
        self._conn.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND item_id = ?",
            (chat_id, item_id),
        )
        self._conn.commit()

    def update_seen_and_hash(self, chat_id: int, item_id: str, seen_at: str, content_hash: str) -> None:
        self._conn.execute(
            """
            UPDATE subscriptions
            SET last_seen_at = ?, last_hash_sent = ?, is_active = 1
            WHERE chat_id = ? AND item_id = ?
            """,
            (seen_at, content_hash, chat_id, item_id),
        )
        self._conn.commit()

    def update_end_reminder_sent(self, chat_id: int, item_id: str, end_date: str) -> None:
        now = to_iso_now()
        self._conn.execute(
            """
            UPDATE subscriptions
            SET last_end_reminder_sent = ?, last_seen_at = COALESCE(last_seen_at, ?)
            WHERE chat_id = ? AND item_id = ?
            """,
            (end_date, now, chat_id, item_id),
        )
        self._conn.commit()

    def mark_inactive(self, chat_id: int, item_id: str) -> None:
        self._conn.execute(
            """
            UPDATE subscriptions
            SET is_active = 0
            WHERE chat_id = ? AND item_id = ?
            """,
            (chat_id, item_id),
        )
        self._conn.commit()

    def iter_all_subscriptions(self) -> Iterable[Subscription]:
        cur = self._conn.execute(
            """
            SELECT chat_id, item_id, created_at, last_hash_sent, last_seen_at, last_end_reminder_sent, is_active
            FROM subscriptions
            """
        )
        for r in cur.fetchall():
            yield self._row_to_sub(r)

    @staticmethod
    def _row_to_sub(r: sqlite3.Row) -> Subscription:
        return Subscription(
            chat_id=int(r["chat_id"]),
            item_id=str(r["item_id"]),
            created_at=str(r["created_at"]),
            last_hash_sent=r["last_hash_sent"],
            last_seen_at=r["last_seen_at"],
            last_end_reminder_sent=r["last_end_reminder_sent"],
            is_active=bool(int(r["is_active"])),
        )
