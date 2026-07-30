import os
import re
import sys
import html
import json
import time
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup
import feedparser


def _load_env():
    """~/.openclaw/.env 를 명시적으로 읽어 os.environ 에 채운다(이미 있으면 유지)."""
    candidates = [
        Path(__file__).resolve().parents[1] / ".env",   # ~/.openclaw/.env
        Path("~/.openclaw/.env").expanduser(),
    ]
    for p in candidates:
        try:
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                break
        except Exception:
            pass


_load_env()

# ─────────────────────────────────────────────────────────────
# 카테고리별 RSS 피드 (매일경제 + 한국경제)
# 목표 비중: 부동산 4 / 주식 2 / 금융 2 / 경제 2 = 총 10건
# (모두 기존 검증된 메인 섹션 피드)
# ─────────────────────────────────────────────────────────────
CATEGORY_FEEDS = {
    "부동산": [
        ("매일경제", "https://www.mk.co.kr/rss/50300009/"),
        ("한국경제", "https://www.hankyung.com/feed/realestate"),
    ],
    "주식": [
        ("매일경제", "https://www.mk.co.kr/rss/50200011/"),   # 증권
    ],
    "금융": [
        ("한국경제", "https://www.hankyung.com/feed/finance"),  # 금융
    ],
    "경제": [
        ("매일경제", "https://www.mk.co.kr/rss/30100041/"),   # 경제
        ("한국경제", "https://www.hankyung.com/feed/economy"),
    ],
}

# 목표 비중 (총합 = 발송 기사 수)
TARGET_RATIO = {"부동산": 4, "주식": 2, "금융": 2, "경제": 2}

# 특정 카테고리가 목표에 못 미칠 때 채워 넣을 일반 풀 (총 10건 보장용)
GENERAL_FEEDS = [
    ("매일경제", "https://www.mk.co.kr/rss/30000001/"),   # 헤드라인
    ("매일경제", "https://www.mk.co.kr/rss/30300018/"),   # 국제
    ("한국경제", "https://www.hankyung.com/feed/international"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3"
}


def clean_text(text):
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    return " ".join([line for line in lines if line])


def norm_title(title):
    return clean_text(title).replace(" ", "")


def fetch_article_body(url):
    """Fetches the main text content of the news article."""
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        if res.encoding == 'ISO-8859-1':
            res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = [
            "#artText", ".art_txt", "#news_cnt_detail", ".news_cnt_detail_wrap",
            "#articletxt", ".article-body", "#news-body", ".news-body", ".news_cnt"
        ]
        body_text = ""
        for sel in selectors:
            elem = soup.select_one(sel)
            if elem:
                for s in elem(["script", "style", "iframe", "ins"]):
                    s.decompose()
                body_text = elem.get_text()
                break
        if not body_text:
            candidates = []
            for tag in soup.find_all(['div', 'section']):
                text_len = len(clean_text(tag.get_text()))
                if text_len > 200 and ('ad' not in tag.get('class', []) and 'footer' not in tag.get('class', [])):
                    candidates.append((tag, text_len))
            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)
                body_text = candidates[0][0].get_text()
        cleaned = clean_text(body_text)
        return cleaned[:1500] + "..." if len(cleaned) > 1500 else cleaned
    except Exception as e:
        print(f"Error fetching article body from {url}: {e}", file=sys.stderr)
        return ""


def parse_rss_feed(feed_url, outlet_name, max_hours=24):
    """Parses a single RSS feed and filters by time and strict outlet domain."""
    articles = []
    try:
        # 한경은 봇 요청을 403으로 막으므로, 브라우저 헤더 + Referer 로 요청한다.
        headers = dict(HEADERS)
        headers["Referer"] = "https://www.hankyung.com/" if outlet_name == "한국경제" else "https://www.mk.co.kr/"
        status = None
        try:
            res = requests.get(feed_url, headers=headers, timeout=12)
            status = res.status_code
            feed = feedparser.parse(res.content)
        except Exception as e:
            print(f"    · [{outlet_name}] 요청 오류 {feed_url}: {e}", file=sys.stderr)
            feed = feedparser.parse(feed_url)  # 최후의 수단
        print(f"    · [{outlet_name}] HTTP {status} entries={len(feed.entries)} {feed_url}", file=sys.stderr)
        now = datetime.now(timezone.utc)
        for entry in feed.entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            published = entry.get('published', '')
            if outlet_name == "매일경제" and "mk.co.kr" not in link:
                continue
            if outlet_name == "한국경제" and "hankyung.com" not in link:
                continue
            pub_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif published:
                try:
                    pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                except ValueError:
                    pass
            if pub_date and (now - pub_date) > timedelta(hours=max_hours):
                continue
            articles.append({
                "title": title,
                "link": link,
                "published": published,
                "pub_date_parsed": pub_date.isoformat() if pub_date else None,
                "outlet": outlet_name,
            })
    except Exception as e:
        print(f"Error parsing feed {feed_url}: {e}", file=sys.stderr)
    return articles


def collect_feeds(feed_list, seen, max_hours=24):
    """여러 피드에서 기사 수집(제목 중복 제거). category 태그는 호출측에서 붙인다."""
    out = []
    for outlet, url in feed_list:
        for art in parse_rss_feed(url, outlet, max_hours=max_hours):
            nt = norm_title(art["title"])
            if nt and nt not in seen:
                seen.add(nt)
                out.append(art)
    return out


