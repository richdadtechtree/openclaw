#!/usr/bin/env bash
#
# setup-env.sh — 키를 하나씩 물어보고 .env 에 저장하는 대화식 마법사
#
# 사용법:
#   scripts/setup-env.sh
#
# - 각 키마다 "어디서 받는지" 안내하고 입력을 받습니다.
# - 그냥 엔터를 치면 기존 값을 그대로 둡니다.
# - 게이트웨이 토큰은 엔터만 치면 자동 생성합니다.
# - 결과는 리포 루트 .env 에 권한 600 으로 저장됩니다. (git 제외)
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"

# 기존 .env 값 읽기 (있으면)
declare -A cur
if [ -f "$ENV_FILE" ]; then
  while IFS='=' read -r k v; do
    [[ "$k" =~ ^[A-Z_]+$ ]] && cur[$k]="$v"
  done < "$ENV_FILE"
fi

ask() {  # ask VAR "설명" "발급처"
  local var="$1" desc="$2" where="$3" existing="${cur[$1]:-}" input
  echo
  echo "▶ $desc"
  echo "   발급처: $where"
  if [ -n "$existing" ]; then
    echo "   (현재 값 있음: ${existing:0:6}…  — 그대로 두려면 엔터)"
  fi
  read -r -p "   값 입력: " input || true
  if [ -n "$input" ]; then
    cur[$var]="$input"
  fi
}

echo "=== openclaw .env 설정 마법사 ==="
echo "각 키를 하나씩 입력하세요. 모르면 엔터로 건너뛰고 나중에 다시 실행해도 됩니다."

ask TELEGRAM_BOT_TOKEN_DEFAULT "1) 텔레그램 봇토큰 (신문 분석가/기본 봇)" "@BotFather → /mybots → 봇 선택 → API Token"
ask TELEGRAM_BOT_TOKEN_PT      "2) 텔레그램 봇토큰 (PT 트레이너 봇)"     "@BotFather → /mybots → PT 봇 → API Token"
ask BRAVE_API_KEY              "3) Brave 웹검색 API 키"                  "https://api-dashboard.search.brave.com/ → API Keys"
ask SLACK_APP_TOKEN            "3-1) Slack 앱 토큰 (xapp-)"              "https://api.slack.com/apps → 앱 → Basic Information → App-Level Tokens"
ask SLACK_BOT_TOKEN            "3-2) Slack 봇 토큰 (xoxb-)"              "같은 앱 → OAuth & Permissions → Bot User OAuth Token"
ask GEMINI_API_KEY             "4) Gemini(Google) API 키"               "https://aistudio.google.com/apikey → Create API key"

# 게이트웨이 토큰: 엔터 시 자동 생성
echo
echo "▶ 5) 게이트웨이 인증 토큰"
echo "   아무 랜덤 문자열. 엔터만 치면 자동 생성합니다."
if [ -n "${cur[GATEWAY_TOKEN]:-}" ]; then
  echo "   (현재 값 있음: ${cur[GATEWAY_TOKEN]:0:6}…  — 그대로 두려면 엔터)"
fi
read -r -p "   값 입력(엔터=자동생성): " gw || true
if [ -n "$gw" ]; then
  cur[GATEWAY_TOKEN]="$gw"
elif [ -z "${cur[GATEWAY_TOKEN]:-}" ]; then
  cur[GATEWAY_TOKEN]="$(openssl rand -hex 24 2>/dev/null || head -c24 /dev/urandom | xxd -p)"
  echo "   → 자동 생성함"
fi

# 저장 (기존 .env 백업)
[ -f "$ENV_FILE" ] && cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
{
  echo "# openclaw 비밀 키 (setup-env.sh 로 저장: $(date '+%F %T'))"
  echo "# .gitignore 로 git 에 올라가지 않음"
  echo
  for var in TELEGRAM_BOT_TOKEN_DEFAULT TELEGRAM_BOT_TOKEN_PT BRAVE_API_KEY SLACK_APP_TOKEN SLACK_BOT_TOKEN GEMINI_API_KEY GATEWAY_TOKEN; do
    echo "${var}=${cur[$var]:-}"
  done
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo
echo "=== 저장 완료: $ENV_FILE (권한 600) ==="
for var in TELEGRAM_BOT_TOKEN_DEFAULT TELEGRAM_BOT_TOKEN_PT BRAVE_API_KEY SLACK_APP_TOKEN SLACK_BOT_TOKEN GEMINI_API_KEY GATEWAY_TOKEN; do
  v="${cur[$var]:-}"
  if [ -n "$v" ]; then echo "  ✓ $var = ${v:0:6}… (${#v}자)"; else echo "  ✗ $var  (비어있음)"; fi
done
echo
echo "다음 단계: openclaw.json 을 \${변수명} 참조로 바꾸세요."
echo "  자동으로 바꾸려면:  scripts/apply-env-refs.sh"
