#!/usr/bin/env bash
#
# extract-secrets-to-env.sh — 서버의 live openclaw.json 에서 키를 뽑아 .env 생성
#
# 이미 openclaw.json 에 키가 들어있는 경우, 손으로 입력할 필요 없이
# 그 값들을 그대로 .env 로 옮겨줍니다. (직접 입력하려면 setup-env.sh 사용)
#
# 사용법 (서버에서):
#   scripts/extract-secrets-to-env.sh
#
# 필요 도구: jq
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="${OPENCLAW_CONF:-$REPO_DIR/openclaw.json}"
ENV_FILE="$REPO_DIR/.env"

command -v jq >/dev/null 2>&1 || { echo "오류: jq 필요 (sudo apt install jq)" >&2; exit 1; }
[ -f "$CONF" ] || { echo "오류: $CONF 없음. OPENCLAW_CONF 로 지정하세요." >&2; exit 1; }

[ -f "$ENV_FILE" ] && cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)" && echo "[extract] 기존 .env 백업함"

# 이미 ${...} 참조로 바뀐 값은 무시(빈 값 취급)
val() { jq -r "$1 // empty" "$CONF" | grep -v '^\${' || true; }

tg_default="$(val '.channels.telegram.accounts.default.botToken')"
tg_pt="$(val '.channels.telegram.accounts.pt.botToken')"
brave="$(val '.plugins.entries.brave.config.webSearch.apiKey // .tools.web.search.apiKey')"
gemini="$(val '.auth.profiles."google:default".apiKey // .models.providers.google.apiKey')"
gwtoken="$(val '.gateway.auth.token')"

{
  echo "# openclaw 비밀 키 (extract-secrets-to-env.sh: $(date '+%F %T'))"
  echo "# .gitignore 로 git 에 올라가지 않음"
  echo
  echo "TELEGRAM_BOT_TOKEN_DEFAULT=${tg_default}"
  echo "TELEGRAM_BOT_TOKEN_PT=${tg_pt}"
  echo "BRAVE_API_KEY=${brave}"
  echo "GEMINI_API_KEY=${gemini}"
  echo "GATEWAY_TOKEN=${gwtoken}"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "[extract] .env 생성 완료: $ENV_FILE (권한 600)"
for var in TELEGRAM_BOT_TOKEN_DEFAULT TELEGRAM_BOT_TOKEN_PT BRAVE_API_KEY GEMINI_API_KEY GATEWAY_TOKEN; do :; done
for pair in "TELEGRAM_BOT_TOKEN_DEFAULT:$tg_default" "TELEGRAM_BOT_TOKEN_PT:$tg_pt" "BRAVE_API_KEY:$brave" "GEMINI_API_KEY:$gemini" "GATEWAY_TOKEN:$gwtoken"; do
  name="${pair%%:*}"; v="${pair#*:}"
  if [ -n "$v" ]; then echo "  ✓ $name = ${v:0:6}… (${#v}자)"; else echo "  ✗ $name  (설정에 없음 — setup-env.sh 로 입력)"; fi
done
echo
echo "다음: scripts/apply-env-refs.sh 로 openclaw.json 을 \${참조} 로 바꾸고 재시작하세요."
