#!/usr/bin/env bash
#
# sync-stock.sh — openclaw repo 의 vendor 소스(~/.openclaw/stock/*.py)를
#                 실제 실행 폴더(~/stock/stock)로 동기화하고, 코드가 바뀐
#                 경우에만 scheduler 를 재시작한다.
#
# 배경(A안 vendoring):
#   주식 프로젝트 소스는 openclaw repo 의 stock/ 에서 관리(=claude.ai 에서 편집).
#   서버는 git-auto-pull 로 repo 를 받은 뒤, 이 스크립트로 코드만 실행 폴더에
#   반영한다. venv / *.sqlite / .env / monitored_stocks.json(감시종목 데이터) 등
#   런타임·비밀은 절대 건드리지 않는다(코드 .py 만 rsync, --delete 안 함).
#
# 동작:
#   1. SRC(vendor)·DST(실행) 둘 다 있어야 진행. 없으면 조용히 종료(0).
#   2. .py 만 rsync(체크섬 비교). 변경 없으면 재시작하지 않고 종료.
#   3. 변경이 있으면 scheduler 를 단일 인스턴스로 재시작.
#
# 환경변수:
#   OPENCLAW_STOCK_SRC   vendor 소스 경로   (기본: ~/.openclaw/stock)
#   STOCK_DIR            실행 폴더 경로     (기본: ~/stock/stock)
#   STOCK_PY             파이썬 실행기      (기본: <STOCK_DIR>/venv/bin/python)
#
set -uo pipefail

SRC="${OPENCLAW_STOCK_SRC:-$HOME/.openclaw/stock}"
DST="${STOCK_DIR:-$HOME/stock/stock}"
PY="${STOCK_PY:-$DST/venv/bin/python}"
LOCK="/tmp/openclaw-sync-stock.lock"

log() { echo "[sync-stock] $(date '+%F %T') $*"; }

# 중복 실행 방지
exec 8>"$LOCK"
if ! flock -n 8; then
  exit 0
fi

[ -d "$SRC" ] || { exit 0; }                       # vendor 아직 없음 → no-op
[ -d "$DST" ] || { log "실행 폴더 없음: $DST"; exit 0; }

# 코드(.py)만 동기화. 디렉토리 구조는 유지, 그 외 전부 제외(venv/DB/.env/json/…).
# -c 체크섬 비교, -i 변경 항목 출력. --delete 안 함(서버 런타임 보존).
CHANGES="$(rsync -rcim \
  --include='*/' \
  --include='*.py' \
  --exclude='*' \
  "$SRC"/ "$DST"/ 2>&1)"
rc=$?
if [ "$rc" -ne 0 ]; then
  log "rsync 실패(rc=$rc): $CHANGES"
  exit 1
fi

CHANGED="$(printf '%s\n' "$CHANGES" | grep -E '^[<>ch]' || true)"
if [ -z "$CHANGED" ]; then
  exit 0                                            # 코드 변경 없음 → 재시작 안 함
fi

log "stock 코드 변경 반영:"
printf '%s\n' "$CHANGED"

# scheduler 단일 인스턴스로 재시작
if [ ! -x "$PY" ]; then
  log "파이썬 실행기 없음: $PY (재시작 생략)"
  exit 1
fi
cd "$DST" || { log "cd 실패: $DST"; exit 1; }
pkill -f "scheduler.py" 2>/dev/null || true
sleep 2
nohup "$PY" scheduler.py > "$DST/scheduler.log" 2>&1 &
sleep 2
pids="$(pgrep -f 'scheduler.py' | tr '\n' ' ')"
log "scheduler 재시작 완료 (pid: ${pids:-없음})"
