#!/usr/bin/env bash
#
# paper-retry-0800.sh — 종이신문 07:00 실행이 실패했을 때 08:00 에 딱 한 번 더 실행 (2026-11-09 사용자 요청)
#
# 판단: 오늘 날짜의 요약 기록(~/.openclaw/slack_logs/<날짜>.jsonl)에 '신문요약' 이 이미 있으면
#       07:00 실행이 성공한 것 → 아무것도 안 하고 끝(중복 실행·중복 요약 방지).
#       없으면 ~/newspaper-claude/run_daily.sh 를 한 번 실행한다. (재시도는 이 08:00 한 번뿐)
# 환경변수: NEWSPAPER_CLAUDE_DIR(기본 ~/newspaper-claude), OPENCLAW_HOME(기본 ~/.openclaw)
# 사용: paper-retry-0800.sh [--dry-run]   ※ cron 에 넣는 건 setup-paper-retry-cron.sh 가 한다.
set -uo pipefail
DIR="${NEWSPAPER_CLAUDE_DIR:-$HOME/newspaper-claude}"
HOME_OC="${OPENCLAW_HOME:-$HOME/.openclaw}"
TODAY="$(TZ=Asia/Seoul date +%F)"
LOG="$HOME_OC/slack_logs/$TODAY.jsonl"
say() { echo "[$(TZ=Asia/Seoul date '+%F %T')] paper-retry: $*"; }

if [ -s "$LOG" ] && grep -q "신문요약" "$LOG" 2>/dev/null; then
  say "오늘($TODAY) 요약이 이미 있어요 — 재시도 필요 없음"
  exit 0
fi
if [ ! -x "$DIR/run_daily.sh" ] && [ ! -f "$DIR/run_daily.sh" ]; then
  say "❌ $DIR/run_daily.sh 가 없어요"
  exit 1
fi
if [ "${1:-}" = "--dry-run" ]; then
  say "(시험) 요약이 없어서 실행할 것: bash $DIR/run_daily.sh"
  exit 0
fi
# 이미 실행 중이면(.run.lock 을 flock 으로 잡고 있으면) run_daily.sh 쪽 잠금이 알아서 막는다.
say "오늘 요약이 아직 없어요 — run_daily.sh 를 한 번 더 실행합니다"
cd "$DIR" && bash ./run_daily.sh
say "끝 (종료코드 $?)"
