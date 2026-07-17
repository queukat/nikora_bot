#!/usr/bin/env bash
set -Eeuo pipefail

source_dir=${1:?"usage: install.sh <staged-source-dir>"}
app_dir=/home/nikora_bot
unit_path=/etc/systemd/system/nikora-bot.service
env_path=/etc/nikora-bot.env

for required in \
  app/bot.py \
  app/config.py \
  app/translation_store.py \
  app/translator.py \
  data/translations.json \
  data/translation_memory.json \
  deploy/nikora-bot.service \
  schema.sql; do
  test -f "$source_dir/$required"
done

PYTHONPATH="$source_dir" "$app_dir/.venv/bin/python" -m compileall -q "$source_dir/app"
PYTHONPATH="$source_dir" "$app_dir/.venv/bin/python" -m unittest discover -s "$source_dir/tests" -q
systemd-analyze verify "$source_dir/deploy/nikora-bot.service"

umask 077
env_tmp=$(mktemp /tmp/nikora-env.XXXXXX)
if test -f "$env_path"; then
  cp "$env_path" "$env_tmp"
else
  main_pid=$(systemctl show nikora-bot --property=MainPID --value)
  test -n "$main_pid"
  test "$main_pid" != "0"
  tr '\0' '\n' < "/proc/$main_pid/environ" \
    | grep -E '^(TELEGRAM_BOT_TOKEN|DAILY_POLL_AT|POLL_SECONDS|NIKORA_API_URL|NIKORA_BASE_URL|EUROPRODUCT_ENABLED|EUROPRODUCT_PROMO_URL|EUROPRODUCT_BASE_URL|DATA_DIR|DB_PATH|TRANSLATIONS_PATH|TRANSLATION_MEMORY_PATH|UNTRANSLATED_PATH|DEALS_PAGE_SIZE|DEALS_CACHE_TTL_SECONDS|EUROPRODUCT_PAGE_CONCURRENCY|HTTP_TIMEOUT_S|HTTP_UA|TZ_NAME)=' \
    > "$env_tmp" || true
fi

if ! grep -q '^TELEGRAM_BOT_TOKEN=.' "$env_tmp"; then
  embedded_token=$("$app_dir/.venv/bin/python" -c '
import ast
from pathlib import Path

tree = ast.parse(Path("/home/nikora_bot/app/config.py").read_text(encoding="utf-8"))
for node in ast.walk(tree):
    if not isinstance(node, ast.Call) or len(node.args) < 2:
        continue
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "getenv":
        continue
    if not isinstance(node.args[0], ast.Constant) or node.args[0].value != "TELEGRAM_BOT_TOKEN":
        continue
    default = node.args[1]
    if isinstance(default, ast.Constant) and isinstance(default.value, str) and default.value:
        print(default.value, end="")
        break
')
  test -n "$embedded_token"
  printf 'TELEGRAM_BOT_TOKEN=%s\n' "$embedded_token" >> "$env_tmp"
  unset embedded_token
fi

grep -q '^TELEGRAM_BOT_TOKEN=.' "$env_tmp"
ensure_env() {
  local key=$1
  local value=$2
  if ! grep -q "^${key}=" "$env_tmp"; then
    printf '%s=%s\n' "$key" "$value" >> "$env_tmp"
  fi
}
ensure_env DATA_DIR /home/nikora_bot/data
ensure_env DAILY_POLL_AT 09:00
ensure_env TZ_NAME Asia/Tbilisi
ensure_env DEALS_CACHE_TTL_SECONDS 3600
ensure_env EUROPRODUCT_ENABLED true
ensure_env EUROPRODUCT_PAGE_CONCURRENCY 4
install -o root -g root -m 600 "$env_tmp" "$env_path"
rm -f "$env_tmp"

if ! id -u nikora_bot >/dev/null 2>&1; then
  useradd --system --home-dir "$app_dir" --no-create-home --shell /usr/sbin/nologin nikora_bot
fi

service_stopped=0
deployment_started=0
backup_dir="$app_dir/backups/$(date -u +%Y%m%dT%H%M%SZ)"
rollback() {
  trap - ERR
  if test "$service_stopped" = "1"; then
    if test "$deployment_started" = "1"; then
      echo "Deployment failed; restoring $backup_dir" >&2
      cp -a "$backup_dir/app/." "$app_dir/app/"
      cp -a "$backup_dir/data/." "$app_dir/data/"
      cp -a "$backup_dir/schema.sql" "$app_dir/schema.sql"
      cp -a "$backup_dir/nikora-bot.service" "$unit_path"
      systemctl daemon-reload
    fi
    systemctl start nikora-bot
  fi
}
trap rollback ERR

systemctl stop nikora-bot
service_stopped=1

mkdir -p "$backup_dir"
chmod 700 "$app_dir/backups" "$backup_dir"
cp -a "$app_dir/app" "$backup_dir/app"
cp -a "$app_dir/data" "$backup_dir/data"
cp -a "$app_dir/schema.sql" "$backup_dir/schema.sql"
cp -a "$unit_path" "$backup_dir/nikora-bot.service"
deployment_started=1

install -d -o root -g root -m 755 "$app_dir/app" "$app_dir/scripts"
install -o root -g root -m 644 "$source_dir"/app/*.py "$app_dir/app/"
install -o root -g root -m 644 "$source_dir"/scripts/*.py "$app_dir/scripts/"
install -o root -g root -m 644 "$source_dir/schema.sql" "$app_dir/schema.sql"

install -d -o nikora_bot -g nikora_bot -m 750 "$app_dir/data"
install -o nikora_bot -g nikora_bot -m 640 \
  "$source_dir/data/translations.json" \
  "$source_dir/data/translation_memory.json" \
  "$source_dir/data/fallback_glossary.json" \
  "$app_dir/data/"
chown -R nikora_bot:nikora_bot "$app_dir/data"

install -o root -g root -m 644 "$source_dir/deploy/nikora-bot.service" "$unit_path"
systemctl daemon-reload
systemctl start nikora-bot
sleep 3
systemctl is-active --quiet nikora-bot

service_stopped=0
trap - ERR
echo "Deployment complete; backup=$backup_dir"
