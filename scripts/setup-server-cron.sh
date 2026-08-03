#!/usr/bin/env bash
#
# setup-server-cron.sh — 서버에 자동 pull cron 등록 (멱등)
#
# git-auto-pull.sh 를 1분마다 실행하도록 현재 사용자의 crontab 에 추가합니다.
# 여러 번 실행해도 중복 등록되지 않습니다.
#
# 사용법 (서버에서 실행):
#   scripts/setup-server-cron.sh
#
# 조정하고 싶은 값이 있으면 환경변수로 넘기세요:
#   OPENCLAW_GIT_BRANCH   추적 브랜치 (기본: main)
#   OPENCLAW_RESTART_CMD  재시작 명령 (기본: openclaw daemon restart)
#   PULL_SCHEDULE         cron 스케줄 (기본: "* * * * *" = 매 1분)
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PULL_SCRIPT="$REPO_DIR/scripts/git-auto-pull.sh"
BRANCH="${OPENCLAW_GIT_BRANCH:-main}"
RESTART_CMD="${OPENCLAW_RESTART_CMD:-openclaw daemon restart}"
SCHEDULE="${PULL_SCHEDULE:-* * * * *}"
LOGFILE="$REPO_DIR/scripts/auto-pull.log"

chmod +x "$PULL_SCRIPT"

# cron 은 최소 환경이라 openclaw(PATH) 와 systemctl --user(XDG_RUNTIME_DIR) 가
# 안 잡힘. 그래서 실행에 필요한 환경을 cron 라인에 직접 넣는다.
UID_NUM="$(id -u)"
# openclaw 바이너리 위치 → 그 디렉토리를 PATH 앞에 붙임
OC_BIN="$(command -v openclaw 2>/dev/null || true)"
OC_DIR="${OC_BIN:+$(dirname "$OC_BIN")}"
CRON_PATH="${OC_DIR:+$OC_DIR:}$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin"

# cron 한 줄 구성 (식별용 주석 태그 포함 → 멱등 갱신에 사용)
TAG="# openclaw-auto-pull"
CRON_LINE="$SCHEDULE PATH='$CRON_PATH' XDG_RUNTIME_DIR='/run/user/$UID_NUM' OPENCLAW_DIR='$REPO_DIR' OPENCLAW_GIT_BRANCH='$BRANCH' OPENCLAW_RESTART_CMD='$RESTART_CMD' $PULL_SCRIPT >> '$LOGFILE' 2>&1 $TAG"

# 기존 태그 라인 제거 후 새 라인 추가
current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -vF "$TAG" || true)"
{
  printf '%s\n' "$filtered" | sed '/^$/d'
  printf '%s\n' "$CRON_LINE"
} | crontab -

echo "[setup] crontab 등록 완료:"
echo "  $CRON_LINE"
echo
echo "[setup] 확인: crontab -l"
echo "[setup] 로그: $LOGFILE"
echo
echo "※ 재시작(openclaw daemon restart = systemctl --user)이 cron 에서 동작하려면"
echo "  사용자 세션이 로그아웃 후에도 유지되도록 linger 를 켜두는 걸 권장합니다:"
echo "    sudo loginctl enable-linger $(whoami)"
echo "  (한 번만 실행하면 됩니다.)"
