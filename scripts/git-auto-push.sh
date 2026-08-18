#!/usr/bin/env bash
#
# git-auto-push.sh — 설정/콘텐츠 수정 후 자동 커밋 & 푸시
#
# 클로드(Claude) 세션이나 로컬에서 SOUL.md, jobs.json, 프롬프트 등을
# 수정한 뒤 이 스크립트를 실행하면 변경분을 커밋하고 원격에 푸시합니다.
# .gitignore 로 런타임/세션/백업 파일은 자동 제외되므로 설정만 올라갑니다.
#
# 사용법:
#   scripts/git-auto-push.sh                 # 자동 커밋 메시지
#   scripts/git-auto-push.sh "메시지"        # 커밋 메시지 직접 지정
#
# 환경변수:
#   OPENCLAW_GIT_BRANCH  푸시할 브랜치 (기본: 현재 체크아웃된 브랜치)
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

BRANCH="${OPENCLAW_GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
MSG="${1:-chore: 설정 자동 동기화 $(date '+%Y-%m-%d %H:%M:%S %Z')}"

# 변경 사항이 없으면 종료 (추적 파일 수정 + 새 추적 대상 파일 모두 확인)
if git diff --quiet && git diff --cached --quiet && \
   [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "[auto-push] 변경 사항 없음. 종료."
  exit 0
fi

git add -A
git commit -m "$MSG"
echo "[auto-push] 커밋 완료: $MSG"

# 네트워크 오류 시 지수 백오프 재시도 (2s, 4s, 8s, 16s)
delay=2
for attempt in 1 2 3 4 5; do
  if git push -u origin "$BRANCH"; then
    echo "[auto-push] 푸시 완료 → origin/$BRANCH"
    exit 0
  fi
  if [ "$attempt" -eq 5 ]; then break; fi
  echo "[auto-push] 푸시 실패, ${delay}s 후 재시도... ($attempt/4)"
  sleep "$delay"
  delay=$((delay * 2))
done

echo "[auto-push] 푸시 실패 (재시도 초과)" >&2
exit 1
