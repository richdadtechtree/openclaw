#!/usr/bin/env bash
#
# install-notebook-audio.sh — 오디오 만드는 프로그램(notebook_audio.py)을 'PDF 재료' 버전으로 교체 (멱등)
#
# 왜: 2026-11-13 사용자 요청 — 오디오를 요약 글이 아니라 신문 PDF 원본으로 만든다.
#     notebook_audio.py 는 리포가 아니라 서버(~/newspaper-claude)에만 있어서, 리포의 scripts/notebook_audio.py
#     (고친 전체 파일)를 그 자리에 복사한다. 옛 파일은 날짜 붙여 백업해 둔다(되돌리기: --revert).
#
# 사용:
#   scripts/install-notebook-audio.sh            # 교체
#   scripts/install-notebook-audio.sh --dry-run  # 무엇을 할지만 보기
#   scripts/install-notebook-audio.sh --revert   # 가장 최근 백업으로 되돌리기
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/notebook_audio.py"
DIR="${NEWSPAPER_CLAUDE_DIR:-$HOME/newspaper-claude}"
DST="$DIR/notebook_audio.py"
PY="$DIR/venv-nlm/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

mode="${1:-install}"
[ -d "$DIR" ] || { echo "폴더 없음: $DIR"; exit 1; }

if [ "$mode" = "--revert" ]; then
  last="$(ls -1t "$DST".bak-* 2>/dev/null | head -1 || true)"
  [ -n "$last" ] || { echo "백업이 없어요."; exit 1; }
  cp -p "$last" "$DST"; echo "되돌림: $last → $DST"; exit 0
fi

"$PY" -m py_compile "$SRC" && echo "문법 검사 통과: $SRC"
if [ -f "$DST" ] && cmp -s "$SRC" "$DST"; then echo "이미 같은 버전이에요. 할 일 없음."; exit 0; fi
if [ "$mode" = "--dry-run" ]; then echo "[dry-run] $SRC → $DST (옛 파일은 .bak-* 로 백업)"; exit 0; fi

[ -f "$DST" ] && cp -p "$DST" "$DST.bak-$(date +%Y%m%d%H%M%S)"
cp "$SRC" "$DST"; chmod +x "$DST"
"$PY" "$DST" --help | grep -q -- '--source' && echo "설치 완료: $DST (--source pdf|summary 지원)"
