#!/usr/bin/env bash
#
# set-newspaper-schedule.sh — 신문 수집 시작 시각을 바꾼다 (멱등)
#
# [배경]
#   cron 이 05:30 에 run_daily.sh 를 부르는데, 그 시각엔 카페에 신문 글이
#   아직 안 올라온 날이 있다. 시작을 05:00 으로 당긴다.
#
#   run_daily.sh 는 원래부터 '성공할 때까지 5분 간격 재시도, 07:00 지나면 포기'
#   구조다. 그래서 시작 시각만 바꾸면 **05:00~07:00 사이 5분마다 확인**이 된다.
#   (제목 필터 패치와 같이 쓰면 '신문 글이 아직 없음 = 실패 → 재시도' 가 되어
#    늦게 올라오는 날도 저절로 따라간다.)
#
# 사용법:
#   ~/.openclaw/scripts/set-newspaper-schedule.sh            # 05:00 시작
#   ~/.openclaw/scripts/set-newspaper-schedule.sh "10 4"     # 04:10 시작 (분 시)
#
# 확인: crontab -l | grep run_daily
#
set -euo pipefail

SCHEDULE="${1:-0 5}"            # "분 시"
MARK="newspaper/scripts/run_daily.sh"

current="$(crontab -l 2>/dev/null || true)"
if ! printf '%s\n' "$current" | grep -qF "$MARK"; then
  echo "❌ crontab 에서 run_daily.sh 줄을 찾지 못했습니다. 수동으로 확인하세요: crontab -l"
  exit 1
fi

before="$(printf '%s\n' "$current" | grep -F "$MARK" | head -1)"
# 앞의 5칸(분 시 일 월 요일)만 갈아끼우고 나머지 명령은 그대로 둔다.
updated="$(printf '%s\n' "$current" | awk -v sched="$SCHEDULE" -v mark="$MARK" '
  index($0, mark) > 0 && $0 !~ /^[[:space:]]*#/ {
    rest = $0
    for (i = 1; i <= 5; i++) { sub(/^[[:space:]]*[^[:space:]]+/, "", rest) }
    print sched " * * *" rest
    next
  }
  { print }
')"

printf '%s\n' "$updated" | crontab -

echo "✅ 신문 수집 시작 시각 변경"
echo "  전: $before"
echo "  후: $(crontab -l | grep -F "$MARK" | head -1)"
echo
echo "run_daily.sh 는 성공할 때까지 5분 간격으로 재시도하고 07:00 을 넘기면 포기합니다."
echo "→ 실제 동작: ${SCHEDULE#* }:${SCHEDULE%% *} 부터 07:00 까지 5분마다 확인"
echo "재시도 간격·마감 시각은 ~/newspaper/scripts/run_daily.sh 의 INTERVAL_SECONDS / CUTOFF."
