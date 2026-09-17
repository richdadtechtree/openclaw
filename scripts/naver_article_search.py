#!/usr/bin/env python3
"""
naver_article_search.py — 기사 '제목' 으로 네이버에서 매경·한경 원문 링크를 찾아준다.

왜 필요한가
-----------
1) 지면(신문 스크랩) 브리핑은 **제목만** 있고 링크가 없다. 사람이 손으로 찾거나
   AI 가 주소를 지어내면 엉뚱한 기사로 간다.
2) 한국경제(hankyung.com)는 서버에서 **HTTP 403** 으로 막혀 RSS·원문 접근이 안 된다
   (2026-09-17 `--probe` 로 확인). 네이버를 거치면 그 기사에 닿을 수 있다.

그래서 "제목 → 네이버 검색 → 매경·한경 기사 중 **제목이 가장 비슷한** 것" 을 찾아준다.
유사도 계산은 `verify_article_url.py` 와 **똑같은 기준**을 쓴다(따로 놀면 안 되므로).

준비물 (한 번만)
----------------
네이버 검색 오픈API 키가 필요하다. 무료다.
  1. https://developers.naver.com/apps/#/register 에서 애플리케이션 등록
     → 사용 API 에 **검색** 추가
  2. 발급된 Client ID / Secret 을 `~/.openclaw/.env` 에 추가:
        NAVER_CLIENT_ID=발급받은_아이디
        NAVER_CLIENT_SECRET=발급받은_시크릿
키가 없으면 이 도구는 **조용히 실패**하고(exit 3), 브리핑은 하던 대로 계속 돈다.

사용법
------
  python3 scripts/naver_article_search.py --title "삼성전자 3조 투자 결정"
  python3 scripts/naver_article_search.py --title "..." --outlet 한국경제
  python3 scripts/naver_article_search.py --title "..." --json
  python3 scripts/naver_article_search.py --self-test     # 키 없이 판단 로직만 점검

종료 코드:  0 = 찾음,  2 = 비슷한 기사 없음,  3 = 키 없음/네이버 오류,  1 = 사용법 오류
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_article_url as V  # noqa: E402  (제목 정규화·유사도·페이지 열기 재사용)

API = "https://openapi.naver.com/v1/search/news.json"
TIMEOUT = 8
MATCH_PASS = 0.55        # 이 점수 아래면 '같은 기사라고 못 하겠다' → 링크를 주지 않는다
DISPLAY = 30             # 한 번에 받아올 검색 결과 수 (최대 100)

# 어느 매체를 '원문' 으로 인정할지
OUTLET_HOSTS = {
    "매일경제": ("mk.co.kr",),
    "한국경제": ("hankyung.com", "hankyungtv.com"),
}


# ── .env 읽기 (다른 스크립트와 같은 방식) ─────────────────────────────────
def load_env() -> None:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (os.path.join(base, ".env"), ".env"):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


# ── 검색어 다듬기 ─────────────────────────────────────────────────────────
def search_query(title: str, short: bool = False) -> str:
    """기사 제목 → 검색어.

    제목을 그대로 넣으면 따옴표·말줄임표·[단독] 때문에 결과가 0건일 때가 있다.
    기호를 털어내고, short=True 면 **앞쪽 핵심 낱말 7개**만 남겨 더 넓게 찾는다.
    """
    t = html.unescape(title or "")
    t = re.sub(r"[\[\]【】〈〉《》「」『』()（）]", " ", t)      # 괄호류
    t = re.sub(r"[\"'“”‘’…·|/\\~*#]+", " ", t)                  # 따옴표·기호
    t = re.sub(r"\s+", " ", t).strip()
    if short:
        t = " ".join(t.split()[:7])
    return t


def _clean(s: str) -> str:
    """네이버가 주는 제목에는 <b> 강조태그와 HTML 기호가 섞여 있다 → 벗겨낸다."""
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# ── 네이버 검색 ───────────────────────────────────────────────────────────
def naver_search(query: str, display: int = DISPLAY, sort: str = "sim") -> tuple[list, str]:
    """네이버 뉴스 검색. 반환 (결과목록, 오류메시지)."""
    cid = os.getenv("NAVER_CLIENT_ID", "")
    secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not (cid and secret):
        return [], ("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 없습니다. "
                    "~/.openclaw/.env 에 추가하세요(발급: https://developers.naver.com/apps/).")
    url = f"{API}?query={urllib.parse.quote(query)}&display={display}&sort={sort}"
    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": cid,
        "X-Naver-Client-Secret": secret,
        "User-Agent": V.UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return json.loads(res.read().decode("utf-8")).get("items", []), ""
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = " " + e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        return [], f"네이버 API 오류 HTTP {e.code}{detail}"
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def _outlet_of(link: str, outlets) -> str:
    """원문 주소의 도메인으로 어느 신문사인지 가린다. 대상 밖이면 빈 문자열."""
    host = V.host_of(link)
    for name in outlets:
        if V.host_matches(host, OUTLET_HOSTS.get(name, ())):
            return name
    return ""


def search_best(title: str, outlets=("매일경제", "한국경제"),
                min_score: float = MATCH_PASS, check_open: bool = True) -> dict:
    """제목과 가장 비슷한 매경·한경 기사를 찾는다.

    반환 dict:
      found        찾았는가
      score        제목 유사도 0~1
      outlet       매일경제 / 한국경제
      title        네이버가 준 그 기사 제목
      link         **브리핑에 쓸 링크** (원문이 열리면 원문, 막혀 있으면 네이버 링크)
      origin_url   신문사 원문 주소
      naver_url    네이버 뉴스 주소 (원문이 막혔을 때의 우회로)
      reason       실패 사유
      candidates   점수 상위 후보 3건 (사람이 눈으로 확인할 수 있게)
    """
    out = {"query": "", "found": False, "score": 0.0, "outlet": "", "title": "",
           "link": "", "origin_url": "", "naver_url": "", "reason": "", "candidates": []}
    if not (title or "").strip():
        out["reason"] = "no_title"
        return out

    # 1차는 제목 전체로, 결과가 시원찮으면 2차로 핵심 낱말만 넣어 넓게 찾는다
    scored: list[tuple[float, dict]] = []
    for short in (False, True):
        q = search_query(title, short=short)
        out["query"] = q
        items, err = naver_search(q)
        if err:
            out["reason"] = err
            return out
        for it in items:
            origin = it.get("originallink", "") or ""
            outlet = _outlet_of(origin, outlets)
            if not outlet:
                continue                       # 매경·한경이 아니면 버린다
            found_title = _clean(it.get("title", ""))
            score = V.title_score(title, found_title)
            scored.append((score, {"outlet": outlet, "title": found_title,
                                   "origin_url": origin,
                                   "naver_url": it.get("link", "") or ""}))
        scored.sort(key=lambda x: -x[0])
        if scored and scored[0][0] >= min_score:
            break                              # 충분히 비슷한 걸 찾았으면 2차 검색 생략

    out["candidates"] = [{"score": round(s, 3), **d} for s, d in scored[:3]]
    if not scored:
        out["reason"] = "매경·한경 기사를 찾지 못했습니다"
        return out

    best_score, best = scored[0]
    out["score"] = round(best_score, 3)
    out.update({k: best[k] for k in ("outlet", "title", "origin_url", "naver_url")})
    if best_score < min_score:
        out["reason"] = f"제목이 충분히 비슷하지 않습니다(유사도 {best_score:.2f})"
        return out

    # 브리핑에 쓸 링크 고르기 — 원문이 우선이지만 '열리는지' 확인한다.
    # 한국경제처럼 403 으로 막힌 곳은 네이버 링크가 유일하게 열리는 길이다.
    link = best["origin_url"]
    if check_open and link:
        _, page, err = V.fetch(link)
        if err or not page:
            link = best["naver_url"] or link
            out["reason"] = f"원문이 안 열려({err}) 네이버 링크를 씁니다"
    out["link"] = link or best["naver_url"]
    out["found"] = bool(out["link"])
    return out


# ── 키 없이 판단 로직만 점검 ──────────────────────────────────────────────
def self_test() -> int:
    """네이버 키 없이도 '무엇을 고를지' 판단이 맞는지 확인한다."""
    print("네이버 키 없이 판단 로직만 점검합니다\n")
    ok = True

    cases = [
        ("검색어 다듬기(기호 제거)",
         search_query('[단독] "삼성전자" 3조 투자…반도체 승부수'),
         "단독 삼성전자 3조 투자 반도체 승부수"),
        ("검색어 줄이기(핵심 7낱말)",
         search_query("가 나 다 라 마 바 사 아 자 차", short=True),
         "가 나 다 라 마 바 사"),
    ]
    for name, got, want in cases:
        good = got == want
        ok &= good
        print(("  ✅ " if good else "  ❌ ") + f"{name}\n       → {got!r}")

    pairs = [
        ("같은 기사(강조태그 섞임)", '삼성전자, 3조 투자 결정',
         _clean('<b>삼성전자</b>, 3조 투자 결정'), True),
        ("같은 기사(언론사 꼬리표)", "전세대출 규제 강화",
         "전세대출 규제 강화 - 한국경제", True),
        ("다른 기사", "삼성전자 3조 투자 결정", "가을 전시회 추천 10선", False),
    ]
    for name, a, b, want_match in pairs:
        sc = V.title_score(a, b)
        good = (sc >= MATCH_PASS) == want_match
        ok &= good
        print(("  ✅ " if good else "  ❌ ") + f"{name} (유사도 {sc:.2f})")

    hosts = [("https://www.mk.co.kr/news/stock/1", "매일경제"),
             ("https://www.hankyung.com/article/1", "한국경제"),
             ("https://www.chosun.com/x", "")]
    for link, want in hosts:
        got = _outlet_of(link, ("매일경제", "한국경제"))
        good = got == want
        ok &= good
        print(("  ✅ " if good else "  ❌ ") + f"매체 가리기 {link[:38]} → {got or '대상아님'}")

    print("\n총평:", "통과" if ok else "실패")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="기사 제목으로 네이버에서 매경·한경 원문 링크를 찾는다")
    ap.add_argument("--title", help="찾을 기사 제목")
    ap.add_argument("--outlet", choices=["매일경제", "한국경제"],
                    help="한 매체로 한정(기본: 둘 다)")
    ap.add_argument("--json", action="store_true", help="결과를 JSON 으로 출력")
    ap.add_argument("--min-score", type=float, default=MATCH_PASS,
                    help=f"이 유사도 미만이면 링크를 주지 않는다 (기본 {MATCH_PASS})")
    ap.add_argument("--no-check-open", action="store_true",
                    help="원문이 열리는지 확인하지 않는다(빠름)")
    ap.add_argument("--self-test", action="store_true", help="키 없이 판단 로직만 점검")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if not a.title:
        ap.print_help()
        return 1

    load_env()
    outlets = (a.outlet,) if a.outlet else ("매일경제", "한국경제")
    r = search_best(a.title, outlets, min_score=a.min_score,
                    check_open=not a.no_check_open)

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif r["found"]:
        print(f"✅ {r['outlet']} (제목 유사도 {r['score']:.2f})")
        print(f"   제목  : {r['title']}")
        print(f"   링크  : {r['link']}          ← 브리핑에 이걸 쓰세요")
        print(f"   원문  : {r['origin_url']}")
        print(f"   네이버: {r['naver_url']}")
        if r["reason"]:
            print(f"   참고  : {r['reason']}")
    else:
        print(f"❌ 못 찾음 — {r['reason']}")
        for c in r["candidates"]:
            print(f"   후보({c['score']:.2f}) {c['outlet']} {c['title'][:44]}")

    if r["found"]:
        return 0
    if "NAVER_CLIENT_ID" in r["reason"] or "네이버 API" in r["reason"]:
        return 3                      # 키·API 문제 → 부르는 쪽이 조용히 넘어가도록
    return 2                          # 비슷한 기사 없음 → 링크를 지어내면 안 된다


if __name__ == "__main__":
    sys.exit(main())
