#!/usr/bin/env bash
#
# patch-newspaper-keep-local.sh — 신문 수집기가 로컬 파일을 '오늘치만' 남기도록 바꾼다 (멱등)
#
# [배경]
#   ~/newspaper 수집기는 매일 05:30(cron) 에 네이버 카페에서 신문 사진을 받아
#   PDF 를 만들고 구글 드라이브에 올린 뒤, app/drive_uploader.py 의
#       shutil.rmtree(local_dir)
#   한 줄로 로컬 폴더를 통째로 지운다. (그래서 data 폴더엔 metadata.json 만 남아 있다)
#
#   다이제스트 웹(:8000 /slack)의 '오늘 신문 원본' 패널이 그 파일을 그대로 보여주려면
#   하루만 남아 있으면 된다. 구글 드라이브를 다시 거칠 이유가 없다(인증도 불필요).
#
# [무엇을 바꾸나]  그 한 줄만.
#   - 오늘치            : 사진·PDF 그대로 보관 → 웹이 읽는다
#   - 지난 날짜         : 사진·PDF 만 삭제, metadata.json 은 보존(지금까지의 기록 유지)
#   - 드라이브 업로드   : 손대지 않는다 → 백업 그대로
#
# [안전장치]
#   - 수정 전 자동 백업(drive_uploader.py.bak-<시각>)
#   - 문법 검사(py_compile) 실패 시 자동 원복
#   - 이미 적용돼 있으면 아무것도 안 함(멱등)
#   - --revert 로 되돌리기 / --dry-run 으로 미리보기
#
# 사용법:
#   ~/.openclaw/scripts/patch-newspaper-keep-local.sh            # 적용
#   ~/.openclaw/scripts/patch-newspaper-keep-local.sh --dry-run  # 미리보기
#   ~/.openclaw/scripts/patch-newspaper-keep-local.sh --revert   # 되돌리기
#
# 환경변수: NEWSPAPER_DIR (기본: ~/newspaper)
#
set -euo pipefail

NEWSPAPER_DIR="${NEWSPAPER_DIR:-$HOME/newspaper}"
TARGET="$NEWSPAPER_DIR/app/drive_uploader.py"
HELPER_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/newspaper_keep_local.py"
MARKER="_oc_keep_local_prune"
MODE="apply"
[ "${1:-}" = "--dry-run" ] && MODE="dry"
[ "${1:-}" = "--revert" ] && MODE="revert"

[ -f "$TARGET" ] || { echo "❌ 파일이 없습니다: $TARGET"; echo "   NEWSPAPER_DIR 로 경로를 지정하세요."; exit 1; }

# ── 되돌리기 ────────────────────────────────────────────────────────────────
if [ "$MODE" = "revert" ]; then
  LATEST="$(ls -1t "$TARGET".bak-* 2>/dev/null | head -1 || true)"
  [ -n "$LATEST" ] || { echo "❌ 백업이 없습니다."; exit 1; }
  cp "$TARGET" "$TARGET.before-revert.$(date +%s)"
  cp "$LATEST" "$TARGET"
  echo "✅ 되돌렸습니다: $LATEST → $TARGET"
  echo "   다음 실행부터 원래대로(업로드 후 전부 삭제) 동작합니다."
  exit 0
fi

[ -f "$HELPER_SRC" ] || { echo "❌ 삽입할 코드가 없습니다: $HELPER_SRC"; exit 1; }

# ── 이미 적용됐는지 ─────────────────────────────────────────────────────────
if grep -q "$MARKER" "$TARGET"; then
  echo "✅ 이미 적용돼 있습니다 (변경 없음): $TARGET"
  exit 0
fi

# ── 백업 ────────────────────────────────────────────────────────────────────
BACKUP="$TARGET.bak-$(date +%Y%m%d-%H%M%S)"
if [ "$MODE" = "apply" ]; then
  cp "$TARGET" "$BACKUP"
  echo "[1/4] 백업: $BACKUP"
else
  echo "[1/4] (미리보기) 백업 생략"
fi

# ── 수정 ────────────────────────────────────────────────────────────────────
echo "[2/4] 수정 대상 찾는 중: shutil.rmtree(local_dir)"
if ! OC_TARGET="$TARGET" OC_HELPER="$HELPER_SRC" OC_MODE="$MODE" python3 "$HELPER_SRC" --patch; then
  rc=$?
  echo "중단합니다(rc=$rc)."
  [ "$MODE" = "apply" ] && cp "$BACKUP" "$TARGET" && echo "원복했습니다."
  exit "$rc"
fi

if [ "$MODE" = "dry" ]; then
  echo "[3/4] (미리보기) 문법 검사 생략"
  echo "[4/4] 미리보기 끝 — 실제로 적용하려면 옵션 없이 다시 실행하세요."
  exit 0
fi

# ── 문법 검사 (실패하면 즉시 원복) ──────────────────────────────────────────
echo "[3/4] 문법 검사"
PYBIN="$NEWSPAPER_DIR/.venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="python3"
if ! "$PYBIN" -m py_compile "$TARGET" 2>/tmp/oc-newspaper-patch.err; then
  echo "❌ 문법 오류 — 원래 파일로 되돌립니다."
  sed -n 1,20p /tmp/oc-newspaper-patch.err
  cp "$BACKUP" "$TARGET"
  exit 1
fi
echo "   통과"

echo "[4/4] 완료"
echo
echo "다음 수집(내일 05:30 cron)부터 오늘치 신문이 서버에 남습니다."
echo "지금 바로 확인하려면 수집기를 한 번 수동 실행하세요:"
echo "  cd $NEWSPAPER_DIR && ./scripts/run_daily.sh"
echo
echo "되돌리기:      $0 --revert"
echo "보관 일수 조절: ~/newspaper/.env 에  NEWSPAPER_KEEP_DAYS=2   (기본 1 = 오늘치만)"
