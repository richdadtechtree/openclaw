#!/usr/bin/env bash
#
# apply-env-refs.sh — openclaw.json 의 인라인 비밀값을 ${env} 참조로 교체
#
# 서버에서 실행하세요. openclaw.json 안의 실제 키 값을 지우고
# ${TELEGRAM_BOT_TOKEN_DEFAULT} 같은 참조로 바꿉니다.
# openclaw 가 ~/.openclaw/.env 를 자동 로드해 시작 시 치환합니다.
#
# 사용 순서:
#   1) scripts/setup-env.sh          # .env 채우기 (또는 extract-secrets-to-env.sh)
#   2) scripts/apply-env-refs.sh     # openclaw.json 을 참조로 교체  ← 이 스크립트
#   3) openclaw 재시작
#
# 필요 도구: jq
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="${OPENCLAW_CONF:-$REPO_DIR/openclaw.json}"

command -v jq >/dev/null 2>&1 || { echo "오류: jq 필요 (sudo apt install jq)" >&2; exit 1; }
[ -f "$CONF" ] || { echo "오류: $CONF 없음. OPENCLAW_CONF 로 지정하세요." >&2; exit 1; }

cp "$CONF" "$CONF.bak.$(date +%s)"
echo "[apply] 백업: $CONF.bak.*"

tmp="$(mktemp)"
jq '
  # 존재하는 필드만 참조 문자열로 교체
  (if .gateway.auth.token then .gateway.auth.token = "${GATEWAY_TOKEN}" else . end)
  | (if .plugins.entries.brave.config.webSearch.apiKey
       then .plugins.entries.brave.config.webSearch.apiKey = "${BRAVE_API_KEY}" else . end)
  | (if .channels.telegram.accounts.default.botToken
       then .channels.telegram.accounts.default.botToken = "${TELEGRAM_BOT_TOKEN_DEFAULT}" else . end)
  | (if .channels.telegram.accounts.pt.botToken
       then .channels.telegram.accounts.pt.botToken = "${TELEGRAM_BOT_TOKEN_PT}" else . end)
' "$CONF" > "$tmp"

# 유효한 JSON 인지 확인 후 교체
jq empty "$tmp" && mv "$tmp" "$CONF"

echo "[apply] 교체 완료. 현재 참조 상태:"
jq '{
  gateway_token: .gateway.auth.token,
  brave: .plugins.entries.brave.config.webSearch.apiKey,
  tg_default: .channels.telegram.accounts.default.botToken,
  tg_pt: .channels.telegram.accounts.pt.botToken
}' "$CONF"

echo
echo "참고: Gemini 키는 openclaw 가 GEMINI_API_KEY 환경변수를 직접 읽습니다"
echo "      (openclaw.json 에 인라인 필드가 없으면 .env 의 GEMINI_API_KEY 로 충분)."
echo "다음: openclaw 재시작 후 정상 동작 확인하세요."
