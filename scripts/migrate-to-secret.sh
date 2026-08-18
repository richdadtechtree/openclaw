#!/usr/bin/env bash
# =============================================================================
# migrate-to-secret.sh — secret/ 폴더로 민감 파일 이동 (서버에서 한 번만 실행)
# =============================================================================
#
# 목적:
#   기존에 ~/.openclaw/ 루트에 흩어져 있던 민감 파일/폴더를
#   secret/ 폴더로 이동해서 한곳에서 관리한다.
#   이후 git pull/push는 secret/ 을 건드리지 않는다.
#
# 사용법:
#   cd ~/.openclaw
#   bash scripts/migrate-to-secret.sh
#
# 안전:
#   - 실제로 이동하기 전에 대상 목록만 출력하는 dry-run 모드가 기본이다.
#   - 실제 이동하려면:  bash scripts/migrate-to-secret.sh --run
#
# =============================================================================
set -euo pipefail

OPENCLAW="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRET="$OPENCLAW/secret"
DRY_RUN=true

if [[ "${1:-}" == "--run" ]]; then
  DRY_RUN=false
fi

echo "=========================================="
echo " OpenClaw secret/ 마이그레이션"
echo " OPENCLAW = $OPENCLAW"
echo " SECRET   = $SECRET"
[[ "$DRY_RUN" == true ]] && echo " 모드: DRY-RUN (실제 이동 없음)" || echo " 모드: 실행"
echo "=========================================="

mkdir -p "$SECRET"

move_item() {
  local src="$OPENCLAW/$1"
  local dst="$SECRET/$2"
  if [[ -e "$src" || -d "$src" ]]; then
    echo "  [MOVE] $1  →  secret/$2"
    if [[ "$DRY_RUN" == false ]]; then
      mv "$src" "$dst"
      echo "         ✅ 완료"
    fi
  else
    echo "  [SKIP] $1  (없음)"
  fi
}

echo ""
echo "── 이동 대상 파일/폴더 ──────────────────────────────────"

# 인증/기기 정보
move_item "credentials"       "credentials"
move_item "identity"          "identity"
move_item "devices"           "devices"

# Google OAuth 클라이언트 시크릿 (파일명 패턴으로 탐색)
for f in "$OPENCLAW"/client_secret_*.json; do
  [[ -f "$f" ]] || continue
  fname="$(basename "$f")"
  echo "  [MOVE] $fname  →  secret/$fname"
  if [[ "$DRY_RUN" == false ]]; then
    mv "$f" "$SECRET/$fname"
    echo "         ✅ 완료"
  fi
done

# systemd 환경변수 파일
move_item "gateway.systemd.env" "gateway.systemd.env"

echo ""
if [[ "$DRY_RUN" == true ]]; then
  echo "── DRY-RUN 완료. 실제로 이동하려면: bash scripts/migrate-to-secret.sh --run"
else
  echo "── 마이그레이션 완료."
  echo "   이제 secret/ 폴더를 확인하세요: ls -la $SECRET"
  echo ""
  echo "   서버에서 openclaw 를 재시작하면 새 경로를 인식합니다."
  echo "   (openclaw가 credentials/, identity/ 를 직접 참조하는 경우"
  echo "    openclaw.json 경로 설정 확인 필요)"
fi