def fetch_via_naver(keyword, site_domain, outlet_name, seen, count=4):
    """네이버 검색 API(뉴스)로 특정 매체 기사를 수집. originallink(원문 URL)를 그대로 링크로 쓴다.
    한경 직접 RSS가 403으로 막혀도, 네이버를 통해 '진짜 hankyung.com 링크'를 확보할 수 있다."""
    cid = os.getenv("NAVER_CLIENT_ID")
    csec = os.getenv("NAVER_CLIENT_SECRET")
    if not (cid and csec):
        return []
    out = []
    try:
        res = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
            params={"query": keyword, "display": 100, "sort": "date"},
            timeout=12,
        )
        if res.status_code != 200:
            print(f"    · [네이버API/{outlet_name}/{keyword}] HTTP {res.status_code} {res.text[:120]}", file=sys.stderr)
            return []
        for item in res.json().get("items", []):
            link = item.get("originallink", "") or item.get("link", "")
            if site_domain not in link:
                continue
            title = html.unescape(re.sub(r"<[^>]+>", "", item.get("title", ""))).strip()
            nt = norm_title(title)
            if not nt or nt in seen:
                continue
            seen.add(nt)
            out.append({
                "title": title,
                "link": link,
                "published": item.get("pubDate", ""),
                "pub_date_parsed": None,
                "outlet": outlet_name,
                "via": "naver",
            })
            if len(out) >= count:
                break
        print(f"    · [네이버API/{outlet_name}/{keyword}] {len(out)}건", file=sys.stderr)
    except Exception as ex:
        print(f"    · 네이버API 실패({outlet_name}/{keyword}): {ex}", file=sys.stderr)
    return out


def fetch_via_google_news(site_domain, keyword, outlet_name, seen, count=4):
    """직접 RSS가 막혔을 때(예: 한경 403) 구글뉴스 RSS로 해당 매체 기사를 우회 수집."""
    q = urllib.parse.quote(f"site:{site_domain} {keyword}")
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    out = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        feed = feedparser.parse(res.content)
        for e in feed.entries:
            nt = norm_title(e.get("title", ""))
            if not nt or nt in seen:
                continue
            seen.add(nt)
            out.append({
                "title": e.get("title", ""),
                "link": e.get("link", ""),   # news.google.com 리다이렉트(원문으로 연결됨)
                "published": e.get("published", ""),
                "pub_date_parsed": None,
                "outlet": outlet_name,
                "via": "google_news",
            })
            if len(out) >= count:
                break
        print(f"    · [구글뉴스 폴백/{outlet_name}/{keyword}] {len(out)}건", file=sys.stderr)
    except Exception as ex:
        print(f"    · 구글뉴스 폴백 실패({outlet_name}/{keyword}): {ex}", file=sys.stderr)
    return out


# 카테고리별 구글뉴스 검색 키워드 (직접 피드 실패 시 보충용)
CATEGORY_KEYWORDS = {"부동산": "부동산", "주식": "증권 주식", "금융": "금융", "경제": "경제"}


def main():
    print("Starting news fetcher (category ratio mode)...")
    seen = set()

    # 1) 카테고리별 후보 수집
    pools = {}          # category -> [articles]
    for category, feeds in CATEGORY_FEEDS.items():
        target = TARGET_RATIO[category]
        arts = collect_feeds(feeds, seen, max_hours=24)
        if len(arts) < target:  # 부족하면 48h로 완화
            arts += collect_feeds(feeds, seen, max_hours=48)
        # 직접 피드가 부족하면(예: 한경 403) 보충한다.
        if len(arts) < target:
            kw = CATEGORY_KEYWORDS.get(category, category)
            # 1순위: 네이버 API — 원문(hankyung.com 등) 직접 링크 확보
            for dom, outlet in (("hankyung.com", "한국경제"), ("mk.co.kr", "매일경제")):
                if len(arts) >= target:
                    break
                arts += fetch_via_naver(kw, dom, outlet, seen, count=target - len(arts) + 2)
            # 2순위: 구글뉴스 (네이버 키가 없거나 부족할 때)
            for dom, outlet in (("hankyung.com", "한국경제"), ("mk.co.kr", "매일경제")):
                if len(arts) >= target:
                    break
                arts += fetch_via_google_news(dom, kw, outlet, seen, count=4)
        for a in arts:
            a["category"] = category
        pools[category] = arts
        print(f"  [{category}] 후보 {len(arts)}건")

    # 2) 백필용 일반 풀
    general = collect_feeds(GENERAL_FEEDS, seen, max_hours=48)
    for a in general:
        a["category"] = "기타"

    # 3) 목표 비중대로 선별 + 부족분 백필
    selected = []
    leftovers = []
    for category, target in TARGET_RATIO.items():
        arts = pools.get(category, [])
        selected.extend(arts[:target])
        leftovers.extend(arts[target:])
    total_target = sum(TARGET_RATIO.values())
    backfill = leftovers + general
    i = 0
    while len(selected) < total_target and i < len(backfill):
        selected.append(backfill[i])
        i += 1

    # 4) 선별된 기사 본문 수집
    results = {"fetched_at": datetime.now(timezone.utc).isoformat(), "articles": []}
    for idx, art in enumerate(selected):
        print(f"[{art['category']}/{art['outlet']}] body {idx+1}/{len(selected)}: {art['title']}")
        body = fetch_article_body(art["link"])
        art["content"] = body if body else "본문 내용을 가져오는 데 실패했습니다."
        results["articles"].append(art)
        time.sleep(0.5)

    # 5) 저장 + 카테고리 요약
    output_path = os.path.join(os.path.dirname(__file__), "news_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    counts = {}
    for a in results["articles"]:
        counts[a["category"]] = counts.get(a["category"], 0) + 1
    print(f"완료: 총 {len(results['articles'])}건 저장 → {output_path}")
    print(f"카테고리 분포: {counts}  (목표 {TARGET_RATIO})")


if __name__ == "__main__":
    main()
