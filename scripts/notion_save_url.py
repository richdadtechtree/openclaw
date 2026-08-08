#!/usr/bin/env python3
"""
notion_save_url.py — 웹주소(URL) 하나를 받아 그 페이지의 제목/웹주소/본문을 노션 DB에 저장.

슬랙에서 사용자가 링크를 보내면 뚜떵또가 이 스크립트를 실행한다.
저장되는 것:
  - 제목  : 내용 제목(og:title/JSON-LD headline/<title>). 사이트 이름(스레드 등)만
            나오면 본문 첫 줄을 제목으로 대체.
  - 웹주소: 본문 맨 위 북마크 블록 + (DB에 url 타입 칸이 있으면) 해당 속성.
  - 본문  : 여러 소스(JSON-LD·article/main·og:description)에서 가장 완전한 텍스트를
            골라 링크 아래에 붙인다.

사용:
  python3 scripts/notion_save_url.py <URL> [--to ai|book|article|tip] [YYYY-MM-DD]
  - --to 로 저장할 표를 고른다(기본 ai). 한글 별칭: 책=book, 좋은글=article, 꿀팁=tip.

저장 대상(.env) — 카테고리별 대상 DB ID:
  ai      : NOTION_BRIEFING_TARGET (또는 하위호환 NOTION_BRIEFING_DB)  → AI꿀팁 표
  book    : NOTION_BOOK_TARGET                                        → 책 추천 표
  article : NOTION_ARTICLE_TARGET                                     → 좋은글 표
  tip     : NOTION_TIP_TARGET                                         → 꿀팁 표
필요 (.env): NOTION_TOKEN + 위 카테고리 대상 중 사용하는 것.
"""
import html
import json
import os
import re
import sys
from datetime import datetime

import requests

# notion_push.py 의 저장 로직/상수를 재사용 (같은 폴더).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notion_push as np  # noqa: E402

# 요청 UA 후보: SNS(스레드/인스타/X 등)는 일반 브라우저엔 빈 껍데기를 주고,
# 링크 미리보기용 '크롤러 UA' 에게만 og 태그(게시물 텍스트)를 내려주는 경우가 많다.
# → 크롤러 UA 를 먼저 시도하고, og:description 이 담긴 응답을 채택한다.
UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
UAS = [
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Mozilla/5.0 (compatible; Twitterbot/1.0)",
    "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
    UA_BROWSER,
]
MAX_BODY_CHARS = 15000  # 본문 저장 상한(너무 긴 페이지 방지)

# 게시물 자체가 곧 내용인 SNS 호스트 → 제목은 본문(게시물) 첫 줄을 쓴다.
SNS_HOSTS = ("threads.com", "threads.net", "instagram.com", "x.com",
             "twitter.com", "facebook.com", "tiktok.com")

# 사이트 이름만 나오는(=내용 제목이 아닌) 흔한 값들. 이러면 본문 첫 줄을 제목으로 쓴다.
GENERIC_TITLES = {
    "threads", "thread", "스레드", "instagram", "인스타그램", "facebook", "페이스북",
    "x", "twitter", "트위터", "youtube", "유튜브", "naver", "네이버", "tiktok", "틱톡",
    "블로그", "blog", "home", "홈",
}


def _get(url, ua):
    r = requests.get(url, headers={"User-Agent": ua,
                                   "Accept-Language": "ko,en;q=0.8"}, timeout=30)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def fetch(url):
    """URL 을 받아 (제목, 본문텍스트) 반환. 여러 UA 로 시도해 og 본문이 가장 많은 응답 채택."""
    best_doc, best_score = None, -1
    last_err = None
    for ua in UAS:
        try:
            doc = _get(url, ua)
        except Exception as e:
            last_err = e
            continue
        score = len(collect_metas(doc).get("og:description", "") or "")
        if score > best_score:
            best_doc, best_score = doc, score
        if score > 0:            # 게시물 텍스트를 얻었으면 충분
            break
    if best_doc is None:
        raise last_err or RuntimeError("요청 실패")

    metas = collect_metas(best_doc)
    ld = collect_jsonld(best_doc)
    body = pick_body(best_doc, metas, ld)
    is_sns = any(h in url.lower() for h in SNS_HOSTS)
    title = pick_title(best_doc, metas, ld, body, is_sns=is_sns) or url
    return title, body


def collect_metas(doc):
    """<meta> 의 property/name → content 매핑(og:*, twitter:*, description 등)."""
    metas = {}
    for m in re.finditer(r"<meta\s+([^>]+?)/?>", doc, re.I | re.S):
        attrs = dict((k.lower(), v) for k, v in
                     re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', m.group(1)))
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            metas[key.lower()] = html.unescape(attrs["content"]).strip()
    return metas


def collect_jsonld(doc):
    """application/ld+json 블록들을 파싱해 dict 리스트로."""
    out = []
    for m in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            doc, re.I | re.S):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for d in items:
            if isinstance(d, dict):
                out.append(d)
                if isinstance(d.get("@graph"), list):
                    out.extend(x for x in d["@graph"] if isinstance(x, dict))
    return out


def _is_generic(t):
    tt = re.sub(r"[\W_]+", " ", t or "").strip().lower()
    return (not tt) or tt in GENERIC_TITLES or len(tt) <= 2


