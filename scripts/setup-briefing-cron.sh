#!/usr/bin/env bash
#
# setup-briefing-cron.sh — 종국이(GYM종국) 데일리/주간 브리핑 자동 스케줄 등록 (멱등)
#
# 서버 crontab 에 아래 두 잡을 등록합니다. 여러 번 실행해도 중복되지 않습니다.
#   • 데일리 브리핑: 매일 21:00 (KST)  → pt_briefing.py daily
#   • 주간 브리핑:   일요일 20:00 (KST) → pt_briefing.py weekly
#   • 보고 독촉 톡:  10:00 아침 / 13:30 점심 / 18:30 운동 / 20:30 마지막 경고 → pt_nudge.py
#                    (2026-10-06 신설. 기록이 이미 있으면 아무것도 안 보냄. 끄려면 .env 에 PT_NUDGE=off)
# 각 잡은 DB(briefings 테이블)에 저장 → PT 웹 대시보드에 표시 + 슬랙(keepgoing) 전송.
#
# 사용법 (서버에서 실행):
#   scripts/setup-briefing-cron.sh
#
# 조정(환경변수):
#   DAILY_SCHEDULE    데일리 cron 식 (기본: "0 21 * * *")
#   WEEKLY_SCHEDULE   주간 cron 식   (기본: "0 20 * * 0"  = 일요일 20시)
#   NUDGE_MORNING / NUDGE_LUNCH / NUDGE_WORKOUT / NUDGE_FINAL  독촉 cron 식
#                     (기본: "0 10 * * *" / "30 13 * * *" / "30 18 * * *" / "30 20 * * *")
#   PYTHON_BIN        파이썬 실행기  (기본: 자동탐지 python3)
#
# ⚠️ cron 은 서버 로컬 타임존을 씁니다. 서버가 KST 가 아니면 시각을 환산하세요.
#    (확인:  date;  timedatectl 2>/dev/null | grep -i zone)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_DIR/scripts/pt_briefing.py"
LOGFILE="$REPO_DIR/scripts/pt-briefing.log"

DAILY_SCHEDULE="${DAILY_SCHEDULE:-0 21 * * *}"
WEEKLY_SCHEDULE="${WEEKLY_SCHEDULE:-0 20 * * 0}"
NUDGE_MORNING="${NUDGE_MORNING:-0 10 * * *}"
NUDGE_LUNCH="${NUDGE_LUNCH:-30 13 * * *}"
NUDGE_WORKOUT="${NUDGE_WORKOUT:-30 18 * * *}"
NUDGE_FINAL="${NUDGE_FINAL:-30 20 * * *}"
NUDGE="$REPO_DIR/scripts/pt_nudge.py"

PY="${PYTHON_BIN:-$(command -v python3 || true)}"
if [ -z "$PY" ]; then
  echo "[error] python3 를 찾지 못했습니다. PYTHON_BIN 으로 지정하세요." >&2
  exit 1
fi

# cron 은 최소 PATH 라 python3 절대경로를 넣는다.
PY_DIR="$(dirname "$PY")"
CRON_PATH="$PY_DIR:/usr/local/bin:/usr/bin:/bin"

TAG_DAILY="# openclaw-pt-daily-briefing"
TAG_WEEKLY="# openclaw-pt-weekly-briefing"
LINE_DAILY="$DAILY_SCHEDULE PATH='$CRON_PATH' cd '$REPO_DIR/scripts' && '$PY' '$SCRIPT' daily >> '$LOGFILE' 2>&1 $TAG_DAILY"
LINE_WEEKLY="$WEEKLY_SCHEDULE PATH='$CRON_PATH' cd '$REPO_DIR/scripts' && '$PY' '$SCRIPT' weekly >> '$LOGFILE' 2>&1 $TAG_WEEKLY"

TAG_NUDGE="# openclaw-pt-nudge"
nudge_line() {  # $1=cron 식  $2=slot
  printf '%s' "$1 PATH='$CRON_PATH' cd '$REPO_DIR/scripts' && '$PY' '$NUDGE' $2 >> '$LOGFILE' 2>&1 $TAG_NUDGE-$2"
}

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -vF "$TAG_DAILY" | grep -vF "$TAG_WEEKLY" | grep -vF "$TAG_NUDGE" || true)"
{
  printf '%s\n' "$filtered" | sed '/^$/d'
  printf '%s\n' "$LINE_DAILY"
  printf '%s\n' "$LINE_WEEKLY"
  nudge_line "$NUDGE_MORNING" morning; echo
  nudge_line "$NUDGE_LUNCH" lunch; echo
  nudge_line "$NUDGE_WORKOUT" workout; echo
  nudge_line "$NUDGE_FINAL" final; echo
} | crontab -

echo "[setup] 브리핑 cron 등록 완료:"
echo "  daily : $LINE_DAILY"
echo "  weekly: $LINE_WEEKLY"
echo "  nudge : 아침 $NUDGE_MORNING / 점심 $NUDGE_LUNCH / 운동 $NUDGE_WORKOUT / 마지막 $NUDGE_FINAL"
echo
echo "[setup] 확인:  crontab -l"
echo "[setup] 로그 :  $LOGFILE"
echo
echo "[test ] 지금 바로 한 번 만들어 보려면:"
echo "  $PY $SCRIPT daily --print"
echo "  $PY $SCRIPT weekly --print"
echo "  $PY $NUDGE lunch --dry-run      # 독촉: 지금 보낸다면 뭐라고 할지(안 보냄)"
