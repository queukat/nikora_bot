PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS subscriptions (
  chat_id INTEGER NOT NULL,
  item_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_hash_sent TEXT,
  last_seen_at TEXT,
  last_end_reminder_sent TEXT, -- хранит end_date, для которого уже слали напоминание
  title_original TEXT,
  title_ru TEXT,
  old_price TEXT,
  new_price TEXT,
  start_date TEXT,
  end_date TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (chat_id, item_id)
);

CREATE TABLE IF NOT EXISTS chat_settings (
  chat_id INTEGER PRIMARY KEY,
  remind_days INTEGER NOT NULL DEFAULT 3
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_item ON subscriptions(item_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_chat ON subscriptions(chat_id);
