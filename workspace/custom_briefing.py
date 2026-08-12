import urllib.request
import xml.etree.ElementTree as ET
import json

def fetch_rss(url, outlet_name, limit=10):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    articles = []
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            channel = root.find('channel')
            if channel is not None:
                for item in channel.findall('item'):
                    title = item.find('title')
                    link = item.find('link')
                    pubDate = item.find('pubDate')
                    description = item.find('description')
                    
                    t_text = title.text if title is not None else ""
                    l_text = link.text if link is not None else ""
                    p_text = pubDate.text if pubDate is not None else ""
                    d_text = description.text if description is not None else ""
                    
                    articles.append({
                        "title": t_text.strip(),
                        "link": l_text.strip(),
                        "published": p_text.strip(),
                        "outlet": outlet_name,
                        "content": d_text.strip()
                    })
                    if len(articles) >= limit:
                        break
    except Exception as e:
        print(f"Error fetching {outlet_name}: {e}")
    return articles

mk = fetch_rss("https://www.mk.co.kr/rss/30000001", "매일경제", 5)
hk = fetch_rss("https://www.hankyung.com/feed/all-news", "한국경제", 10)

print(f"MK fetched: {len(mk)}")
print(f"HK fetched: {len(hk)}")
for i, a in enumerate(mk[:3]):
    print(f"MK {i+1}: {a['title']} ({a['link']})")
for i, a in enumerate(hk[:5]):
    print(f"HK {i+1}: {a['title']} ({a['link']})")