def _clean_html_text(seg):
    seg = re.sub(r"<(script|style|noscript|nav|header|footer|aside|form|svg)[^>]*>.*?</\1>",
                 " ", seg, flags=re.I | re.S)
    seg = re.sub(r"(?i)</(p|div|br|li|h[1-6]|tr|section|article)>", "\n", seg)
    seg = re.sub(r"<[^>]+>", " ", seg)
    seg = html.unescape(seg)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in seg.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def pick_body(doc, metas, ld):
    """여러 소스에서 본문 후보를 모아 가장 완전한(긴) 것을 고른다."""
    cands = []
    # 1) JSON-LD 의 구조화된 본문
    for d in ld:
        for k in ("articleBody", "text", "description", "caption", "headline"):
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                cands.append(v.strip())
    # 2) article/main 본문
    m = (re.search(r"<article[^>]*>(.*?)</article>", doc, re.I | re.S)
         or re.search(r"<main[^>]*>(.*?)</main>", doc, re.I | re.S))
    if m:
        cands.append(_clean_html_text(m.group(1)))
    # 3) 메타 설명(SNS는 여기 본문이 담기는 경우가 많음)
    for k in ("og:description", "twitter:description", "description"):
        if metas.get(k):
            cands.append(metas[k])
    # 4) 그래도 없으면 페이지 전체 텍스트
    if not cands:
        cands.append(_clean_html_text(doc))
    body = max(cands, key=len) if cands else ""
    return body[:MAX_BODY_CHARS]


def _first_line_title(body):
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if first:
        return first[:80] + ("…" if len(first) > 80 else "")
    return None


def pick_title(doc, metas, ld, body, is_sns=False):
    """내용 제목을 고른다. SNS이거나 사이트 이름만 나오면 본문(게시물) 첫 줄로."""
    # SNS 게시물은 og:title 이 작성자명이라 내용 제목이 아님 → 본문 첫 줄 우선.
    if is_sns:
        t = _first_line_title(body)
        if t and not _is_generic(t):
            return t
    cands = []
    for d in ld:
        for k in ("headline", "name"):
            if isinstance(d.get(k), str):
                cands.append(d[k])
    cands += [metas.get("og:title"), metas.get("twitter:title")]
    m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
    if m:
        cands.append(html.unescape(re.sub(r"\s+", " ", m.group(1))).strip())
    for c in cands:
        if c and not _is_generic(c):
            return c.strip()
    # 내용 제목이 없으면 본문 첫 줄(최대 80자)을 제목으로.
    t = _first_line_title(body)
    if t:
        return t
    # 마지막 폴백: 그래도 있던 후보 아무거나.
    return next((c.strip() for c in cands if c), None)


def sanitize_url(raw):
    """붙여넣기 과정에서 붙는 포장 제거: 공백·꺾쇠·따옴표·Slack 링크표기(<url|텍스트>)."""
    u = (raw or "").strip()
    u = u.strip("<>").strip().strip("\"'` ")   # <...>, 따옴표, 백틱
    if "|" in u:                                # Slack 형식 <url|표시텍스트>
        u = u.split("|", 1)[0].strip()
    # 텍스트 안에 URL이 섞여 있으면 http(s) 부분만 추출.
    m = re.search(r"https?://\S+", u, re.I)
    if m:
        u = m.group(0).strip("<>\"'` )]")
    elif not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    return u


# 카테고리 → (.env 대상 변수 후보들, 표시이름). 첫 번째로 값이 있는 변수를 사용.
CATEGORIES = {
    "ai": (("NOTION_BRIEFING_TARGET", "NOTION_BRIEFING_DB"), "AI꿀팁"),
    "book": (("NOTION_BOOK_TARGET",), "책 추천"),
    "article": (("NOTION_ARTICLE_TARGET",), "좋은글"),
    "tip": (("NOTION_TIP_TARGET",), "꿀팁"),
}
# 한글/별칭 → 표준 카테고리 키
CATEGORY_ALIASES = {
    "ai": "ai", "ai꿀팁": "ai", "aitip": "ai",
    "book": "book", "책": "book", "책추천": "book", "도서": "book",
    "article": "article", "좋은글": "article", "글": "article", "좋은": "article",
    "tip": "tip", "꿀팁": "tip", "팁": "tip",
}


def resolve_category(name):
    key = CATEGORY_ALIASES.get((name or "").strip().lower())
    return key or "ai"


def target_for(category):
    """카테고리의 대상 DB ID 를 .env 에서 찾는다. 없으면 (None, 표시이름)."""
    env_vars, label = CATEGORIES[category]
    for v in env_vars:
        val = os.getenv(v)
        if val:
            return val, label
    return None, label


def main():
    args = sys.argv[1:]
    category = "ai"
    if "--to" in args:
        i = args.index("--to")
        if i + 1 < len(args):
            category = resolve_category(args[i + 1])
            del args[i:i + 2]
        else:
            del args[i:i + 1]

    if not args or not args[0].strip():
        print("사용법: python3 notion_save_url.py <URL> [--to ai|book|article] [YYYY-MM-DD]")
        sys.exit(1)
    url = sanitize_url(args[0])
    date_str = args[1] if len(args) > 1 else datetime.now().strftime("%Y-%m-%d")

    target, label = target_for(category)
    if not target:
        env_name = CATEGORIES[category][0][0]
        print(f"[Error] '{label}' 표의 대상 ID 가 없습니다. .env 에 {env_name}=<database_id> 를 설정하세요.")
        sys.exit(1)

    try:
        title, body = fetch(url)
    except Exception as e:
        print(f"[Error] URL 가져오기 실패: {e}")
        sys.exit(1)

    blocks = np.md_to_blocks(body) if body else []
    ok = np.create_page(title, date_str, None, blocks, url=url, target=target)
    if ok:
        print(f"✅ [{label}] 노션 저장 성공! 제목: {title}")
    else:
        print(f"❌ [{label}] 노션 저장 실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
