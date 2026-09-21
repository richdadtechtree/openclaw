#!/usr/bin/env bash
#
# setup-pilates-cron.sh — 미리 써둔 마이비필라테스 블로그 글을 **매일 아침 6시(한국시간)** 에
#                         슬랙 #심부름 으로 배달하는 cron 을 등록한다. (멱등)
#
# 사용법 (서버에서 한 번만):
#   ~/.openclaw/scripts/setup-pilates-cron.sh
#
# 무엇을 하나
#   crontab 에 아래 한 줄을 넣는다(여러 번 실행해도 중복되지 않는다):
#     <시각> cd ~/.openclaw/scripts && python3 pilates_blog.py >> pilates-blog.log 2>&1
#
# ⏰ 시간대 자동 환산
#   cron 은 '서버 로컬 시간' 으로 돈다. 서버가 한국시간이 아니면 06:00 로 걸어봐야
#   엉뚱한 시각에 돈다. 그래서 이 스크립트가 서버 시간대를 읽어 **06:00 KST 에
#   해당하는 서버 로컬 시각**으로 바꿔서 등록한다. (예: 서버가 UTC면 21:00 전날)
#   ※ 글 안에 들어가는 '오늘 주제'는 스크립트가 항상 한국 날짜로 계산하므로 안전하다.
#
# 조정(환경변수)
#   KST_HOUR=6        한국시간 기준 실행 시(0~23). 기본 6
#   KST_MIN=0         분. 기본 0
#   SCHEDULE="0 6 * * *"   이걸 주면 환산 없이 이 cron 식을 그대로 쓴다
#   PYTHON_BIN=...    파이썬 실행기 (기본: 자동탐지 python3)
#
# 참고: pilates_blog.py 는 표준 라이브러리만 쓰고 AI 키도 안 쓴다 → venv 불필요
#       (이 리포 단골 함정인 "requests 없음" 에 걸리지 않는다).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_DIR/scripts/pilates_blog.py"
LOGFILE="$REPO_DIR/scripts/pilates-blog.log"
TAG="# openclaw-pilates-blog"

if [ ! -f "$SCRIPT" ]; then
  echo "[error] $SCRIPT 가 없습니다." >&2
  exit 1
fi

# ⚠️ venv 가 켜진 상태에서 이 스크립트를 실행하면 `command -v python3` 가
#    venv 파이썬(예: ~/newspaper/.venv/bin/python3)을 가리킨다.
#    pilates_blog.py 는 **표준 라이브러리만** 쓰므로 venv 가 전혀 필요 없고,
#    그 폴더가 지워지거나 옮겨지면 cron 이 조용히 실패한다.
#    → 그래서 cron 에는 **사라질 걱정이 없는 시스템 파이썬**을 기본으로 넣는다.
#      (굳이 다른 파이썬을 쓰려면 PYTHON_BIN 으로 지정하면 된다.)
if [ -n "${PYTHON_BIN:-}" ]; then
  PY="$PYTHON_BIN"
elif [ -x /usr/bin/python3 ]; then
  PY=/usr/bin/python3
else
  PY="$(command -v python3 || true)"
fi
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
  echo "[error] python3 를 찾지 못했습니다. PYTHON_BIN 으로 지정하세요." >&2
  exit 1
fi
case "$PY" in
  */.venv/*|*/venv/*)
    echo "[주의] cron 에 venv 파이썬($PY)을 넣습니다. 이 스크립트는 venv 가 필요 없으니" >&2
    echo "       PYTHON_BIN=/usr/bin/python3 로 다시 등록하시는 편이 안전합니다." >&2 ;;
esac

# ── 06:00 KST → 서버 로컬 시각으로 환산 ────────────────────────────────────
if [ -n "${SCHEDULE:-}" ]; then
  CRON_TIME="$SCHEDULE"
  NOTE="(SCHEDULE 지정값 그대로 사용)"
else
  KST_HOUR="${KST_HOUR:-6}"
  KST_MIN="${KST_MIN:-0}"
  OFF="$(date +%z)"                                  # 예: +0900, -0700
  SIGN="${OFF:0:1}"; OH="${OFF:1:2}"; OM="${OFF:3:2}"
  LOCAL_OFF=$(( 10#$OH * 60 + 10#$OM ))
  [ "$SIGN" = "-" ] && LOCAL_OFF=$(( -LOCAL_OFF ))
  KST_OFF=540                                        # 한국 = UTC+9 = 540분
  TOTAL=$(( KST_HOUR * 60 + KST_MIN + LOCAL_OFF - KST_OFF ))
  TOTAL=$(( (TOTAL % 1440 + 1440) % 1440 ))          # 0~1439 로 정규화(날짜 넘김 처리)
  LH=$(( TOTAL / 60 )); LM=$(( TOTAL % 60 ))
  CRON_TIME="$LM $LH * * *"
  if [ "$LOCAL_OFF" -eq "$KST_OFF" ]; then
    NOTE="(서버가 한국시간 — 그대로 ${KST_HOUR}시 ${KST_MIN}분)"
  else
    NOTE="(서버 시간대 ${OFF} → 06:00 KST = 서버 로컬 $(printf '%02d:%02d' "$LH" "$LM"))"
  fi
fi

LINE="$CRON_TIME cd '$REPO_DIR/scripts' && '$PY' '$SCRIPT' >> '$LOGFILE' 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -vF "$TAG" || true)"
{
  printf '%s\n' "$filtered" | sed '/^$/d'
  printf '%s\n' "$LINE"
} | crontab -

echo "[setup] 필라테스 블로그 cron 등록 완료 $NOTE"
echo "  $LINE"
echo
echo "[확인] crontab -l | grep pilates"
echo "[로그] tail -f $LOGFILE"
echo
echo "[먼저 해둘 것]"
echo "  1) 슬랙 #심부름 채널에서  /invite @뚜떵또   (봇이 채널에 없으면 not_in_channel 오류)"
echo "  2) 창고 점검 + 한 편 미리보기 (발송 안 함):"
echo "       $PY $SCRIPT --check"
echo "       $PY $SCRIPT --dry-run"
