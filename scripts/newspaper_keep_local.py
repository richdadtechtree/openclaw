#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
newspaper_keep_local.py — 신문 수집기가 '오늘치 파일'을 서버에 남기게 하는 코드 + 그 코드를 심는 도구.

[왜]
  ~/newspaper 수집기는 드라이브 업로드가 끝나면 app/drive_uploader.py 의
      shutil.rmtree(local_dir)
  한 줄로 그날 폴더를 통째로 지운다. 그래서 다이제스트 웹이 보여줄 파일이 남지 않는다.
  파일은 서버에서 만들어지므로, 하루만 남겨두면 구글을 거칠 필요가 전혀 없다.

[이 파일의 두 얼굴]
  1) 아래 마커 사이의 함수(_oc_keep_local_prune)가 수집기에 심을 '진짜 코드'다.
     → 여기서 직접 테스트할 수 있다(그래서 문자열이 아니라 실제 코드로 둔다).
  2) `python3 newspaper_keep_local.py --patch` 로 실행하면, 그 함수를 자기 소스에서
     떼어내 대상 파일에 심는다. (실제 호출은 patch-newspaper-keep-local.sh 가 한다)

혼자 쓸 일은 없다. `scripts/patch-newspaper-keep-local.sh` 를 쓰면 백업·문법검사·원복까지 해준다.
"""

import os
import re
import sys

BEGIN = "# === OPENCLAW-KEEP-LOCAL BEGIN ==="
END = "# === OPENCLAW-KEEP-LOCAL END ==="


# === OPENCLAW-KEEP-LOCAL BEGIN ===
# ─────────────────────────────────────────────────────────────────────────────
# [openclaw 패치] 업로드 후 로컬 파일 보관 정책
#
# 원래는 업로드가 끝나면 shutil.rmtree(local_dir) 로 그날 폴더를 통째로 지웠다.
# 다이제스트 웹(:8000 /slack)의 '오늘 신문 원본' 패널이 이 파일을 직접 읽으므로
# 오늘치는 남기고 지난 날짜만 정리한다.
#
#   - 오늘(기본 1일)치 : 사진·PDF 보관        → 웹이 읽는다
#   - 지난 날짜        : 사진·PDF 만 삭제, metadata.json 은 보존(기존 기록 그대로)
#   - 드라이브 업로드  : 이 함수 이전 단계라 전혀 영향 없음(백업 유지)
#
# 보관 일수: 환경변수 NEWSPAPER_KEEP_DAYS (기본 1 = 오늘치만)
# 되돌리기: ~/.openclaw/scripts/patch-newspaper-keep-local.sh --revert
# ─────────────────────────────────────────────────────────────────────────────
def _oc_keep_local_prune(local_dir: str) -> None:
    import os
    import re
    import shutil
    from datetime import date, timedelta

    try:
        keep_days = max(1, int(os.getenv("NEWSPAPER_KEEP_DAYS", "1")))
    except ValueError:
        keep_days = 1

    # local_dir = .../data/newspapers/<YYYY-MM>/<YYYY-MM-DD>  →  root = .../newspapers
    root = os.path.dirname(os.path.dirname(os.path.abspath(local_dir)))
    if not os.path.isdir(root):
        return

    cutoff = date.today() - timedelta(days=keep_days - 1)   # 이 날짜부터는 남긴다
    removed = 0

    for month in sorted(os.listdir(root)):
        month_dir = os.path.join(root, month)
        if not os.path.isdir(month_dir):
            continue
        for day in sorted(os.listdir(month_dir)):
            day_dir = os.path.join(month_dir, day)
            m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", day)
            if not m or not os.path.isdir(day_dir):
                continue
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if d >= cutoff:
                continue                      # 보관 기간 안 → 그대로 둔다

            for name in os.listdir(day_dir):
                if name == "metadata.json":   # 기록은 남긴다(기존 동작 유지)
                    continue
                path = os.path.join(day_dir, name)
                try:
                    if os.path.isdir(path) and not os.path.islink(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    removed += 1
                except OSError:
                    pass

    print("[cleanup] 로컬 보관 %d일 · 지난 날짜 파일 %d개 정리" % (keep_days, removed))
# === OPENCLAW-KEEP-LOCAL END ===


def helper_source():
    """
    자기 소스에서 마커 사이의 '심을 코드'만 떼어낸다.
    ⚠️ 줄 맨 앞에 오는 마커만 찾는다. 그냥 문자열로 찾으면 이 파일 위쪽의
       BEGIN = "..." 상수 줄이 먼저 걸려서 엉뚱한 데를 자른다(실제로 겪음).
    """
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    b = re.search(r"^" + re.escape(BEGIN) + r"$", src, re.M)
    e = re.search(r"^" + re.escape(END) + r"$", src, re.M)
    if not b or not e or e.start() < b.end():
        raise RuntimeError("심을 코드 구간(마커)을 찾지 못했습니다.")
    return src[b.end():e.start()].strip("\n")


def patch():
    target = os.environ["OC_TARGET"]
    dry = os.environ.get("OC_MODE") == "dry"
    src = open(target, encoding="utf-8").read()

    # 지우는 줄은 딱 하나여야 한다. 0개거나 2개 이상이면 추측하지 않고 멈춘다.
    pat = re.compile(r"^([ \t]*)shutil\.rmtree\(local_dir\)[ \t]*$", re.M)
    found = pat.findall(src)
    if len(found) != 1:
        print("❌ 'shutil.rmtree(local_dir)' 줄을 정확히 1개 찾지 못했습니다 (찾은 개수: %d)." % len(found))
        print("   파일이 이미 바뀌었을 수 있습니다. 수동 확인이 필요합니다: %s" % target)
        return 2

    indent = found[0]
    new_line = (indent + "_oc_keep_local_prune(local_dir)"
                "   # [openclaw] 오늘치는 남기고 지난 날짜만 정리 (웹 '오늘 신문 원본'이 읽는다)")

    if dry:
        print("─── 바뀔 줄 ───")
        print("  - %sshutil.rmtree(local_dir)" % indent)
        print("  + %s" % new_line.strip())
        print("─── 그리고 파일 끝에 _oc_keep_local_prune() 함수 추가 (약 60줄) ───")
        return 0

    patched = pat.sub(lambda _m: new_line, src, count=1)     # lambda: 역슬래시 해석 방지
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
    print(__doc__)
    print("사용: patch-newspaper-keep-local.sh 를 쓰세요 (--show 로 심을 코드만 볼 수 있음)")
