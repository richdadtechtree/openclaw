#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
news_page_text.py — 신문 사진마다 '실린 글자'를 읽어 둔다 (지면 ↔ 요약 기사 자동 연결용, 2026-09-24)

[왜 필요한가]
  다이제스트 웹의 '📰 글+지면' 보기는 요약된 기사 옆에 그 기사가 실린 신문 사진을 붙인다.
  요약은 사용자의 ChatGPT 가 만들어서 "몇 번째 사진" 표시(• 사진: 07)가 빠지는 날이 많다.
  → 요약에 기대지 않고, **서버가 사진 속 글자를 직접 읽어** 두면 웹이 요약 기사와 대조해 연결할 수 있다.

[어떻게]
  tesseract(무료 글자 인식 프로그램, AI·인터넷·요금 없음)로 사진 한 장씩 읽고,
  대조에 쓸 '낱말 조각·숫자' 목록만 뽑아 같은 폴더의 page_text.json 에 저장한다.
    · 숫자  : 1305 · 82793 · 3.3 처럼 — 기사마다 거의 겹치지 않아 가장 강한 단서
    · 한글  : 낱말 앞 2·3글자(조사 '은·는·을·를…' 가 붙어도 같은 조각이 나오게)
    · 영문  : ESS · RMAC 같은 약어
  웹(stock/slack_digest_live.html 의 matchPage)이 요약 기사에서 **똑같은 규칙으로** 조각을 뽑아 비교한다.
  ⚠️ 규칙을 바꾸면 두 곳(tokens() 와 JS 의 pageTokens())을 **함께** 고쳐야 한다.

  · 한 번 읽은 장은 다시 안 읽는다(파일 크기가 같으면 재사용). 한 장에 수 초 — 하루 30장이면 1~3분.
  · news_sync.py 가 사진을 준비한 직후 자동으로 불러 쓴다(끄려면 .env 에 NEWS_PAGE_OCR=0).
  · 표준 라이브러리만 사용(서버 시스템 python3 에 requests·Pillow 없음).

[설치 — 서버에서 한 번]
  sudo apt-get install -y tesseract-ocr tesseract-ocr-kor

사용법
  python3 ~/.openclaw/scripts/news_page_text.py              # 오늘
  python3 ~/.openclaw/scripts/news_page_text.py 2026-09-24   # 특정 날짜
  python3 ~/.openclaw/scripts/news_page_text.py --all        # 캐시에 있는 모든 날짜(처음 한 번 채우기)
  python3 ~/.openclaw/scripts/news_page_text.py --show       # 읽어 둔 결과 요약 보기
  python3 ~/.openclaw/scripts/news_page_text.py --force      # 이미 읽은 장도 다시

종료코드: 0 성공(또는 할 일 없음) / 2 사진 없음·tesseract 없음 / 1 일부 장 실패
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
OUT_FILE = "page_text.json"
ENGINE_VER = 1                     # 조각 뽑는 규칙을 바꾸면 올린다 → 예전 결과를 자동으로 다시 만든다

# 대조에 쓸모없는 흔한 조각(어느 기사에나 나오는 말) — 점수를 흐리지 않게 뺀다
STOP = {"있다", "있는", "있어", "하는", "했다", "한다", "것으로", "것이", "이번", "지난", "올해", "기자",
        "그러나", "하지만", "또한", "등의", "등을", "위해", "대한", "대해", "통해", "따라", "이후", "이상",
        "WHAT", "WHY", "HOW"}


def cache_root():
    return os.path.expanduser(os.getenv("NEWS_CACHE_DIR", "~/.openclaw/news_cache"))


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def tokens(text):
    """
    글 → 대조용 조각 집합. (웹 JS 의 pageTokens() 와 **똑같은 규칙**이어야 한다)
      숫자: 쉼표 없애고, 3자리 이상 정수 또는 소수(3.3)
      한글: 2글자 이상 낱말의 앞 2·3글자 → "분양가를" 과 "분양가" 가 '분양'·'분양가' 로 만난다
      영문: 2글자 이상, 대문자로
    """
    text = text or ""
    out = set()
    for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        n = n.replace(",", "")
        if "." in n or len(n) >= 3:
            out.add("#" + n)
    for w in re.findall(r"[가-힣]{2,}", text):
        out.add(w[:2])
        if len(w) >= 3:
            out.add(w[:3])
    for w in re.findall(r"[A-Za-z]{2,}", text):
        out.add(w.upper())
    return {t for t in out if t not in STOP and t.lstrip("#") not in STOP}


def tesseract_bin():
    return shutil.which(os.getenv("TESSERACT_BIN", "tesseract"))


def has_korean(tb):
    try:
        out = subprocess.run([tb, "--list-langs"], capture_output=True, text=True, timeout=20)
        return "kor" in (out.stdout + out.stderr).split()
    except Exception:
        return False


