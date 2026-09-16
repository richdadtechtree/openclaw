#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
newspaper_title_filter.py — 수집기가 '신문스크랩 글'만 집도록 하는 코드 + 그 코드를 심는 도구.

[왜]
  app/naver_cafe.py 는 카페 글 목록에서 이렇게 고른다.
      is_match = bool(date_pattern.search(title))     # 제목에 오늘 날짜가 있으면 OK
  날짜만 보기 때문에, 같은 날짜로 시작하는 다른 글(예: "26.9.16 미모")이 위에 올라오면
  그걸 집어버린다. 2026-09-16 저녁에 실제로 발생 — 신문 30장 대신 엉뚱한 6장을 받아
  드라이브 폴더까지 덮어썼다.

[무엇을 바꾸나]  그 한 줄에 조건 하나를 더한다.
      is_match = bool(date_pattern.search(title)) and _oc_title_ok(title)
  - NEWSPAPER_TITLE_KEYWORD (기본 "신문스크랩") 가 제목에 있어야 통과
  - NEWSPAPER_TITLE_EXCLUDE (쉼표 구분, 선택) 에 걸리면 제외
  - 공백은 무시하고 비교("신문 스크랩" 도 통과)

[덤]
  신문 글이 아직 안 올라왔으면 '못 찾음 = 실패' 가 되어, run_daily.sh 의 재시도 루프가
  5분 뒤 다시 확인한다. 즉 '늦게 올라오는 날'도 저절로 처리된다.

혼자 쓸 일은 없다. `scripts/patch-newspaper-title-filter.sh` 가 백업·검증·원복까지 해준다.
"""

import os
import re
import sys

BEGIN_MARK = "# === OPENCLAW-TITLE-FILTER BEGIN ==="
END_MARK = "# === OPENCLAW-TITLE-FILTER END ==="

OLD_LINE = re.compile(r"^([ \t]*)is_match = bool\(date_pattern\.search\(title\)\)[ \t]*$", re.M)


# === OPENCLAW-TITLE-FILTER BEGIN ===
# ─────────────────────────────────────────────────────────────────────────────
# [openclaw 패치] 어떤 글을 '오늘 신문'으로 볼지 거르는 조건
#
# 원래는 제목에 오늘 날짜만 있으면 통과라서, 같은 날짜로 시작하는 다른 글
# (예: "26.9.16 미모")이 목록 위에 올라오면 그걸 집어왔다.
#
#   NEWSPAPER_TITLE_KEYWORD  제목에 반드시 있어야 할 말 (기본: 신문스크랩)
#                            빈 값으로 두면 이 조건을 끈다(= 예전 동작)
#   NEWSPAPER_TITLE_EXCLUDE  제외할 말들, 쉼표 구분 (선택)
#
# 조절은 ~/newspaper/.env 에서. 되돌리기:
#   ~/.openclaw/scripts/patch-newspaper-title-filter.sh --revert
# ─────────────────────────────────────────────────────────────────────────────
def _oc_title_ok(title: str) -> bool:
    import os

    squash = lambda s: (s or "").replace(" ", "").replace("\t", "")
    t = squash(title)

    for bad in os.getenv("NEWSPAPER_TITLE_EXCLUDE", "").split(","):
        if bad.strip() and squash(bad) in t:
            try:
                logger.info("[filter] 제외어 '%s' 때문에 건너뜀: %s" % (bad.strip(), title))
            except Exception:
                pass
            return False

    keyword = os.getenv("NEWSPAPER_TITLE_KEYWORD", "신문스크랩").strip()
    if not keyword:
        return True                       # 조건 끔 → 예전처럼 날짜만 본다

    if squash(keyword) in t:
        return True

    try:
        logger.info("[filter] 제목에 '%s' 가 없어 건너뜀: %s" % (keyword, title))
    except Exception:
        pass
    return False
# === OPENCLAW-TITLE-FILTER END ===


def helper_source():
    """자기 소스에서 마커 사이의 '심을 코드'만 떼어낸다(줄 맨 앞 마커만 인정)."""
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    b = re.search(r"^" + re.escape(BEGIN_MARK) + r"$", src, re.M)
    e = re.search(r"^" + re.escape(END_MARK) + r"$", src, re.M)
    if not b or not e or e.start() < b.end():
        raise RuntimeError("심을 코드 구간(마커)을 찾지 못했습니다.")
    return src[b.end():e.start()].strip("\n")


def patch():
    target = os.environ["OC_TARGET"]
    dry = os.environ.get("OC_MODE") == "dry"
    src = open(target, encoding="utf-8").read()

    found = OLD_LINE.findall(src)
    if len(found) != 1:
        print("❌ 'is_match = bool(date_pattern.search(title))' 줄을 정확히 1개 찾지 못했습니다 "
              "(찾은 개수: %d)." % len(found))
        print("   파일이 이미 바뀌었을 수 있습니다. 수동 확인이 필요합니다: %s" % target)
        return 2

    indent = found[0]
    new_line = (indent + "is_match = bool(date_pattern.search(title)) and _oc_title_ok(title)"
                "   # [openclaw] 날짜만 맞는 다른 글을 집지 않도록 제목 조건 추가")

    if dry:
        print("─── 바뀔 줄 ───")
        print("  - %sis_match = bool(date_pattern.search(title))" % indent)
        print("  + %s" % new_line.strip())
        print("─── 그리고 파일 끝에 _oc_title_ok() 함수 추가 (약 45줄) ───")
        return 0

    patched = OLD_LINE.sub(lambda _m: new_line, src, count=1)
    patched = patched.rstrip("\n") + "\n\n\n" + helper_source() + "\n"
    open(target, "w", encoding="utf-8").write(patched)
    print("   수정 완료")
    return 0


if __name__ == "__main__":
    if "--patch" in sys.argv:
        sys.exit(patch())
    if "--show" in sys.argv:
        print(helper_source())
        sys.exit(0)
    if "--selftest" in sys.argv:
        # 심을 함수를 여기서 바로 시험해 본다(실제 코드 그대로라 믿을 수 있다)
        os.environ.pop("NEWSPAPER_TITLE_KEYWORD", None)
        cases = [("26.9.16 신문스크랩", True), ("26.9.16 미모", False),
                 ("26.9.16 신문 스크랩", True), ("26.9.15 신문스크랩(수정)", True)]
        ok = all(_oc_title_ok(t) is want for t, want in cases)
        for t, want in cases:
            print("  %-24s → %-5s (기대 %s)" % (t, _oc_title_ok(t), want))
        os.environ["NEWSPAPER_TITLE_KEYWORD"] = ""
        print("  키워드 끄면 전부 통과:", _oc_title_ok("26.9.16 미모") is True)
        os.environ["NEWSPAPER_TITLE_KEYWORD"] = "신문스크랩"
        os.environ["NEWSPAPER_TITLE_EXCLUDE"] = "테스트,공지"
        print("  제외어 동작:", _oc_title_ok("26.9.16 신문스크랩 공지") is False)
        sys.exit(0 if ok else 1)
    print(__doc__)
