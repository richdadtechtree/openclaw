import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

# 링크가 정말 그 기사인지 확인해 주는 도구(표준 라이브러리만 사용).
# scripts/ 는 workspace/ 의 형제 폴더라 경로를 직접 붙여 준다.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import verify_article_url as verifier

# ⚠️ 이 서버엔 파이썬이 여러 개다(시스템 python3, 여러 venv). 어떤 것엔 requests·bs4·
#    feedparser 가 있고 어떤 것엔 없다. 그래서 "있으면 쓰고, 없으면 표준 라이브러리로"
#    돌아가게 만든다. 어느 파이썬으로 실행해도 ModuleNotFoundError 없이 동작한다.
try:
    import requests
except ImportError:
    requests = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
try:
    import feedparser
except ImportError:
    feedparser = None

if not (requests and BeautifulSoup and feedparser):
    missing = [n for n, m in (("requests", requests), ("bs4", BeautifulSoup),
                              ("feedparser", feedparser)) if not m]
    print(f"[안내] {', '.join(missing)} 없이 표준 라이브러리로 실행합니다(결과는 동일).",
          file=sys.stderr, flush=True)

# RSS URLs config
FEEDS = {
    "매일경제": [
        "https://www.mk.co.kr/rss/30000001/",  # 헤드라인
        "https://www.mk.co.kr/rss/30100041/",  # 경제
        "https://www.mk.co.kr/rss/50200011/",  # 증권
        "https://www.mk.co.kr/rss/50300009/",  # 부동산
        "https://www.mk.co.kr/rss/30300018/"   # 국제
    ],
    # ⚠️ 한국경제는 2026-09-17 실행에서 all-news 가 0건이었다(주소가 막혔거나 바뀐 듯).
    #    그래서 후보를 여러 개 두고 **기사가 나오는 주소를 쓴다**. 안 되는 주소는
    #    조용히 건너뛰므로 손해가 없다. 어느 게 살아 있는지는 --probe 로 확인한다.
    "한국경제": [
        "https://www.hankyung.com/feed/all-news",
        "https://www.hankyung.com/feed/economy",
        "https://www.hankyung.com/feed/finance",
        "https://www.hankyung.com/feed/realestate",
        "https://www.hankyung.com/feed/stock",
    ]
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3"
}

def clean_text(text):
    if not text:
        return ""
    # Remove excessive spaces and newlines
    lines = [line.strip() for line in text.splitlines()]
    return " ".join([line for line in lines if line])

# 매경/한경 기사 URL 경로의 섹션 슬러그 → 한글 장르 매핑
# (예: https://www.mk.co.kr/news/business/12129186 → business → 기업)
SECTION_GENRE_MAP = {
    "economy": "경제",
    "business": "기업",
    "company": "기업",
    "stock": "증권",
    "securities": "증권",
    "money": "금융",
    "finance": "금융",
    "realestate": "부동산",
    "estate": "부동산",
    "land": "부동산",
    "society": "사회",
    "world": "국제",
    "international": "국제",
    "politics": "정치",
    "it": "IT·과학",
    "science": "IT·과학",
    "digital": "IT·과학",
    "culture": "문화",
    "sports": "스포츠",
    "entertain": "연예",
    "opinion": "오피니언",
    "health": "건강",
}

# 기사처럼 생겼지만 '뉴스'가 아닌 것들. 브리핑 자리를 잡아먹고 시간만 쓴다.
# (실제로 매경 헤드라인 RSS 에 "오늘의 운세 2026년 9월 18일" 이 들어와 1순위로 뽑혔다)
# ⚠️ 괄호·고정 문구로 못박는다. '인사' 같은 낱말 하나로 거르면 멀쩡한 기사가 날아간다.
JUNK_TITLE_PATTERNS = (
    "오늘의 운세", "[운세]", "띠별 운세", "별자리 운세",
    "[부고]", "[인사]", "[동정]", "[포토]", "[사진]", "[만평]", "[카드뉴스]",
    "오늘의 날씨", "[날씨]", "로또 ", "[오늘의 매경]", "[알림]", "[정정보도]",
)


