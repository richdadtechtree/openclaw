#!/usr/bin/env python3
"""
unabomber_fetch.py — 부동산 앱웹 데이터 수집기 (유나바머 전용)

앱웹(기본: https://richdadtechtree.duckdns.org/)에서 부동산 데이터를 가져와
같은 폴더의 unabomber_data.json 으로 저장한다. 유나바머는 이 JSON 을 읽고
SOUL.md 의 Decision Engine 을 적용해 브리핑한다.

데이터 형태를 몰라도 동작하도록 2단계 자가탐지:
  1) requests 로 페이지 HTML + 임베디드 API 경로(/api…, *.json, fetch(...))를 훑어
     같은 오리진의 JSON 엔드포인트를 찾아 수집한다. (가벼움, 브라우저 불필요)
  2) 페이지가 JS SPA 라 위에서 데이터가 안 잡히면 Playwright 로 실제 렌더하며
     네트워크의 JSON/api 응답을 그대로 가로채 저장한다. (stock venv 의 playwright 사용)

출력 unabomber_data.json 구조:
  {
    "fetched_at": ISO시각,
    "base_url": "...",
    "method": "requests" | "playwright" | "requests+playwright",
    "api": { "<응답 URL>": <JSON 또는 텍스트> , ... },   # 앱이 쓰는 실제 데이터
    "page_text": "화면에 보이는 텍스트(폴백/보조)"
  }

실행:
  # 가벼운 시도(openclaw python3 로 충분):
  python3 ~/.openclaw/workspace/unabomber_fetch.py
  # SPA 라 Playwright 폴백이 필요하면 브라우저 있는 stock venv 로:
  ~/stock/stock/venv/bin/python ~/.openclaw/workspace/unabomber_fetch.py

환경변수:
  UNABOMBER_URL      앱웹 주소 (기본: https://richdadtechtree.duckdns.org/)
  UNABOMBER_NO_PW    "1" 이면 Playwright 폴백을 끈다(requests 만).
  CHROMIUM_PATH      (있으면) Playwright 실행 파일 경로 override
"""
import os
import re
import sys
import json
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests

BASE_URL = os.getenv("UNABOMBER_URL", "https://richdadtechtree.duckdns.org/")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unabomber_data.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}

# HTML/JS 안에서 데이터 엔드포인트 후보를 뽑는 패턴
_PATH_RE = re.compile(r"""["'`]([^"'`]*?(?:/api/[^"'`]*|\.json)[^"'`]*)["'`]""", re.I)


def _same_origin(url, base):
    try:
        a, b = urlparse(url), urlparse(base)
        return (a.netloc or b.netloc) == b.netloc
    except Exception:
        return False


def _try_json(resp):
    ct = resp.headers.get("content-type", "")
    if "application/json" in ct or resp.text[:1].strip() in ("{", "["):
        try:
            return resp.json()
        except Exception:
            return None
    return None


def fetch_via_requests(base_url):
    """페이지를 받고, 임베디드 API 경로를 찾아 JSON 을 수집한다."""
    api = {}
    page_text = ""
    try:
        res = requests.get(base_url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        html = res.text

        # 페이지 자체가 JSON 이면 바로 저장
        j = _try_json(res)
        if j is not None:
            api[base_url] = j

        # 화면 텍스트(보조): 태그 제거 대충
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for s in soup(["script", "style", "noscript"]):
                s.decompose()
            page_text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()[:8000]
        except Exception:
            page_text = re.sub(r"<[^>]+>", " ", html)
            page_text = re.sub(r"\s+", " ", page_text).strip()[:8000]

        # 임베디드 엔드포인트 후보 수집
        candidates = set()
        for m in _PATH_RE.findall(html):
            full = urljoin(base_url, m)
            if _same_origin(full, base_url):
                candidates.add(full)

        for url in sorted(candidates):
            if url in api:
                continue
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                data = _try_json(r)
                if data is not None:
                    api[url] = data
            except Exception as e:
                print(f"[warn] API 후보 실패 {url}: {e}", file=sys.stderr)

    except Exception as e:
        print(f"[error] requests 수집 실패: {e}", file=sys.stderr)

    return api, page_text


def fetch_via_playwright(base_url):
    """JS SPA 폴백: 실제 렌더하며 네트워크의 JSON/api 응답을 가로챈다."""
    api = {}
    page_text = ""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"[info] Playwright 미설치({e}). stock venv 로 실행 필요. 폴백 생략.", file=sys.stderr)
        return api, page_text

    with sync_playwright() as p:
        launch_kwargs = {"headless": True}
        cp = os.getenv("CHROMIUM_PATH")
        if cp:
            launch_kwargs["executable_path"] = cp
        browser = None
        try:
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page()

            def on_response(resp):
                try:
                    ct = resp.headers.get("content-type", "")
                    if "application/json" in ct or "/api" in resp.url:
                        try:
                            api[resp.url] = resp.json()
                        except Exception:
                            api[resp.url] = resp.text()[:5000]
                except Exception:
                    pass

            page.on("response", on_response)
            page.goto(base_url, wait_until="networkidle", timeout=30000)
            time.sleep(1.5)
            try:
                page_text = page.inner_text("body")[:8000]
            except Exception:
                page_text = ""
        except Exception as e:
            print(f"[error] Playwright 수집 실패: {e}", file=sys.stderr)
        finally:
            if browser:
                browser.close()

    return api, page_text


def main():
    print(f"[unabomber_fetch] 대상: {BASE_URL}")
    method = "requests"
    api, page_text = fetch_via_requests(BASE_URL)

    # 데이터가 빈약하면 Playwright 폴백
    if not api and os.getenv("UNABOMBER_NO_PW") != "1":
        print("[unabomber_fetch] requests 로 API 데이터 못 찾음 → Playwright 폴백 시도")
        pw_api, pw_text = fetch_via_playwright(BASE_URL)
        if pw_api or pw_text:
            method = "playwright" if not api else "requests+playwright"
            api.update(pw_api)
            if pw_text:
                page_text = pw_text

    out = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "method": method,
        "api": api,
        "page_text": page_text,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    n_api = len(api)
    print(f"[unabomber_fetch] 완료: API {n_api}건, page_text {len(page_text)}자 → {OUT_PATH}")
    if n_api == 0 and not page_text:
        print("[unabomber_fetch] ⚠️ 데이터를 하나도 못 가져왔다. 사이트 접근/구조 확인 필요.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
