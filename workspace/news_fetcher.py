import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup
import feedparser

# RSS URLs config
FEEDS = {
    "매일경제": [
        "https://www.mk.co.kr/rss/30000001/",  # 헤드라인
        "https://www.mk.co.kr/rss/30100041/",  # 경제
        "https://www.mk.co.kr/rss/50200011/",  # 증권
        "https://www.mk.co.kr/rss/50300009/",  # 부동산
        "https://www.mk.co.kr/rss/30300018/"   # 국제
    ],
    "한국경제": [
        "https://www.hankyung.com/feed/economy",
        "https://www.hankyung.com/feed/finance",
        "https://www.hankyung.com/feed/realestate",
        "https://www.hankyung.com/feed/international"
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

def fetch_article_body(url):
    """Fetches the main text content of the news article."""
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        
        # Check encoding
        if res.encoding == 'ISO-8859-1':
            res.encoding = res.apparent_encoding
            
        soup = BeautifulSoup(res.text, 'html.parser')
        
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
            for tag in soup.find_all(['div', 'section']):
                paragraphs = tag.find_all('p', recursive=False)
                text_len = len(clean_text(tag.get_text()))
                if text_len > 200 and ('ad' not in tag.get('class', []) and 'footer' not in tag.get('class', [])):
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

def parse_rss_feed(feed_url, outlet_name, max_hours=24):
    """Parses a single RSS feed and filters by time and strict outlet domain."""
    articles = []
    try:
        # Use feedparser first
        feed = feedparser.parse(feed_url)
        
        # If feedparser fails or is empty, try requesting raw XML and parse it
        if not feed.entries:
            res = requests.get(feed_url, headers=HEADERS, timeout=10)
            feed = feedparser.parse(res.content)
            
        now = datetime.now(timezone.utc)
        
        for entry in feed.entries:
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
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
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
            
            articles.append({
                "title": title,
                "link": link,
                "published": published,
                "pub_date_parsed": pub_date.isoformat() if pub_date else None
            })
    except Exception as e:
        print(f"Error parsing feed {feed_url}: {e}", file=sys.stderr)
    return articles

def fetch_google_news_fallback(keyword, outlet_name, count=5):
    """Fallback search using Google RSS search feeds to gather recent articles with strict domain."""
    query = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    articles = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            link = entry.get('link', '')
            
            # Domain check
            if outlet_name == "매일경제" and "mk.co.kr" not in link:
                continue
            if outlet_name == "한국경제" and "hankyung.com" not in link:
                continue
                
            articles.append({
                "title": entry.get('title', ''),
                "link": link,
                "published": entry.get('published', '')
            })
            if len(articles) >= count:
                break
    except Exception as e:
        print(f"Error in Google News Fallback: {e}", file=sys.stderr)
    return articles


def main():
    print("Starting news fetcher...")
    max_hours = 24
    results = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "articles": []
    }
    
    # Track collected titles to prevent duplicates
    seen_titles = set()
    
    for outlet, urls in FEEDS.items():
        print(f"Fetching from {outlet}...")
        outlet_articles = []
        
        for url in urls:
            feed_articles = parse_rss_feed(url, max_hours=max_hours)
            for art in feed_articles:
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
            for url in urls:
                feed_articles = parse_rss_feed(url, max_hours=48)
                for art in feed_articles:
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
                    
        # If STILL less than 5, trigger fallback search
        if len(outlet_articles) < 5:
            fallback_needed = 5 - len(outlet_articles)
            print(f"Warning: Found only {len(outlet_articles)} articles from {outlet}. Fetching {fallback_needed} fallback articles via Google News...")
            fallback_query = f"site:mk.co.kr" if outlet == "매일경제" else f"site:hankyung.com"
            # Add general economy keywords to find relevant articles
            fallback_query += " 경제 OR 부동산 OR 증권"
            fallback_arts = fetch_google_news_fallback(fallback_query, count=fallback_needed * 2)
            
            for art in fallback_arts:
                norm_title = clean_text(art["title"]).replace(" ", "")
                if norm_title not in seen_titles:
                    seen_titles.add(norm_title)
                    art["outlet"] = outlet
                    outlet_articles.append(art)
                    if len(outlet_articles) >= 5:
                        break
                        
        # Take the top 5 most relevant/recent articles
        selected_articles = outlet_articles[:5]
        
        # Now fetch the body content for the selected articles
        for idx, art in enumerate(selected_articles):
            print(f"[{outlet}] Fetching body {idx+1}/5: {art['title']}")
            body = fetch_article_body(art["link"])
            art["content"] = body if body else "본문 내용을 가져오는 데 실패했습니다."
            results["articles"].append(art)
            # Sleep briefly to respect the servers
            time.sleep(0.5)
            
    # Save results to json
    output_path = os.path.join(os.path.dirname(__file__), "news_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"News fetching complete. Saved {len(results['articles'])} articles to {output_path}")

if __name__ == "__main__":
    main()
