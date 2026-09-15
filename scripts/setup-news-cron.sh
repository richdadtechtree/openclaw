#!/usr/bin/env bash
#
# setup-news-cron.sh — '그날 신문'(사진·PDF) 드라이브 → 서버 캐시 동기화를 cron 에 등록 (멱등)
#
# 무엇을 하나:
#   scripts/news_sync.py 를 주기적으로 돌려, 구글 드라이브 '신문스크랩' 폴더의
#   그날 PDF·사진을 ~/.openclaw/news_cache/<날짜>/ 로 내려받아 둔다.
#   다이제스트 웹(포트 8000, /slack)의 '오늘 신문 원본' 패널이 이 캐시를 읽는다.
#
# 왜 30분마다인가:
#   신문은 보통 06:01(KST)에 드라이브에 올라오지만, 늦어질 수도 있고 서버 시간대가
#   UTC 일 수도 있다. 이미 받아둔 파일은 건너뛰므로(목록만 한 번 확인) 자주 돌려도
#   부담이 거의 없다. 시간대 계산으로 헤매느니 자주 확인하는 쪽이 안전하다.
#
# 사용법 (서버에서):
#   ~/.openclaw/scripts/setup-news-cron.sh
#
# 환경변수로 조정:
#   NEWS_SCHEDULE   cron 스케줄 (기본: "*/30 * * * *")
#   NEWS_PY         파이썬 실행기 (기본: python3 — 외부 라이브러리가 필요 없다)
#   GOG_BIN         gog 실행파일 (기본: /home/linuxbrew/.linuxbrew/bin/gog)
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYNC_SCRIPT="$REPO_DIR/scripts/news_sync.py"
SCHEDULE="${NEWS_SCHEDULE:-*/30 * * * *}"
PY="${NEWS_PY:-python3}"
GOG="${GOG_BIN:-/home/linuxbrew/.linuxbrew/bin/gog}"
LOGFILE="$REPO_DIR/scripts/news-sync.log"

[ -f "$SYNC_SCRIPT" ] || { echo "[setup] 스크립트가 없습니다: $SYNC_SCRIPT"; exit 1; }
chmod +x "$SYNC_SCRIPT"

# cron 은 환경이 거의 비어 있다.
#  - PATH: python3 / gog 를 찾을 수 있게
#  - XDG_RUNTIME_DIR: news_sync.py 가 `systemctl --user` 로 게이트웨이의 gog 환경변수를
#    빌려올 때 필요(= gog keyring 잠금 해제)
UID_NUM="$(id -u)"
CRON_PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin"

TAG="# openclaw-news-sync"
CRON_LINE="$SCHEDULE PATH='$CRON_PATH' XDG_RUNTIME_DIR='/run/user/$UID_NUM' GOG_BIN='$GOG' $PY '$SYNC_SCRIPT' --quiet >> '$LOGFILE' 2>&1 $TAG"

current="$(crontab -l 2>/dev/null || true)"
filtered="$(printf '%s\n' "$current" | grep -vF "$TAG" || true)"
{
  printf '%s\n' "$filtered" | sed '/^$/d'
  printf '%s\n' "$CRON_LINE"
} | crontab -

echo "[setup] crontab 등록 완료:"
echo "  $CRON_LINE"
echo
echo "[setup] 확인:  crontab -l"
echo "[setup] 로그:  $LOGFILE"
echo
echo "지금 바로 한 번 받아보려면:"
echo "  GOG_BIN='$GOG' $PY '$SYNC_SCRIPT'"
echo "gog 사용법이 예상과 다르면(목록 조회 실패 메시지가 나오면):"
echo "  $PY '$SYNC_SCRIPT' --probe"
