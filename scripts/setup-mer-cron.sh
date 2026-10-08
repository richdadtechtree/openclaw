#!/usr/bin/env bash
#
# setup-mer-cron.sh — 메르님 블로그 새 글 → #메르의-가르침 확인을 cron 에 등록 (멱등)
#
# 10분마다 mer_blog_slack.py 를 실행. 새 글이 없으면 아무것도 안 보낸다.
# 표준 라이브러리만 쓰므로 시스템 python3 로 충분 (venv 불필요).
#
# 사용법 (서버에서):  ~/.openclaw/scripts/setup-mer-cron.sh
# 조정:  MER_SCHEDULE="*/5 * * * *" (기본 "*/10 * * * *")   PYTHON_BIN=python3 경로
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_DIR/scripts/mer_blog_slack.py"
LOGFILE="$REPO_DIR/scripts/mer-blog.log"
SCHEDULE="${MER_SCHEDULE:-*/10 * * * *}"
PY="${PYTHON_BIN:-$(command -v python3 || true)}"
[ -n "$PY" ] || { echo "[error] python3 를 찾지 못했습니다." >&2; exit 1; }
[ -f "$SCRIPT" ] || { echo "[error] 스크립트가 없습니다: $SCRIPT" >&2; exit 1; }

TAG="# openclaw-mer-blog"
LINE="$SCHEDULE PATH='$(dirname "$PY"):/usr/local/bin:/usr/bin:/bin' '$PY' '$SCRIPT' >> '$LOGFILE' 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -vF "$TAG" || true)"
{ printf '%s\n' "$filtered" | sed '/^$/d'; printf '%s\n' "$LINE"; } | crontab -

echo "[setup] 등록 완료: $LINE"
echo "[setup] 확인: crontab -l    로그: tail -f $LOGFILE"