def is_junk_title(title):
    """뉴스가 아닌 글이면 True."""
    t = (title or "").strip()
    return any(pat in t for pat in JUNK_TITLE_PATTERNS)


def derive_genre(url):
    """기사 URL 경로에서 섹션 슬러그를 뽑아 한글 장르로 변환한다.
    확실히 매핑되지 않으면 (섹션 슬러그, None)을 돌려주고,
    라벨은 AI가 본문 내용으로 판단하도록 남긴다."""
    try:
        path = urllib.parse.urlparse(url).path.lower()
    except Exception:
        return None, None
    parts = [p for p in path.split("/") if p]
    # 매경: /news/<section>/<id> , 한경: /<section>/... 또는 /article/...
    slug = None
    for i, p in enumerate(parts):
        if p == "news" and i + 1 < len(parts):
            slug = parts[i + 1]
            break
    if slug is None and parts:
        # 한경 등: 첫 경로 조각이 섹션인 경우가 많음
        slug = parts[0]
    genre = SECTION_GENRE_MAP.get(slug) if slug else None
    return slug, genre

def fetch_article_body(url, html=None):
    """기사 본문 글자만 뽑아낸다.

    html 을 넘겨주면 **새로 받지 않고 그걸 쓴다.**
    (검증 단계에서 이미 같은 페이지를 받아뒀기 때문 — 두 번 받으면 시간이 2배 든다.)
    """
    try:
        if html is None:
            if requests is not None:
                res = requests.get(url, headers=HEADERS, timeout=8)
                res.raise_for_status()
                # Check encoding
                if res.encoding == 'ISO-8859-1':
                    res.encoding = res.apparent_encoding
                html = res.text
            else:
                _, html, err = verifier.fetch(url)     # 표준 라이브러리로 받기
                if err:
                    raise RuntimeError(err)

        if BeautifulSoup is None:
            # bs4 가 없으면 표준 라이브러리 추출기 사용(광고·관련기사 제거는 동일하게 한다)
            return verifier.extract_body(html)

        soup = BeautifulSoup(html, 'html.parser')

        # ⚠️ 먼저 '다른 기사'가 섞여 있는 영역을 통째로 들어낸다.
        #    관련기사·추천기사·많이 본 뉴스 박스가 본문에 딸려 들어오면
        #    AI 가 엉뚱한 기사를 요약해 버린다(= '엉뚱한 기사' 사고의 한 원인).
        for sel in ("aside", "nav", "footer", "header", "script", "style", "iframe", "ins",
                    ".related", ".relate", ".link_news", ".article_rel", ".news_rel",
                    "#relatedNews", ".recommend", ".most_view", ".ad", ".banner", ".sns"):
            for junk in soup.select(sel):
                junk.decompose()

        # Selectors for main article body
        selectors = [
            "#artText", ".art_txt", "#news_cnt_detail", ".news_cnt_detail_wrap", 
            "#articletxt", ".article-body", "#news-body", ".news-body", ".news_cnt"
        ]
        
        body_text = ""
        for sel in selectors:
            elem = soup.select_one(sel)
            if elem:
                # Remove script/style tags from body
                for s in elem(["script", "style", "iframe", "ins"]):
                    s.decompose()
                body_text = elem.get_text()
                break
                
        if not body_text:
            # Fallback: Find the div with the most paragraphs or long text
            candidates = []
            for tag in soup.find_all(['article', 'div', 'section']):
                text_len = len(clean_text(tag.get_text()))
                if text_len <= 200:
                    continue
                if 'ad' in tag.get('class', []) or 'footer' in tag.get('class', []):
                    continue
                # 링크 글자가 30% 를 넘으면 본문이 아니라 '기사 목록'이다 → 버린다.
                link_len = sum(len(clean_text(a.get_text())) for a in tag.find_all('a'))
                if link_len / text_len > 0.3:
                    continue
                candidates.append((tag, text_len))
            if candidates:
                # Sort by text length descending
                candidates.sort(key=lambda x: x[1], reverse=True)
                body_text = candidates[0][0].get_text()
                
        cleaned = clean_text(body_text)
        return cleaned[:1500] + "..." if len(cleaned) > 1500 else cleaned
    except Exception as e:
        print(f"Error fetching article body from {url}: {e}", file=sys.stderr)
        return ""

