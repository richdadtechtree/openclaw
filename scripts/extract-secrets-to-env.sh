#!/usr/bin/env bash
#
# extract-secrets-to-env.sh — 서버의 live openclaw.json 에서 키를 뽑아 .env 생성
#
# 서버에서 실행하세요. live 설정(openclaw.json)의 실제 키 값을 읽어
# 리포 루트에 .env 를 만듭니다. (.env 는 .gitignore 로 git 에 올라가지 않음)
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

if ! command -v jq >/dev/null 2>&1; then
  echo "오류: jq 가 필요합니다. (sudo apt install jq)" >&2
  exit 1
fi
if [ ! -f "$CONF" ]; then
  echo "오류: 설정 파일을 찾을 수 없습니다: $CONF" >&2
  echo "  OPENCLAW_CONF=/경로/openclaw.json 로 지정하세요." >&2
  exit 1
fi

# 기존 .env 백업
if [ -f "$ENV_FILE" ]; then
  cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
  echo "[extract] 기존 .env 백업함"
fi

brave="$(jq -r '.plugins.entries.brave.config.webSearch.apiKey // .tools.web.search.apiKey // empty' "$CONF")"
gwtoken="$(jq -r '.gateway.auth.token // empty' "$CONF")"

{
  echo "# openclaw 비밀 키 (자동 생성: $(date '+%F %T'))"
  echo "# 이 파일은 .gitignore 로 git 에 올라가지 않습니다."
  echo
  echo "BRAVE_API_KEY=${brave}"
  echo "GATEWAY_TOKEN=${gwtoken}"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "[extract] .env 생성 완료: $ENV_FILE (권한 600)"
echo "[extract] 담긴 키:"
echo "  BRAVE_API_KEY = ${brave:0:6}… (${#brave} chars)"
echo "  GATEWAY_TOKEN = ${gwtoken:0:6}… (${#gwtoken} chars)"
echo
echo "다음 단계: openclaw 서비스가 .env 를 읽도록 설정하세요."
echo "  - systemd 유닛에  EnvironmentFile=$ENV_FILE  추가"
echo "  - 또는 실행 전  set -a; . $ENV_FILE; set +a"
echo "그리고 openclaw.json 의 인라인 키를 env 참조로 바꾸세요:"
echo "  - Brave:   plugins.entries.brave.config.webSearch.apiKey 삭제 → BRAVE_API_KEY env 사용"
echo "  - Gateway: --gateway-token-ref-env GATEWAY_TOKEN 로 기동"
