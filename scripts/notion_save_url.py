#!/usr/bin/env python3
"""
notion_save_url.py — 웹주소(URL) 하나를 받아 그 페이지의 제목/웹주소/본문을 노션 DB에 저장.

슬랙에서 사용자가 링크를 보내면 뚜떵또가 이 스크립트를 실행한다.
저장되는 것:
  - 제목  : 웹페이지 제목(og:title 또는 <title>). 없으면 URL.
  - 웹주소: 본문 맨 위 북마크 블록 + (DB에 url 타입 칸이 있으면) 해당 속성.
  - 본문  : 페이지 본문 텍스트(article/main 우선 추출).

사용:
  python3 scripts/notion_save_url.py <URL> [YYYY-MM-DD]

필요 (.env): NOTION_TOKEN, NOTION_BRIEFING_TARGET(또는 NOTION_BRIEFING_DB)
  → notion_push.py 와 동일한 대상 DB/페이지에 저장한다.
"""
import html
import os
import re
import sys
from datetime import datetime

import requests

# notion_push.py 의 저장 로직/상수를 재사용 (같은 폴더).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notion_push as np  # noqa: E402

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_BODY_CHARS = 15000  # 본문 저장 상한(너무 긴 페이지 방지)


def fetch(url):
    """URL 을 받아 (제목, 본문텍스트) 반환."""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    doc = r.text
    return extract_title(doc) or url, extract_text(doc)


def extract_title(doc):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']og:title["\'][^>]*content=["\']([^"\']+)',
                  doc, re.I)
    if m:
        return html.unescape(m.group(1)).strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
    if m:
        return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    return None


def extract_text(doc):
    """본문 텍스트 대략 추출(외부 라이브러리 없이). article/main 우선."""
    m = (re.search(r"<article[^>]*>(.*?)</article>", doc, re.I | re.S)
         or re.search(r"<main[^>]*>(.*?)</main>", doc, re.I | re.S))
    seg = m.group(1) if m else doc
    # 안 보이는/부수 영역 제거
    seg = re.sub(r"<(script|style|noscript|nav|header|footer|aside|form|svg)[^>]*>.*?</\1>",
                 " ", seg, flags=re.I | re.S)
    # 블록 종료 태그 → 줄바꿈
    seg = re.sub(r"(?i)</(p|div|br|li|h[1-6]|tr|section|article)>", "\n", seg)
    seg = re.sub(r"<[^>]+>", " ", seg)          # 남은 태그 제거
    seg = html.unescape(seg)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in seg.splitlines()]
    lines = [ln for ln in lines if ln]
    text = "\n".join(lines)
    return text[:MAX_BODY_CHARS]


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("사용법: python3 notion_save_url.py <URL> [YYYY-MM-DD]")
        sys.exit(1)
    url = sys.argv[1].strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    date_str = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime("%Y-%m-%d")

    try:
        title, body = fetch(url)
    except Exception as e:
        print(f"[Error] URL 가져오기 실패: {e}")
        sys.exit(1)

    blocks = np.md_to_blocks(body) if body else []
    # session 은 없음(신문 브리핑의 아침/저녁과 무관) → None.
    ok = np.create_page(title, date_str, None, blocks, url=url)
    if ok:
        print(f"✅ 노션 저장 성공! 제목: {title}")
    else:
        print("❌ 노션 저장 실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