def _parse_rss_stdlib(feed_url):
    """feedparser 없이 RSS 를 읽는다(표준 라이브러리만).

    feedparser 의 entry 와 같은 모양(dict)으로 돌려주므로 아래 코드는 그대로 쓴다.
    pubDate 는 RFC822 형식('Wed, 17 Sep 2026 06:00:00 +0900')이라
    email 모듈의 parsedate_to_datetime 으로 해석한다.
    """
    _, xml_text, err = verifier.fetch(feed_url)
    if err or not xml_text:
        print(f"RSS 읽기 실패 {feed_url}: {err}", file=sys.stderr)
        return []
    return _parse_rss_stdlib_from_text(xml_text, feed_url)


def _parse_rss_stdlib_from_text(xml_text, feed_url=""):
    """이미 받아온 RSS 글자 → 기사 목록. (--probe 와 공용)"""
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"RSS 형식 오류 {feed_url}: {e}", file=sys.stderr)
        return []
    for item in root.iter("item"):
        def txt(tag):
            el = item.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        published = txt("pubDate")
        parsed = None
        if published:
            try:
                dt = parsedate_to_datetime(published)
                # tz 정보가 없으면 UTC 로 본다(비교할 때 터지지 않게)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed = dt.astimezone(timezone.utc).timetuple()[:6]
            except Exception:
                parsed = None
        entries.append({"title": txt("title"), "link": txt("link"),
                        "published": published, "published_parsed": parsed})
    return entries


def parse_rss_feed(feed_url, outlet_name, max_hours=24):
    """Parses a single RSS feed and filters by time and strict outlet domain."""
    articles = []
    try:
        if feedparser is not None:
            feed = feedparser.parse(feed_url)
            # 비어 있으면 원문 XML 을 직접 받아 다시 시도
            if not feed.entries and requests is not None:
                res = requests.get(feed_url, headers=HEADERS, timeout=10)
                feed = feedparser.parse(res.content)
            entries = feed.entries
        else:
            entries = _parse_rss_stdlib(feed_url)

        now = datetime.now(timezone.utc)

        for entry in entries:
            title = entry.get('title', '')
            link = entry.get('link', '')
            published = entry.get('published', '')
            
            # Domain check
            if outlet_name == "매일경제" and "mk.co.kr" not in link:
                continue
            if outlet_name == "한국경제" and "hankyung.com" not in link:
                continue
            
            # Convert published time to datetime object
            pub_date = None
            # feedparser 는 객체, 표준 라이브러리 판은 dict — 둘 다 .get 으로 읽힌다
            parsed = entry.get('published_parsed') if hasattr(entry, 'get') else None
            if parsed:
                pub_date = datetime(*parsed[:6], tzinfo=timezone.utc)
            elif published:
                try:
                    # Try basic ISO parsing
                    pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                except ValueError:
                    pass
            
            # If publication date cannot be parsed, allow it but mark as recent
            if pub_date:
                time_diff = now - pub_date
                if time_diff > timedelta(hours=max_hours):
                    continue  # Skip older articles
            
            if is_junk_title(title):
                continue          # 운세·부고·포토 등은 아예 후보에서 뺀다

            section_slug, genre = derive_genre(link)
            articles.append({
                "title": title,
                "link": link,
                "published": published,
                "pub_date_parsed": pub_date.isoformat() if pub_date else None,
                "section": section_slug,
                "genre": genre
            })
    except Exception as e:
        print(f"Error parsing feed {feed_url}: {e}", file=sys.stderr)
    return articles

