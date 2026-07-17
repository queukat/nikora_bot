from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.storage import Storage


ROOT = Path(__file__).resolve().parents[1]


class StorageTests(unittest.TestCase):
    def test_migrates_old_subscription_table_and_keeps_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "bot.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE subscriptions (
                  chat_id INTEGER NOT NULL,
                  item_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  last_hash_sent TEXT,
                  last_seen_at TEXT,
                  last_end_reminder_sent TEXT,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  PRIMARY KEY (chat_id, item_id)
                );
                CREATE TABLE chat_settings (
                  chat_id INTEGER PRIMARY KEY,
                  remind_days INTEGER NOT NULL DEFAULT 3
                );
                """
            )
            connection.close()

            storage = Storage(db_path)
            try:
                storage.init_schema((ROOT / "schema.sql").read_text(encoding="utf-8"))
                storage.upsert_subscribe(42, "europroduct:demo")
                storage.update_item_snapshot(
                    42,
                    "europroduct:demo",
                    title_original="Demo product",
                    title_ru="Тестовый товар",
                    old_price="12.00",
                    new_price="9.00",
                    start_date=None,
                    end_date=None,
                )

                subscription = storage.list_subs(42)[0]
                self.assertEqual(subscription.title_original, "Demo product")
                self.assertEqual(subscription.title_ru, "Тестовый товар")
                self.assertEqual(subscription.old_price, "12.00")
                self.assertEqual(subscription.new_price, "9.00")
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
