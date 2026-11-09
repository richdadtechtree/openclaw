#!/usr/bin/env bash
#
# setup-paper-retry-cron.sh — 매일 08:00 에 paper-retry-0800.sh 를 부르는 cron 한 줄을 등록 (멱등)
#   사용: ~/.openclaw/scripts/setup-paper-retry-cron.sh [--remove]
#   확인: crontab -l | grep paper-retry     로그: ~/.openclaw/logs/paper-retry.log
set -euo pipefail
MARK="paper-retry-0800.sh"
SCRIPT="$HOME/.openclaw/scripts/paper-retry-0800.sh"
LINE="0 8 * * * bash $SCRIPT >> $HOME/.openclaw/logs/paper-retry.log 2>&1"
current="$(crontab -l 2>/dev/null || true)"
rest="$(printf '%s\n' "$current" | grep -vF "$MARK" || true)"
if [ "${1:-}" = "--remove" ]; then
  printf '%s\n' "$rest" | crontab -; echo "✅ 08:00 재시도 줄 제거"; exit 0
fi
mkdir -p "$HOME/.openclaw/logs"
printf '%s\n%s\n' "$rest" "$LINE" | sed '/^$/N;/^\n$/D' | crontab -
echo "✅ 등록: $LINE"