# ⚠️ 2026-09-17 제거: 구글뉴스(news.google.com/rss/...) 폴백.
#    구글뉴스가 주는 주소는 언론사 주소가 아니라 구글의 중계 주소라서,
#    눌러 보면 다른 기사나 구글뉴스 화면으로 빠진다(실제 사고 원인).
#    RSS 만으로도 매체당 5건은 충분히 모이므로 폴백 자체를 없앴다.
#    혹시 링크가 섞여 들어와도 아래 verify 단계에서 'relay_link' 로 걸러진다.


def probe():
    """어느 RSS 주소가 살아 있는지 점검한다 (--probe).

    한국경제처럼 '0건' 이 나올 때 원인을 눈으로 확인하려고 만든 진단 도구.
    주소마다 HTTP 상태 · 받은 크기 · 기사 수 · 첫 기사 링크를 보여준다.
    """
    print("RSS 주소 점검 — 어느 것이 살아 있는지 봅니다\n", flush=True)
    for outlet, urls in FEEDS.items():
        print(f"■ {outlet}")
        for url in urls:
            _, text, err = verifier.fetch(url)
            if err:
                print(f"   ❌ {url}\n      → 접속 실패: {err}", flush=True)
                continue
            items = _parse_rss_stdlib_from_text(text, url)
            head = items[0]["link"] if items else "-"
            mark = "✅" if items else "⚠️ "
            print(f"   {mark} {url}\n      → {len(text):,}바이트, 기사 {len(items)}건, 첫 링크: {head[:70]}",
                  flush=True)
        print()
    print("기사 0건인 주소는 FEEDS 에서 빼거나 다른 주소로 바꾸면 됩니다.")
    return 0


