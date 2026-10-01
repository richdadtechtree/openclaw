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
WORDS_FILE = "page_words.json"     # 낱말 위치(2026-10-01) — 요약 근거를 지면에 형광펜으로 긋는 데 쓴다
ENGINE_VER = 2                     # 조각 뽑는 규칙·읽기 설정을 바꾸면 올린다 → 예전 결과를 자동으로 다시 만든다
                                   # (2 = 2026-10-01 Sauvola 흑백 변환으로 읽기 → 숫자를 훨씬 잘 읽음)
WORDS_VER = 1                      # 낱말 위치·단 나누기 규칙을 바꾸면 올린다

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


def ocr(tb, path, timeout=600):
    """
    사진 한 장 → (글자, 낱말 위치 표). 신문은 여러 단이라 psm 3(자동 배치 분석)이 가장 잘 읽는다.
    'tsv' 로 받으면 **한 번 읽기로** 글자와 낱말마다의 위치(왼쪽·위·너비·높이)를 함께 얻는다.
    """
    # 서버의 다른 일(게이트웨이·웹)을 막지 않게 CPU 를 2개까지만 쓰게 한다
    env = dict(os.environ, OMP_THREAD_LIMIT=os.getenv("OMP_THREAD_LIMIT", "2"))
    # thresholding_method=2 (Sauvola): 사진을 흑백으로 바꿀 때 '부분마다' 밝기 기준을 달리한다.
    #   기본값(전체 한 기준)으로는 2026-10-01 시험 지면에서 숫자 13개 중 8개만 읽혔고 줄 일부를 그림으로 착각했다
    #   → Sauvola 로 12개. 조명이 고르지 않은 사진·스캔 지면에 특히 낫다. 속도는 같다. NEWS_OCR_THRESH=0 이면 예전 방식.
    r = subprocess.run([tb, path, "stdout", "-l", "kor+eng", "--psm", "3",
                        "-c", "thresholding_method=" + os.getenv("NEWS_OCR_THRESH", "2"), "tsv"],
                       capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "tesseract 실패").strip().splitlines()[-1][:160])
    return parse_tsv(r.stdout)


def parse_tsv(tsv):
    """
    tesseract tsv → (글자, {"W","H","lines":[[낱말…]…]}).
    낱말 = (글자, 왼쪽, 위, 너비, 높이) 픽셀. 줄은 tesseract 가 묶은 (block, par, line) 단위.
    """
    W = H = 0
    lines, order = {}, []
    for row in (tsv or "").splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12:
            continue
        try:
            lv, l, t, w, h = int(c[0]), int(c[6]), int(c[7]), int(c[8]), int(c[9])
        except ValueError:
            continue
        if lv == 1:
            W, H = max(W, l + w), max(H, t + h)
            continue
        txt = c[11].strip()
        if lv != 5 or not txt:
            continue
        key = (c[2], c[3], c[4])
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append((txt, l, t, w, h))
    text = "\n".join(" ".join(wd[0] for wd in lines[k]) for k in order)
    return text, {"W": W, "H": H, "lines": [lines[k] for k in order]}