def ocr(tb, path, timeout=180):
    """사진 한 장 → 글자. 신문은 여러 단이라 psm 3(자동 배치 분석)이 가장 잘 읽는다."""
    # 서버의 다른 일(게이트웨이·웹)을 막지 않게 CPU 를 2개까지만 쓰게 한다
    env = dict(os.environ, OMP_THREAD_LIMIT=os.getenv("OMP_THREAD_LIMIT", "2"))
    r = subprocess.run([tb, path, "stdout", "-l", "kor+eng", "--psm", "3"],
                       capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "tesseract 실패").strip().splitlines()[-1][:160])
    return r.stdout


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def build(date, force=False, verbose=True):
    say = (lambda m: print(m, flush=True)) if verbose else (lambda m: None)
    ddir = os.path.join(cache_root(), date)
    index = load_json(os.path.join(ddir, "index.json"), None)
    if not index or not index.get("images"):
        say("[%s] 신문 사진이 캐시에 없습니다(news_sync.py 먼저)." % date)
        return 2
    tb = tesseract_bin()
    if not tb or not has_korean(tb):
        say("[%s] tesseract(한국어)가 없어 지면 글자 읽기를 건너뜁니다.\n"
            "      설치: sudo apt-get install -y tesseract-ocr tesseract-ocr-kor" % date)
        return 2

    opath = os.path.join(ddir, OUT_FILE)
    store = load_json(opath, {}) or {}
    if store.get("ver") != ENGINE_VER:
        store = {}                                   # 규칙이 바뀌었으면 처음부터
    pages = store.get("pages") or {}
    done = kept = fail = 0
    for im in index["images"]:
        name = im["name"]
        path = os.path.join(ddir, os.path.basename(name))
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        old = pages.get(name) or {}
        if not force and old.get("ok") and old.get("size") == size and size:
            kept += 1
            continue
        if not size:
            say("  %s  ✗ 파일 없음(깨진 링크일 수 있음 — retention_cleanup.py --status)" % name)
            fail += 1
            continue
        try:
            text = ocr(tb, path)
            tk = sorted(tokens(text))
            pages[name] = {"size": size, "ok": bool(tk), "tokens": tk,
                           "head": re.sub(r"\s+", " ", text).strip()[:160]}
            say("  %s  ✓ 조각 %d개 · %s" % (name, len(tk), pages[name]["head"][:40]))
            done += 1
        except Exception as e:
            pages[name] = {"size": size, "ok": False, "tokens": [], "error": str(e)[:160]}
            say("  %s  ✗ %s" % (name, str(e)[:120]))
            fail += 1
        # 한 장 끝날 때마다 저장 — 중간에 끊겨도 읽은 것은 남는다
        store.update({"ver": ENGINE_VER, "engine": "tesseract",
                      "updated": datetime.now(KST).isoformat(timespec="seconds"), "pages": pages})
        write_json(opath, store)
    say("[%s] 지면 글자 읽기 — 새로 %d · 그대로 %d · 실패 %d" % (date, done, kept, fail))
    return 1 if fail else 0


def show(date):
    store = load_json(os.path.join(cache_root(), date, OUT_FILE), None)
    if not store:
        print("[%s] 아직 읽은 결과가 없습니다." % date)
        return 2
    print("[%s] %s · %s" % (date, store.get("engine"), store.get("updated")))
    for name, p in sorted((store.get("pages") or {}).items()):
        print("  %s  %s" % (name, ("조각 %d · %s" % (len(p.get("tokens") or []), p.get("head", "")[:50]))
                            if p.get("ok") else "✗ " + p.get("error", "없음")))
    return 0


def main():
    ap = argparse.ArgumentParser(description="신문 사진 속 글자를 읽어 page_text.json 에 저장(지면↔요약 자동 연결용)")
    ap.add_argument("date", nargs="?", default="", help="YYYY-MM-DD (기본: 오늘 KST)")
    ap.add_argument("--all", action="store_true", help="캐시에 있는 모든 날짜")
    ap.add_argument("--force", action="store_true", help="이미 읽은 장도 다시")
    ap.add_argument("--show", action="store_true", help="읽어 둔 결과만 보기")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.all:
        root = cache_root()
        dates = sorted(d for d in (os.listdir(root) if os.path.isdir(root) else []) if DATE_RE.fullmatch(d))
    else:
        dates = [a.date or today_kst()]
    rc = 0
    for d in dates:
        if not DATE_RE.fullmatch(d):
            print("날짜 형식은 YYYY-MM-DD 입니다: %s" % d, file=sys.stderr)
            return 1
        r = show(d) if a.show else build(d, force=a.force, verbose=not a.quiet)
        rc = max(rc, 0 if (a.all and r == 2) else r)
    return rc


if __name__ == "__main__":
    sys.exit(main())
