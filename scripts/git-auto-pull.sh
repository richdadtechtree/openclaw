#!/usr/bin/env bash
#
# git-auto-pull.sh — 서버에서 주기적으로 실행(cron)하여 원격 설정을 반영
#
# 동작:
#   1. 원격 브랜치를 fetch
#   2. stock 소스 동기화(sync-stock.sh)는 새 커밋 여부와 무관하게 매 tick 마다 실행
#      - sync-stock.sh 자체가 rsync 체크섬 비교라 변경 없으면 사실상 no-op.
#      - ⚠️ 예전엔 "새 커밋 감지" 분기 안에서만 호출돼서, 그 실행이 락 경합 등으로
#        실패하면 리포가 이미 최신이라 다음 tick부터는 영원히 재시도가 안 되고
#        실행 폴더(~/stock/stock)가 조용히 옛날 코드에 고정되는 사일런트 버그가
#        있었다(2026-08/09월에 두 번 재현). 매 tick 무조건 실행으로 근본 해결.
#   3. 새 커밋이 없으면 나머지(설정 동기화·게이트웨이 재시작)는 생략
#   4. 새 커밋이 있으면 "설정 파일(git 추적 대상)만" 원격 상태로 강제 동기화
#      - reset --mixed + checkout 방식이라 런타임 파일(세션/로그/미디어/DB)은
#        절대 삭제·변경되지 않습니다. (working tree 의 untracked 파일은 그대로 유지)
#   5. openclaw 서비스 재시작 (systemd)
#
# 안전성:
#   - flock 으로 중복 실행 방지
#   - git 추적 대상은 설정 파일뿐이므로 강제 동기화해도 런타임 데이터 손실 없음
#
# 환경변수 (필요에 맞게 조정):
#   OPENCLAW_DIR          리포 경로            (기본: 스크립트 상위 디렉토리)
#   OPENCLAW_GIT_BRANCH   추적 브랜치          (기본: main)
#   OPENCLAW_RESTART_CMD  pull 후 실행할 재시작 명령
#                         (기본: "openclaw daemon restart")
#                         재시작이 필요 없으면 OPENCLAW_RESTART_CMD=":" 로 설정
#
set -euo pipefail

REPO_DIR="${OPENCLAW_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BRANCH="${OPENCLAW_GIT_BRANCH:-main}"
RESTART_CMD="${OPENCLAW_RESTART_CMD:-openclaw daemon restart}"
LOCK="/tmp/openclaw-auto-pull.lock"

log() { echo "[auto-pull] $(date '+%F %T') $*"; }

# 중복 실행 방지: 이미 실행 중이면 조용히 종료
exec 9>"$LOCK"
if ! flock -n 9; then
  exit 0
fi

cd "$REPO_DIR"

# 원격 최신 상태 가져오기 (네트워크 오류 시 지수 백오프 재시도)
delay=2
fetched=0
for attempt in 1 2 3 4; do
  if git fetch --quiet origin "$BRANCH"; then
    fetched=1
    break
  fi
  log "fetch 실패, ${delay}s 후 재시도... ($attempt/4)"
  sleep "$delay"
  delay=$((delay * 2))
done
if [ "$fetched" -ne 1 ]; then
  log "fetch 실패 (재시도 초과). 종료."
  exit 1
fi

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

# --- stock 소스 동기화: 새 커밋 여부와 무관하게 매 tick 무조건 실행 -------------
# 리포가 이미 최신이어도(=아래서 곧 exit 0) 이 실행 폴더 동기화는 반드시 시도한다.
# sync-stock.sh 는 rsync 체크섬 비교라 변경 없으면 사실상 no-op.
STOCK_SYNC="$REPO_DIR/scripts/sync-stock.sh"
if [ -f "$STOCK_SYNC" ]; then
  bash "$STOCK_SYNC" || log "stock 동기화 실패(무시하고 계속)" >&2
fi

if [ "$LOCAL" = "$REMOTE" ]; then
  # 새 커밋 없음 → 설정 동기화·게이트웨이 재시작은 생략(조용히 종료)
  exit 0
fi

log "새 커밋 감지: ${LOCAL:0:8} → ${REMOTE:0:8}"

# openclaw 게이트웨이 재시작이 필요한 변경인지 판단.
#   stock/ · scripts/ · 루트 문서만 바뀌면 openclaw 재시작 불필요(뚜떵또 대화 중단 방지).
#   stock scheduler 는 sync-stock.sh 가 따로 재시작하고, scripts/문서는 런타임 무관.
#   workspace/ · agents/ · cron/ · openclaw 설정 등이 바뀔 때만 게이트웨이 재시작.
CHANGED="$(git diff --name-only "$LOCAL" "$REMOTE" 2>/dev/null || true)"
NEED_OC_RESTART=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    stock/*|scripts/*) : ;;
    HANDOFF.md|CLAUDE.md|README.md|.gitignore|.env.example|requirements.txt) : ;;
    *) NEED_OC_RESTART=1 ;;
  esac
done <<< "$CHANGED"

# --- 설정 파일만 안전하게 원격 상태로 동기화 -----------------------------------
# reset --mixed: HEAD 와 index 를 원격에 맞추되 working tree 는 건드리지 않음
#                → 추적 해제되는 런타임 파일이 untracked 로 남아 디스크에 보존됨
# checkout -- . : index(=원격)에 있는 "추적 파일"만 working tree 에 반영
#                → 설정 파일은 원격으로 강제 갱신, untracked 런타임 파일은 무시
git reset --mixed --quiet "$REMOTE"
git checkout --quiet --force -- .

log "설정 동기화 완료 (런타임 파일 보존됨)"

# --- openclaw 게이트웨이 재시작 (필요할 때만) ----------------------------------
if [ "$NEED_OC_RESTART" -eq 0 ]; then
  log "openclaw 재시작 불필요(stock/scripts/문서 변경만) — 건너뜀"
elif [ -n "$RESTART_CMD" ] && [ "$RESTART_CMD" != ":" ]; then
  if eval "$RESTART_CMD"; then
    log "서비스 재시작 완료: $RESTART_CMD"
  else
    log "서비스 재시작 실패: $RESTART_CMD" >&2
    exit 1
  fi
fi

log "동기화 종료"
