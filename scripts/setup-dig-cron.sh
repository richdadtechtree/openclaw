#!/usr/bin/env bash
#
# setup-dig-cron.sh — 매일경제 '디그' 뉴스레터(Gmail) → 웹 캐시 수집을 cron 에 등록 (멱등)
#
# 30분마다 dig_mail.py 를 실행해 새 디그 메일을 ~/.openclaw/dig_cache/ 에 저장한다.
# 새 메일이 없으면 아무것도 안 한다. 표준 라이브러리만 → 시스템 python3 로 충분.
#
# 먼저 ~/.openclaw/.env 에 두 줄이 있어야 한다 (Gmail '앱 비밀번호', 일반 비밀번호 아님):
#   DIG_GMAIL_USER=bbonoyo@gmail.com
#   DIG_GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
#
# 사용법 (서버에서):  ~/.openclaw/scripts/setup-dig-cron.sh
# 조정:  DIG_SCHEDULE="*/15 * * * *" (기본 "*/30 * * * *")   PYTHON_BIN=python3 경로
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_DIR/stock/dig_mail.py"
LOGFILE="$REPO_DIR/scripts/dig-mail.log"
SCHEDULE="${DIG_SCHEDULE:-*/30 * * * *}"
PY="${PYTHON_BIN:-$(command -v python3 || true)}"
[ -n "$PY" ] || { echo "[error] python3 를 찾지 못했습니다." >&2; exit 1; }
[ -f "$SCRIPT" ] || { echo "[error] 스크립트가 없습니다: $SCRIPT" >&2; exit 1; }

TAG="# openclaw-dig-mail"
LINE="$SCHEDULE PATH='$(dirname "$PY"):/usr/local/bin:/usr/bin:/bin' '$PY' '$SCRIPT' >> '$LOGFILE' 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -vF "$TAG" || true)"
{ printf '%s\n' "$filtered" | sed '/^$/d'; printf '%s\n' "$LINE"; } | crontab -

echo "[setup] 등록 완료: $LINE"
echo "[setup] 확인: crontab -l    로그: tail -f $LOGFILE"