def main():
    started = time.time()
    print("신문 기사 수집 시작 — 링크 검증까지 보통 20~40초 걸립니다.", flush=True)
    max_hours = 24
    results = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "articles": [],     # ✅ 링크가 제목과 일치하는 것으로 '확인된' 기사만 들어간다
        "rejected": []      # ❌ 왜 버렸는지 기록 (디버깅용 — AI 는 이 목록을 쓰면 안 된다)
    }
    
    # Track collected titles to prevent duplicates
    seen_titles = set()
    
    for outlet, urls in FEEDS.items():
        print(f"Fetching from {outlet}...")
        outlet_articles = []
        
        # ⚠️ 예전엔 피드를 순서대로 이어 붙이고 앞에서 6건을 잘랐다. 그러면 첫 피드
        #    (헤드라인)가 30건을 채워 **증권·부동산·경제 피드는 한 건도 못 들어왔다.**
        #    → 피드들을 **한 건씩 번갈아** 가져온다(라운드로빈). 분야가 골고루 섞인다.
        per_feed = []
        for url in urls:
            got = parse_rss_feed(url, outlet, max_hours=max_hours)
            if got:
                per_feed.append(got)
            print(f"  · {url.split('/')[-1] or url}: {len(got)}건", flush=True)

        for i in range(max(len(f) for f in per_feed) if per_feed else 0):
            for feed_arts in per_feed:
                if i >= len(feed_arts):
                    continue
                art = feed_arts[i]
                norm_title = clean_text(art["title"]).replace(" ", "")
                if norm_title not in seen_titles:
                    seen_titles.add(norm_title)
                    art["outlet"] = outlet
                    outlet_articles.append(art)
                    
        # If we couldn't find enough articles from RSS, relax time constraint
        if len(outlet_articles) < 5:
            print(f"Warning: Only found {len(outlet_articles)} articles from {outlet} within {max_hours}h. Relaxing time filter to 48 hours...")
            seen_titles_relaxed = set()
            relaxed_articles = []
            relaxed_per_feed = [g for g in
                                (parse_rss_feed(u, outlet, max_hours=48) for u in urls) if g]
            for i in range(max(len(f) for f in relaxed_per_feed) if relaxed_per_feed else 0):
                for feed_arts in relaxed_per_feed:
                    if i >= len(feed_arts):
                        continue
                    art = feed_arts[i]
                    norm_title = clean_text(art["title"]).replace(" ", "")
                    if norm_title not in seen_titles_relaxed:
                        seen_titles_relaxed.add(norm_title)
                        art["outlet"] = outlet
                        relaxed_articles.append(art)
            
            # Merge while avoiding duplicates
            for art in relaxed_articles:
                norm_title = clean_text(art["title"]).replace(" ", "")
                if norm_title not in seen_titles:
                    seen_titles.add(norm_title)
                    outlet_articles.append(art)
                    
        if len(outlet_articles) < 5:
            print(f"Note: {outlet} 에서 {len(outlet_articles)}건만 모았습니다(구글뉴스 폴백은 사용하지 않음).")

        # 검증에서 몇 건 탈락할 수 있으니 여유 있게 8건까지 후보로 둔다.
        selected_articles = outlet_articles[:10]   # 검증이 건당 0.1초라 넉넉히 본다

        # ★ 핵심: 링크가 정말 그 제목의 기사인지 한 건씩 확인한다.
        #    통과한 기사만 news_data.json 에 넣는다 → AI 는 확인된 것만 쓸 수 있다.
        kept = 0
        print(f"[{outlet}] 후보 {len(selected_articles)}건 — 링크가 진짜 그 기사인지 확인합니다"
              f"(한 건당 1~3초)", flush=True)
        for n, art in enumerate(selected_articles, 1):
            if kept >= 5:
                break
            t0 = time.time()
            # keep_html=True → 검증하며 받은 HTML 을 그대로 재활용(요청 횟수 절반)
            check = verifier.verify(art["link"], art["title"], outlet, keep_html=True)
            art["verified"] = check["verified"]
            art["verify_reason"] = check["reason"]
            art["verify_score"] = check["score"]
            art["page_title"] = check["page_title"]

            art.pop("html", None)                 # 결과 json 에 HTML 을 남기지 않는다

            if not check["verified"]:
                print(f"[{outlet}] {n}/{len(selected_articles)} ❌ 링크 불일치"
                      f"({check['reason']}) — 버림: {art['title'][:40]}",
                      file=sys.stderr, flush=True)
                art["outlet"] = outlet
                results["rejected"].append(art)
                continue

            # 확인된 '최종 주소'로 바꿔 둔다(리다이렉트·추적 파라미터 제거 효과)
            art["link"] = check["canonical_url"] or check["final_url"]
            print(f"[{outlet}] {n}/{len(selected_articles)} ✅ 확인"
                  f"({check['reason']}, {check['score']:.2f}, {time.time()-t0:.1f}초) "
                  f"{art['title'][:40]}", flush=True)
            body = fetch_article_body(art["link"], html=check.get("html"))
            art["content"] = body if body else "본문 내용을 가져오는 데 실패했습니다."
            results["articles"].append(art)
            kept += 1
            time.sleep(0.2)          # 서버 예의상 아주 짧게 (이제 요청이 절반이라 충분)
            
    # Save results to json
    output_path = os.path.join(os.path.dirname(__file__), "news_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"\n완료 ({time.time()-started:.0f}초). 확인된 기사 {len(results['articles'])}건 저장 "
          f"(링크 불일치로 버린 기사 {len(results['rejected'])}건) → {output_path}", flush=True)
    if not results["articles"]:
        print("⚠️ 확인된 기사가 한 건도 없습니다. 브리핑을 만들지 말고 이 사실을 먼저 알리세요.",
              file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    if "--probe" in sys.argv:
        sys.exit(probe())
    main()
