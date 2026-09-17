#!/usr/bin/env python3
"""
verify_article_url.py — "이 링크가 정말 그 기사인가?" 를 실제로 열어 보고 확인한다.

왜 필요한가
-----------
브리핑에 붙는 '원문 링크' 가 엉뚱한 기사로 가는 일이 있었다. 원인은 크게 셋:
  1) 구글뉴스 중계 주소(`news.google.com/rss/articles/CBMi…`) — 언론사 주소가 아니라
     구글이 만든 임시 주소다. 요즘 형식은 사람이 풀 수 없고, 열면 다른 기사나
     구글뉴스 화면으로 빠진다.  ← 과거 브리핑에서 실제로 발견됨
  2) RSS 제목과 실제 페이지 제목이 다른 경우(주소가 옮겨갔거나 목록 페이지).
  3) 사람/AI 가 제목과 링크를 옮겨 적다가 짝을 잘못 맞추는 경우.

그래서 "제목 ↔ 주소" 짝이 맞는지 **직접 페이지를 열어** 대조한다.

판정 방법 (세 겹)
-----------------
  ① 도메인 검사 — 최종 도착지가 그 언론사 도메인인가. (구글뉴스 등 중계 주소는 탈락)
  ② 기사 번호 대조 — 주소 속 기사 ID 와 페이지가 스스로 밝힌 정식 주소(canonical)의
     ID 가 같은가. 같으면 제목이 조금 달라도 같은 기사로 인정한다.
  ③ 제목 대조 — 페이지의 og:title / h1 / <title> 과 우리가 아는 제목을 정규화해 비교.

의존성 없음 — **파이썬 표준 라이브러리만** 쓴다.
(서버 시스템 python3 에는 requests 가 없다. 그 함정을 피하려고 일부러 stdlib 만 썼다.)

사용법
------
  # 링크 한 개 확인
  python3 scripts/verify_article_url.py --url "https://www.mk.co.kr/news/stock/11111" \
                                        --title "기사 제목"

  # news_data.json 통째로 검사해서 '확인된 기사만' 남기기
  python3 scripts/verify_article_url.py --json workspace/news_data.json --write

종료 코드:  0 = 같은 기사 확인,  2 = 다른 기사/확인 실패,  1 = 실행 오류
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from html.parser import HTMLParser

# ── 설정값 ────────────────────────────────────────────────────────────────
TIMEOUT = 8                  # 한 페이지 기다리는 최대 초 (느린 서버는 빨리 포기)
MAX_BYTES = 1_200_000        # 너무 큰 페이지는 앞부분만 (제목은 <head> 에 있다)
TITLE_PASS = 0.60            # 제목 유사도 합격선 (0~1)
CONTAIN_PASS = 0.80          # 한쪽이 다른 쪽을 품고 있을 때의 합격선

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 언론사별로 '진짜 원문' 으로 인정하는 도메인.
# 여기 없는 곳으로 도착하면 중계·수집 사이트로 보고 탈락시킨다.
OUTLET_HOSTS = {
    "매일경제": ("mk.co.kr",),
    "한국경제": ("hankyung.com", "hankyungtv.com"),
}

# 기사 원문이 아니라 '중간에 거쳐 가는' 주소들 — 무조건 탈락.
# (구글뉴스 중계 주소가 바로 과거 브리핑을 망친 주범이다)
RELAY_HOSTS = (
    "news.google.com", "google.com", "t.co", "bit.ly", "buff.ly",
    "feedproxy.google.com", "feeds.feedburner.com", "link.mk.co.kr",
)


# ── 아주 작은 HTML 파서 (bs4 없이 <head> 정보만 뽑는다) ─────────────────────
class HeadParser(HTMLParser):
    """페이지에서 제목·정식주소(canonical)·첫 h1 만 뽑아내는 최소 파서."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.og_title = ""
        self.doc_title = ""
        self.canonical = ""
        self.og_url = ""
        self.h1 = ""
        self._in_title = False
        self._in_h1 = False
        self._h1_done = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            content = a.get("content", "").strip()
            if key in ("og:title", "twitter:title") and content and not self.og_title:
                self.og_title = content
            elif key == "og:url" and content and not self.og_url:
                self.og_url = content
        elif tag == "link":
            rel = a.get("rel", "").lower()
            if "canonical" in rel and a.get("href") and not self.canonical:
                self.canonical = a["href"].strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "h1" and not self._h1_done:
            self._in_h1 = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1" and self._in_h1:
            self._in_h1 = False
            self._h1_done = True

    def handle_data(self, data):
        if self._in_title:
            self.doc_title += data
        if self._in_h1:
            self.h1 += data


