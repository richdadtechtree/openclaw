#!/usr/bin/env bash
#
# patch-newspaper-title-filter.sh — 수집기가 '신문스크랩 글'만 집도록 고친다 (멱등)
#
# [배경] 2026-09-16 저녁 사고
#   app/naver_cafe.py 는 제목에 오늘 날짜만 있으면 그 글을 집었다.
#       is_match = bool(date_pattern.search(title))
#   그래서 "26.9.16 미모"(사진 6장)를 신문(30장)으로 착각해 받아오고,
#   드라이브의 오늘 폴더까지 덮어썼다.
#
# [무엇을 바꾸나]  그 한 줄에 제목 조건을 더한다.
#       ... and _oc_title_ok(title)
#   NEWSPAPER_TITLE_KEYWORD(기본 "신문스크랩") 가 제목에 있어야 통과.
#
# [덤] 신문 글이 아직 안 올라온 시각이면 '못 찾음=실패' 가 되어
#      run_daily.sh 의 5분 간격 재시도가 돈다 → 늦게 올라오는 날도 자동 처리.
#
# [안전장치] 백업 → 수정 → 문법검사(py_compile) → 실패 시 자동 원복. --dry-run / --revert.
#
# 사용법:
#   ~/.openclaw/scripts/patch-newspaper-title-filter.sh --dry-run
#   ~/.openclaw/scripts/patch-newspaper-title-filter.sh
#   ~/.openclaw/scripts/patch-newspaper-title-filter.sh --revert
#
set -euo pipefail

NEWSPAPER_DIR="${NEWSPAPER_DIR:-$HOME/newspaper}"
TARGET="$NEWSPAPER_DIR/app/naver_cafe.py"
HELPER_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/newspaper_title_filter.py"
MARKER="_oc_title_ok"
MODE="apply"
[ "${1:-}" = "--dry-run" ] && MODE="dry"
[ "${1:-}" = "--revert" ] && MODE="revert"

[ -f "$TARGET" ] || { echo "❌ 파일이 없습니다: $TARGET"; exit 1; }

if [ "$MODE" = "revert" ]; then
  LATEST="$(ls -1t "$TARGET".bak-* 2>/dev/null | head -1 || true)"
  [ -n "$LATEST" ] || { echo "❌ 백업이 없습니다."; exit 1; }
  cp "$TARGET" "$TARGET.before-revert.$(date +%s)"
  cp "$LATEST" "$TARGET"
  echo "✅ 되돌렸습니다: $LATEST → $TARGET"
  exit 0
fi

[ -f "$HELPER_SRC" ] || { echo "❌ 삽입할 코드가 없습니다: $HELPER_SRC"; exit 1; }

if grep -q "$MARKER" "$TARGET"; then
  echo "✅ 이미 적용돼 있습니다 (변경 없음): $TARGET"
  exit 0
fi

BACKUP="$TARGET.bak-$(date +%Y%m%d-%H%M%S)"
if [ "$MODE" = "apply" ]; then
  cp "$TARGET" "$BACKUP"
  echo "[1/4] 백업: $BACKUP"
else
  echo "[1/4] (미리보기) 백업 생략"
fi

echo "[2/4] 수정 대상 찾는 중: is_match = bool(date_pattern.search(title))"
if ! OC_TARGET="$TARGET" OC_MODE="$MODE" python3 "$HELPER_SRC" --patch; then
  rc=$?
  echo "중단합니다(rc=$rc)."
  [ "$MODE" = "apply" ] && cp "$BACKUP" "$TARGET" && echo "원복했습니다."
  exit "$rc"
fi

if [ "$MODE" = "dry" ]; then
  echo "[3/4] (미리보기) 문법 검사 생략"
  echo "[4/4] 미리보기 끝 — 적용하려면 옵션 없이 다시 실행하세요."
  exit 0
fi

echo "[3/4] 문법 검사"
PYBIN="$NEWSPAPER_DIR/.venv/bin/python"
[ -x "$PYBIN" ] || PYBIN="python3"
if ! "$PYBIN" -m py_compile "$TARGET" 2>/tmp/oc-title-filter.err; then
  echo "❌ 문법 오류 — 원래 파일로 되돌립니다."
  sed -n 1,20p /tmp/oc-title-filter.err
  cp "$BACKUP" "$TARGET"
  exit 1
fi
echo "   통과"

echo "[4/4] 완료"
echo
echo "이제 제목에 '신문스크랩' 이 있는 글만 집습니다."
echo "다른 말로 바꾸려면 ~/newspaper/.env 에:"
echo "  NEWSPAPER_TITLE_KEYWORD=신문스크랩      # 반드시 포함돼야 할 말 (빈 값이면 조건 끔)"
echo "  NEWSPAPER_TITLE_EXCLUDE=공지,테스트      # 제외할 말 (선택)"
echo
echo "되돌리기: $0 --revert"