def layout(page):
    """
    낱말 위치 → **단(세로 기둥)별로 다시 정렬한 줄 조각** (2026-10-01).

    왜 필요한가: 여러 단짜리 지면에서 tesseract 는 한 줄을 **세 단을 가로질러** 읽기도 한다
    ("…미분양 주택이 / 해 상반기 말 4383 / 올해 6월까지…"). 그대로 이으면 문장이 뒤섞여
    요약의 근거 문장을 찾을 수 없다.
      ① 한 줄 안에서 낱말 사이가 글자 높이의 1.6배보다 벌어지면 → 다른 단 → 조각을 나눈다
      ② 왼쪽 끝이 비슷하고(단 폭의 30% 이내) 가로로 겹치며 글자 크기가 비슷한 조각끼리 → 같은 단
         (큰 제목은 글자 크기가 달라 본문 단과 섞이지 않는다)
      ③ 단은 왼쪽→오른쪽, 단 안의 조각은 위→아래 순서로
    반환 좌표는 사진 크기 대비 0~10000 정수(용량 절약). 형식:
      {"W":픽셀,"H":픽셀,"segs":[[단번호, x, y, w, h, [[글자, x, y, w, h], …]], …]}
    """
    W, H = page.get("W") or 0, page.get("H") or 0
    if not (W and H):
        return {"W": W, "H": H, "segs": []}
    # 단 사이 골에 tesseract 가 '_' '|' '「' 같은 부스러기를 읽어 넣으면 두 단이 이어져 버린다 → 기호뿐인 짧은 조각은 뺀다
    junk = re.compile(r"^[_|「」『』\[\]=~>\-—–'\"`.,:;!]{1,2}$")
    lines = [sorted((q for q in ln if not junk.match(q[0])), key=lambda q: q[1]) for ln in (page.get("lines") or [])]
    lines = [ln for ln in lines if ln]
    allw = [q for ln in lines for q in ln]
    # 위아래 줄 찾기를 빠르게 — 낱말을 세로 띠(64px)별로 담아 둔다
    band = {}
    for li, ln in enumerate(lines):
        for q in ln:
            band.setdefault((q[2] + q[4] // 2) // 64, []).append((li, q))

    def gutter(li, x0, x1, ymid, h):
        """이 줄의 낱말 틈(x0~x1)이 '단 사이 골'인가? → 위아래 가까운 줄들도 그 자리가 비어 있으면 그렇다.
        낱말 사이 빈칸은 줄마다 위치가 달라 위아래 줄의 글자가 그 자리를 덮는다."""
        mid = (x0 + x1) / 2.0
        up, down = set(), set()
        for bk in range(int((ymid - 4 * h) // 64), int((ymid + 4 * h) // 64) + 1):
            for lj, q in band.get(bk, ()):
                cy = q[2] + q[4] / 2.0
                if lj == li or abs(cy - ymid) > 4 * h or abs(cy - ymid) < 0.5 * h:
                    continue
                if not (0.6 * h <= q[4] <= 1.6 * h):          # 글자 크기가 다른 줄(제목 등)은 안 본다
                    continue
                if not (x0 - 8 * h < q[1] < x1 + 8 * h):      # 멀리 떨어진 다른 기사 글자는 안 본다
                    continue
                (up if cy < ymid else down).add(lj)
                if q[1] - 0.15 * h < mid < q[1] + q[3] + 0.15 * h:
                    return False                              # 위·아래 줄 글자가 그 자리를 덮는다 → 그냥 빈칸
        return len(up) >= 2 or len(down) >= 2                 # 비교할 줄이 위나 아래에 2줄 이상 있어야 판단

    segs = []
    for li, ln in enumerate(lines):
        hmed = sorted(q[4] for q in ln)[len(ln) // 2] or 1
        cur = [ln[0]]
        for q in ln[1:]:
            prev = cur[-1]
            gap = q[1] - (prev[1] + prev[3])
            ymid = (min(prev[2], q[2]) + max(prev[2] + prev[4], q[2] + q[4])) / 2.0
            # 단 사이 골은 보통 글자 한 개 폭 이상. 양쪽 맞춤 줄의 넓은 빈칸(0.3~0.8배)을 골로 착각하지 않게 0.9배부터 본다
            if gap > 1.6 * hmed or (gap > 0.9 * hmed and gutter(li, prev[1] + prev[3], q[1], ymid, hmed)):
                segs.append(cur)
                cur = [q]
            else:
                cur.append(q)
        segs.append(cur)

    def box(ws):
        l = min(q[1] for q in ws); t = min(q[2] for q in ws)
        r = max(q[1] + q[3] for q in ws); b = max(q[2] + q[4] for q in ws)
        hs = sorted(q[4] for q in ws)
        return [l, t, r - l, b - t, hs[len(hs) // 2] or 1]

    boxes = [box(sg) for sg in segs]
    parent = list(range(len(segs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(segs)):
        li, ti, wi, hi, fi = boxes[i]
        for j in range(i + 1, len(segs)):
            lj, tj, wj, hj, fj = boxes[j]
            if max(fi, fj) > 1.5 * min(fi, fj):              # 글자 크기가 다르면(제목↔본문) 다른 무리
                continue
            ov = min(li + wi, lj + wj) - max(li, lj)
            if ov <= 0.5 * min(wi, wj):                      # 가로로 충분히 안 겹치면 다른 단
                continue
            if abs(li - lj) > 0.3 * max(wi, wj):             # 왼쪽 끝이 너무 다르면 다른 단
                continue
            parent[find(i)] = find(j)

    groups = {}
    for i in range(len(segs)):
        groups.setdefault(find(i), []).append(i)
    cols = sorted(groups.values(), key=lambda g: (min(boxes[i][0] for i in g), min(boxes[i][1] for i in g)))
    sx, sy = 10000.0 / W, 10000.0 / H
    n = lambda v, s: int(round(v * s))
    out = []
    for ci, g in enumerate(cols):
        for i in sorted(g, key=lambda k: (boxes[k][1], boxes[k][0])):
            l, t, w, h, _ = boxes[i]
            out.append([ci, n(l, sx), n(t, sy), n(w, sx), n(h, sy),
                        [[q[0], n(q[1], sx), n(q[2], sy), n(q[3], sx), n(q[4], sy)] for q in segs[i]]])
    return {"W": W, "H": H, "segs": out}


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

    # 한 번에 하나만 — 30분마다 도는 자동 실행과 손으로 한 실행이 겹치면 같은 장을 두 번 읽고 파일을 서로 덮어쓴다
    import fcntl
    lockf = open(os.path.join(ddir, ".page_text.lock"), "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        say("[%s] 이미 다른 곳에서 지면 글자를 읽는 중이에요(30분마다 도는 자동 실행일 수 있음). 그쪽이 끝나면 반영돼요." % date)
        return 0

    opath = os.path.join(ddir, OUT_FILE)
    store = load_json(opath, {}) or {}
    if store.get("ver") != ENGINE_VER:
        store = {}                                   # 규칙이 바뀌었으면 처음부터
    pages = store.get("pages") or {}
    wpath = os.path.join(ddir, WORDS_FILE)
    wstore = load_json(wpath, {}) or {}
    if wstore.get("ver") != WORDS_VER:
        wstore = {}
    wpages = wstore.get("pages") or {}
    done = kept = fail = 0
    total = len(index["images"])
    def _done(n):
        o = pages.get(n) or {}
        return "tokens" in o and not o.get("error") and (wpages.get(n) or {}).get("size")
    todo = sum(1 for im in index["images"] if force or not _done(im["name"]))
    if todo:
        say("[%s] 신문 %d장 중 %d장을 읽어요. 한 장에 30초~1분쯤 걸려요 — 끝날 때까지 그대로 두세요.\n"
            "      (중간에 꺼도 읽은 장은 남고, 30분마다 서버가 이어서 읽어요)" % (date, total, todo))
    import time
    for no, im in enumerate(index["images"], 1):
        name = im["name"]
        path = os.path.join(ddir, os.path.basename(name))
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        old = pages.get(name) or {}
        # 글자 조각과 낱말 위치가 **둘 다** 있을 때만 건너뛴다
        # (2026-10-01 이전에 읽은 장은 위치가 없어 한 번 더 읽는다)
        # 글자가 거의 없는 장(광고·큰 사진)은 조각이 0개라 ok=False 지만 오류는 아니다 → 다시 읽지 않는다
        if not force and size and old.get("size") == size and not old.get("error") and "tokens" in old \
                and (wpages.get(name) or {}).get("size") == size:
            kept += 1
            continue
        if not size:
            say("  %s  ✗ 파일 없음(깨진 링크일 수 있음 — retention_cleanup.py --status)" % name)
            fail += 1
            continue
        try:
            if verbose:
                print("  [%d/%d] %s 읽는 중…" % (no, total, name), end="", flush=True)
            t0 = time.time()
            text, raw = ocr(tb, path)
            if verbose:
                print(" %.0f초" % (time.time() - t0), flush=True)
            tk = sorted(tokens(text))
            lay = layout(raw)
            lay["size"] = size
            wpages[name] = lay
            pages[name] = {"size": size, "ok": bool(tk), "tokens": tk,
                           "head": re.sub(r"\s+", " ", text).strip()[:160]}
            say("  %s  ✓ 조각 %d개 · %s" % (name, len(tk), pages[name]["head"][:40]))
            done += 1
        except Exception as e:
            if verbose:
                print("", flush=True)              # '읽는 중…' 줄을 끝내고 오류는 새 줄에
            pages[name] = {"size": size, "ok": False, "tokens": [], "error": str(e)[:160]}
            say("  %s  ✗ %s" % (name, str(e)[:120]))
            fail += 1
        # 한 장 끝날 때마다 저장 — 중간에 끊겨도 읽은 것은 남는다
        store.update({"ver": ENGINE_VER, "engine": "tesseract",
                      "updated": datetime.now(KST).isoformat(timespec="seconds"), "pages": pages})
        write_json(opath, store)
        if name in wpages:
            wstore.update({"ver": WORDS_VER, "engine": "tesseract", "updated": store["updated"], "pages": wpages})
            write_json(wpath, wstore)
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
