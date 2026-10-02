#!/bin/bash
# Runs the watcher from this Mac (Lazada blocks GitHub's servers). Called by launchd:
#   run-local.sh drop   -> weekday 12:50, watch pinned items until 14:00 (+ 12:55 reminder)
#   run-local.sh sweep  -> every 15 min, one quiet restock check
# Install as a clone at ~/pokewatch: macOS blocks launchd jobs from reading ~/Desktop.
# Telegram creds live in .env (gitignored): TELEGRAM_BOT_TOKEN=... and TELEGRAM_CHAT_ID=...
cd "$(dirname "$0")" || exit 1
mkdir -p logs
git pull -q --ff-only 2>/dev/null || true   # pick up config/code pushed to GitHub
set -a; source .env; set +a
if [ "$1" = drop ]; then
  exec /usr/bin/python3 watch.py --no-search --auto
fi
pgrep -f "watch.py --no-search --auto" >/dev/null && exit 0   # drop loop already running
exec /usr/bin/python3 watch.py --no-search