# ── 문자열 정규화 / 비교 ──────────────────────────────────────────────────
# 제목 뒤에 붙는 언론사 꼬리표. RSS 제목엔 없고 페이지 <title> 엔 있는 경우가 많다.
OUTLET_TAIL = re.compile(
    r"\s*[|\-–—:·]\s*(매일경제|매경|MK|한국경제|한경|한경닷컴|네이버|다음|Daum|Naver)"
    r"(\s*(뉴스|경제|증권|부동산|닷컴))?\s*$", re.I)

# [단독] 【속보】 <칼럼> 같은 머리표·꼬리표
BRACKETS = re.compile(r"[\[\]【】〈〉<>《》「」『』()（）]")
PUNCT = re.compile(r"[\"'“”‘’·…,.!?~\-–—/\\|:;*#]+")


def norm_title(s: str) -> str:
    """제목을 비교하기 좋은 형태로 다듬는다.

    '[단독] 삼성전자, 3조 투자 - 매일경제'  →  '단독삼성전자3조투자'
    한글은 띄어쓰기가 들쭉날쭉해서 **공백까지 모두 지우고** 비교한다.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("&nbsp;", " ")
    s = OUTLET_TAIL.sub("", s)          # 꼬리 언론사명 제거
    s = BRACKETS.sub(" ", s)            # 괄호류 제거
    s = PUNCT.sub(" ", s)               # 문장부호 제거
    s = re.sub(r"\s+", "", s)           # 공백 전부 제거
    return s.lower()


def title_score(a: str, b: str) -> float:
    """두 제목이 얼마나 같은지 0~1 로 매긴다.

    - 기본은 difflib 유사도.
    - 한쪽이 다른 쪽을 통째로 품고 있으면(제목 줄임 등) 점수를 끌어올린다.
      예) RSS '삼성전자 3조 투자' vs 페이지 '삼성전자 3조 투자…반도체 승부수'
    """
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    short, long_ = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(short) >= 8 and short in long_:       # 짧은 쪽이 통째로 들어있다
        ratio = max(ratio, CONTAIN_PASS + 0.05)
    return round(ratio, 3)


def host_of(url: str) -> str:
    """주소에서 도메인만 뽑는다. (www. 는 아래 host_matches 가 하위도메인으로 처리하므로
    여기서 굳이 떼지 않는다 — lstrip 으로 떼면 'wow.co.kr' 이 'ow.co.kr' 로 망가진다.)"""
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def host_matches(host: str, allowed: tuple[str, ...]) -> bool:
    """도메인이 허용 목록에 속하는가(하위 도메인 포함)."""
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def article_id(url: str) -> str:
    """주소에서 기사 번호로 보이는 가장 긴 숫자 덩어리를 뽑는다.

    매경: /news/stock/12129186        → 12129186
    한경: /article/2026091612345      → 2026091612345
    숫자가 6자리 미만이면 기사 번호로 보지 않는다(연도·페이지 번호 오인 방지).
    """
    try:
        path = urllib.parse.urlparse(url).path
    except Exception:
        return ""
    nums = re.findall(r"\d{6,}", path)
    return max(nums, key=len) if nums else ""


# ── 페이지 가져오기 ───────────────────────────────────────────────────────
def _headers(url: str, full: bool = False) -> dict:
    """요청에 붙일 헤더.

    full=True 면 **진짜 브라우저에 더 가깝게** 만든다. 한국경제처럼 봇을 막는 사이트가
    403(거부)을 줄 때 한 번 더 시도하기 위한 것 — 사이트가 보는 것은 헤더뿐이라
    Referer·Sec-Fetch 같은 브라우저 기본 헤더가 없으면 프로그램으로 판정되기 쉽다.
    """
    h = {
        "User-Agent": UA,
        "Accept": ("application/rss+xml,application/xml;q=0.9,text/html;q=0.8,*/*;q=0.7"
                   if full else
                   "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.5",
    }
    if not full:
        h["Accept-Encoding"] = "gzip"
        return h
    try:
        u = urllib.parse.urlparse(url)
        origin = f"{u.scheme}://{u.netloc}"
    except Exception:
        origin = ""
    h.update({
        "Referer": origin + "/" if origin else "",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    return {k: v for k, v in h.items() if v}     # 빈 값은 빼고 보낸다


# 봇 차단으로 보이는 응답 코드 — 이럴 때만 '브라우저 흉내' 헤더로 한 번 더 시도한다
_BLOCKED = (401, 403, 405, 406, 409, 429)


def fetch(url: str, full_headers: bool = False) -> tuple[str, str, str]:
    """페이지를 연다. 반환 (최종주소, HTML, 오류메시지).

    403 등 '봇 차단' 으로 보이면 헤더를 더 브라우저처럼 바꿔 **한 번만** 더 시도한다.
    (무한 재시도는 상대 서버에 민폐라 딱 1회만)
    """
    req = urllib.request.Request(url, headers=_headers(url, full_headers))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            final_url = res.geturl()                 # 리다이렉트 따라간 최종 주소
            raw = res.read(MAX_BYTES)
            if res.headers.get("Content-Encoding", "") == "gzip":
                try:
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                except Exception:
                    pass                              # 잘린 gzip 은 그냥 포기
            # 인코딩 판단: 헤더 → meta charset → utf-8
            enc = res.headers.get_content_charset()
            if not enc:
                m = re.search(rb'charset=["\']?([\w\-]+)', raw[:4000], re.I)
                enc = m.group(1).decode("ascii", "ignore") if m else "utf-8"
            return final_url, raw.decode(enc, errors="replace"), ""
    except urllib.error.HTTPError as e:
        if e.code in _BLOCKED and not full_headers:
            return fetch(url, full_headers=True)      # 브라우저 흉내로 딱 한 번 재시도
        suffix = " (브라우저 헤더로 재시도했지만 여전히 거부)" if full_headers else ""
        return url, "", f"HTTP {e.code}{suffix}"
    except Exception as e:                            # 타임아웃·DNS·SSL 등
        return url, "", f"{type(e).__name__}: {e}"


# ── 핵심: 한 건 검증 ──────────────────────────────────────────────────────
def verify(url: str, title: str, outlet: str = "", strict_host: bool = True,
           keep_html: bool = False) -> dict:
    """링크가 정말 그 제목의 기사인지 확인한다.

    반환 dict:
      verified     True/False   — 같은 기사라고 확신하는가
      reason       판정 근거 코드
      score        제목 유사도 0~1
      final_url    리다이렉트까지 따라간 최종 주소 (이걸 브리핑에 쓰면 된다)
      page_title   페이지가 스스로 밝힌 제목 (틀렸을 때 사람이 바로 비교 가능)
      html         keep_html=True 일 때만 — 방금 받아온 HTML

    ⚡ keep_html: 검증하려면 어차피 페이지를 한 번 받아야 한다. 그 HTML 을 돌려주면
       부르는 쪽이 **같은 페이지를 두 번 받지 않아도 된다**(속도 2배).
    """
    out = {
        "url": url, "title": title, "outlet": outlet,
        "verified": False, "reason": "", "score": 0.0,
        "final_url": url, "canonical_url": "", "page_title": "",
    }
    if not url or not url.startswith(("http://", "https://")):
        out["reason"] = "bad_url"
        return out

    # ① 중계 주소는 열어보기도 전에 탈락 (구글뉴스 등)
    if host_matches(host_of(url), RELAY_HOSTS):
        out["reason"] = "relay_link"          # 언론사 주소가 아님 → 엉뚱한 기사 위험
        return out

    final_url, html, err = fetch(url)
    out["final_url"] = final_url
    if keep_html:
        out["html"] = html          # 부르는 쪽이 본문 추출에 재활용한다
    if err or not html:
        out["reason"] = f"fetch_failed({err or 'empty'})"
        return out

    # 리다이렉트로 중계/다른 도메인에 도착했는지 다시 확인
    fhost = host_of(final_url)
    if host_matches(fhost, RELAY_HOSTS):
        out["reason"] = "relay_redirect"
        return out
    allowed = OUTLET_HOSTS.get(outlet)
    if strict_host and allowed and not host_matches(fhost, allowed):
        out["reason"] = f"host_mismatch({fhost})"
        return out

    p = HeadParser()
    try:
        p.feed(html)
    except Exception:
        pass                                   # 깨진 HTML 이어도 뽑힌 만큼은 쓴다

    canonical = urllib.parse.urljoin(final_url, p.canonical or p.og_url or "")
    out["canonical_url"] = canonical
    page_title = (p.og_title or p.h1 or p.doc_title or "").strip()
    page_title = re.sub(r"\s+", " ", page_title)
    out["page_title"] = page_title

    # 정식 주소가 아예 다른 기사 번호를 가리키면 그 자체로 탈락
    src_id, can_id = article_id(final_url), article_id(canonical)
    if src_id and can_id and src_id != can_id:
        out["reason"] = f"article_id_mismatch({src_id}≠{can_id})"
        return out

    out["score"] = title_score(title, page_title)

    # ② 기사 번호가 같으면 제목이 조금 달라도 같은 기사다
    if src_id and can_id and src_id == can_id and out["score"] >= 0.35:
        out["verified"] = True
        out["reason"] = "id_match"
        return out

    # ③ 제목 대조
    if out["score"] >= TITLE_PASS:
        out["verified"] = True
        out["reason"] = "title_match"
        return out

    if not page_title:
        out["reason"] = "no_page_title"        # 제목을 못 읽었으면 '확인 못 함' = 탈락
    else:
        out["reason"] = "title_mismatch"
    return out


# ── 본문 뽑기 (bs4 없이, 표준 라이브러리만) ───────────────────────────────
# 서버에 파이썬이 여러 개(시스템 python3 / 여러 venv)라 bs4·feedparser 가 있는 것도
# 없는 것도 있다. 어느 걸로 실행해도 돌아가게 하려고 표준 라이브러리 판을 둔다.

# 통째로 버릴 태그 — 본문이 아니라 광고·메뉴·관련기사 영역
_JUNK_TAGS = {"script", "style", "aside", "nav", "footer", "header", "iframe",
              "ins", "noscript", "form", "button", "figure", "select"}
# class/id 에 이런 낱말이 있으면 '다른 기사 목록'일 가능성이 높다 → 버린다
_JUNK_WORDS = ("related", "relate", "linknews", "articlerel", "newsrel", "recommend",
               "mostview", "popular", "banner", "sns", "share", "comment", "reply",
               "copyright", "gnb", "lnb", "breadcrumb", "tag", "subscribe")
# class/id 에 이런 낱말이 있으면 '본문 영역'이다 → 여기 글을 우선 쓴다
_BODY_WORDS = ("arttext", "arttxt", "newscntdetail", "newscnt", "articletxt",
               "articlebody", "articleview", "artview", "newsbody", "articlecontent",
               "articletext", "storybody")
# 닫는 태그가 없는 태그들 (스택이 꼬이지 않게 따로 관리)
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
         "link", "meta", "param", "source", "track", "wbr"}


def _ident(attrs: dict) -> str:
    """class 와 id 를 합쳐 기호를 뗀 문자열 — 'art_txt' 와 'art-txt' 를 같게 본다."""
    raw = (attrs.get("class", "") + " " + attrs.get("id", "")).lower()
    return re.sub(r"[^a-z0-9]", "", raw)


class BodyParser(HTMLParser):
    """기사 본문 글자만 모으는 파서.

    - 광고·메뉴·관련기사 영역(_JUNK_*)에 들어가면 그 안의 글은 통째로 무시한다.
    - 본문 영역(_BODY_WORDS)에 들어가면 거기서 모은 글을 1순위로 쓴다.
    - 아무것도 못 찾으면 <p> 안의 글을 2순위로 쓴다.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []      # 열려 있는 태그 이름
        self.skip_at: list[int] = []    # 버리는 구간이 시작된 깊이
        self.body_at: list[int] = []    # 본문 구간이 시작된 깊이
        self.body: list[str] = []       # 본문 영역에서 모은 글
        self.paras: list[str] = []      # <p> 안에서 모은 글
        self.in_p = 0

    # 지금 위치가 '버리는 구간' 안인가
    @property
    def skipping(self) -> bool:
        return bool(self.skip_at)

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if tag == "br" and not self.skipping:
                self._add(" ")
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        self.stack.append(tag)
        depth = len(self.stack)
        ident = _ident(a)
        if tag in _JUNK_TAGS or any(w in ident for w in _JUNK_WORDS):
            self.skip_at.append(depth)
        elif any(w in ident for w in _BODY_WORDS):
            self.body_at.append(depth)
        if tag == "p" and not self.skipping:
            self.in_p += 1

    def handle_endtag(self, tag):
        if tag in _VOID or tag not in self.stack:
            return
        # 닫히지 않은 태그가 있어도 견디게, 해당 태그까지 되감는다
        while self.stack:
            top = self.stack.pop()
            depth = len(self.stack) + 1
            while self.skip_at and self.skip_at[-1] >= depth:
                self.skip_at.pop()
            while self.body_at and self.body_at[-1] >= depth:
                self.body_at.pop()
            if top in ("p", "div", "li", "h1", "h2", "h3", "br"):
                self._add(" ")          # 문단 끝 — 문장이 '…밝혔다.회사' 로 붙는 걸 막는다
            if top == "p" and self.in_p:
                self.in_p -= 1
            if top == tag:
                break

    def _add(self, text: str) -> None:
        if self.body_at:
            self.body.append(text)
        if self.in_p:
            self.paras.append(text)

    def handle_data(self, data):
        if self.skipping or not data.strip():
            return
        self._add(data)


def extract_body(html: str, limit: int = 1500) -> str:
    """HTML → 기사 본문 글자. bs4 가 없어도 동작한다.

    limit 글자를 넘으면 뒤를 자르고 '...' 을 붙인다(브리핑엔 앞부분이면 충분).
    """
    if not html:
        return ""
    p = BodyParser()
    try:
        p.feed(html)
    except Exception:
        pass                      # 깨진 HTML 이어도 그때까지 모은 건 쓴다
    text = "".join(p.body).strip() or "".join(p.paras).strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text).strip()
    return text[:limit] + "..." if len(text) > limit else text


# ── news_data.json 통째로 걸러내기 ────────────────────────────────────────
def verify_json(path: str, write: bool = False, strict_host: bool = True) -> int:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    arts = data if isinstance(data, list) else data.get("articles", [])

    kept, dropped = [], []
    for art in arts:
        r = verify(art.get("link", ""), art.get("title", ""),
                   art.get("outlet", ""), strict_host=strict_host)
        art["verified"] = r["verified"]
        art["verify_reason"] = r["reason"]
        art["verify_score"] = r["score"]
        art["page_title"] = r["page_title"]
        if r["verified"]:
            # 확인된 최종 주소로 링크를 바꿔준다(추적 파라미터·리다이렉트 제거 효과)
            art["link"] = r["canonical_url"] or r["final_url"]
            kept.append(art)
        else:
            dropped.append(art)
        mark = "✅" if r["verified"] else "❌"
        print(f"{mark} [{r['reason']:<28}] score={r['score']:.2f}  {art.get('title','')[:46]}",
              file=sys.stderr)

    print(f"\n확인됨 {len(kept)}건 / 버림 {len(dropped)}건", file=sys.stderr)

    if write:
        if isinstance(data, list):
            data = {"articles": kept}
        else:
            data["articles"] = kept
            data["rejected"] = dropped          # 왜 버렸는지 남겨 둔다(디버깅용)
            data["verified_at"] = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"저장 완료: {path}", file=sys.stderr)

    return 0 if kept else 2


def main() -> int:
    ap = argparse.ArgumentParser(description="기사 링크가 정말 그 기사인지 확인한다")
    ap.add_argument("--url", help="확인할 기사 주소")
    ap.add_argument("--title", default="", help="그 기사라고 알고 있는 제목")
    ap.add_argument("--outlet", default="", help="언론사(매일경제/한국경제) — 도메인 검사에 사용")
    ap.add_argument("--json", dest="json_path", help="news_data.json 을 통째로 검사")
    ap.add_argument("--write", action="store_true", help="--json 과 함께: 확인된 기사만 남겨 저장")
    ap.add_argument("--no-strict-host", action="store_true",
                    help="언론사 도메인 검사 생략(다른 매체 기사 확인용)")
    a = ap.parse_args()

    strict = not a.no_strict_host
    if a.json_path:
        return verify_json(a.json_path, write=a.write, strict_host=strict)
    if not a.url:
        ap.print_help()
        return 1

    r = verify(a.url, a.title, a.outlet, strict_host=strict)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
