"""
ai_news.py — 'AI 소식' 화면(/ai)이 보여 줄 글 모으기 (2026-10-28 사용자 요청)

  ① Threads @choi.openai 의 글(스레드 묶음째)
  ② GeekNews(news.hada.io/new) 새 글 목록

방법
  - GeekNews: /new 화면 HTML 을 그대로 읽어 글마다 제목·원문 주소·요약 앞부분·점수·글쓴이·시각을 뽑는다(RSS 는 '새 글'이 아니라 첫 화면 순서라 안 씀).
  - Threads: 로그인 없이 보이는 프로필 화면이지만 글이 자바스크립트로 그려진다 → 서버 크로미움(Playwright, capture.py·dig_pdf.py 와 같은 것)으로
    열어 화면에 들어 있는 데이터(thread_items)에서 글을 뽑는다. 크로미움은 무거워서 동시에 하나만, 30분에 한 번까지만 연다.
  - 결과는 ~/.openclaw/ai_news_cache/<src>.json 에 쌓는다(이전 글도 남겨 최근 것부터 최대 MAX_KEEP 개). 웹은 이 캐시만 읽고,
    오래됐으면 뒤에서 새로 받는다 → 바깥 사이트가 막혀도 화면은 마지막으로 받은 글을 그대로 보여 준다.
"""
import html
import json
import os
import re
import threading
import time
import urllib.request

CACHE_DIR = os.environ.get("AI_NEWS_DIR") or os.path.expanduser("~/.openclaw/ai_news_cache")
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH")             # capture.py 와 같은 변수
THREADS_USER = "choi.openai"
THREADS_URL = "https://www.threads.com/@" + THREADS_USER
GEEK_URL = "https://news.hada.io/new"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")                     # GeekNews 는 짧은 UA 를 403 으로 막는다
MAX_AGE = {"threads": 30 * 60, "geeknews": 10 * 60}    # 이보다 오래된 캐시면 뒤에서 새로 받는다
MAX_KEEP = {"threads": 60, "geeknews": 120}
SOURCES = tuple(MAX_AGE)
_locks = {s: threading.Lock() for s in SOURCES}


# ── GeekNews ─────────────────────────────────────────────────────────────────
def _text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def parse_geeknews(page):
    """news.hada.io/new HTML → 글 목록(화면 순서 = 최신순)."""
    out = []
    for row in re.split(r"<div class='topic_row'", page)[1:]:
        tid = re.search(r"data-topic-state-id='(\d+)'", row)
        a = re.search(r"<div class=topictitle>.*?<a href='([^']*)'[^>]*>(.*?)</a>", row, re.S)
        if not tid or not a:
            continue
        topic = "https://news.hada.io/topic?id=" + tid.group(1)
        link = html.unescape(a.group(1))
        if not re.match(r"^https?://", link):            # 원문 없는 글(Ask/Show 등)은 토론 주소
            link = topic
        dom = re.search(r"<span class=topicurl>\((.*?)\)</span>", row)
        desc = re.search(r"<div class='topicdesc'><a [^>]*>(.*?)</a>", row, re.S)
        pts = re.search(r"<span id='tp\d+'>(\d+)</span>", row)
        who = re.search(r"by <a href='/@[^']*'>(.*?)</a>", row)
        tm = re.search(r'datetime="([^"]+)"', row)
        cm = re.search(r"data-topic-comment-count='(\d+)'", row)
        out.append({"id": tid.group(1), "title": _text(a.group(2)), "url": link, "topic": topic,
                    "domain": _text(dom.group(1)) if dom else "", "desc": _text(desc.group(1)) if desc else "",
                    "points": int(pts.group(1)) if pts else 0, "author": _text(who.group(1)) if who else "",
                    "at": tm.group(1) if tm else "", "comments": int(cm.group(1)) if cm else 0})
    return out


def html_to_text(h):
    """GeekNews 본문 HTML → 줄글(목록은 '• ', 안쪽 목록은 들여쓰기). 화면은 글자로만 그려 바깥 HTML 을 넣지 않는다."""
    out, depth, pre = [], 0, False
    for tok in re.split(r"(<[^>]+>)", h or ""):
        if tok.startswith("<"):
            t = re.match(r"</?\s*([a-zA-Z0-9]+)", tok)
            t = t.group(1).lower() if t else ""
            end = tok.startswith("</")
            if t in ("ul", "ol"):
                depth = max(depth - 1, 0) if end else depth + 1
                if depth == (0 if end else 1):              # 맨 바깥 목록 앞뒤에만 줄을 띄운다
                    out.append("\n")
            elif t == "li" and not end:
                out.append("\n" + "  " * max(depth - 1, 0) + "• ")
            elif t == "pre":
                pre = not end
                out.append("\n")
            elif t in ("p", "br", "div", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
                out.append("\n")
            continue
        s = html.unescape(tok)
        out.append(s if pre else re.sub(r"\s+", " ", s))
    text = "\n".join(x.rstrip() for x in "".join(out).split("\n"))
    text = re.sub(r"(?m)^ +(?!\s*• )", "", text)          # 목록이 아닌 줄의 앞 공백
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_topic(page):
    """news.hada.io/topic 화면 → 본문 글. 본문 칸이 없으면 ''."""
    m = re.search(r"<section id='topic_contents'[^>]*>(.*?)</section>", page or "", re.S)
    return html_to_text(m.group(1)) if m else ""


def topic(tid):
    """GeekNews 글 하나의 본문(누르면 펼치기용). 한 번 받은 글은 하루 동안 캐시에서 준다."""
    tid = str(tid or "")
    if not re.fullmatch(r"\d{1,9}", tid):
        return {"ok": False, "reason": "잘못된 글 번호"}
    p = os.path.join(CACHE_DIR, "topics", tid + ".json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if time.time() - d.get("at", 0) < 86400:
            return d
    except (OSError, ValueError):
        pass
    try:
        req = urllib.request.Request("https://news.hada.io/topic?id=" + tid,
                                     headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = parse_topic(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return {"ok": False, "reason": "본문을 받지 못함: %s" % str(e)[:100]}
    d = {"ok": bool(text), "id": tid, "text": text, "at": int(time.time())}
    if text:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    return d


def fetch_geeknews():
    req = urllib.request.Request(GEEK_URL, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        items = parse_geeknews(r.read().decode("utf-8", "replace"))
    if not items:
        raise RuntimeError("GeekNews 목록을 못 읽음(화면 구조 바뀜?)")
    return items


# ── Threads ──────────────────────────────────────────────────────────────────
# 브라우저 안에서 돌리는 코드: 화면에 든 JSON(script type=application/json) 중 thread_items 를 모두 찾는다.
_EXTRACT_JS = """() => {
  const out = [];
  const walk = o => { if (!o || typeof o !== 'object') return;
    if (Array.isArray(o.thread_items)) { out.push(o.thread_items); return; }
    for (const k in o) walk(o[k]); };
  document.querySelectorAll('script[type="application/json"]').forEach(s => {
    if (s.textContent.includes('thread_items')) { try { walk(JSON.parse(s.textContent)); } catch (e) {} } });
  return out;
}"""


def parse_threads(groups, user=THREADS_USER):
    """thread_items 묶음들 → [{code,url,at,posts:[{code,url,at,text,media}]}] (그 사람이 쓴 글만, 최신 묶음 먼저)."""
    seen, out = set(), []
    for items in groups or []:
        posts = []
        for it in items or []:
            po = (it or {}).get("post") or {}
            if ((po.get("user") or {}).get("username") or "") != user or not po.get("code"):
                continue
            media = bool(po.get("carousel_media") or (po.get("image_versions2") or {}).get("candidates")
                         or po.get("video_versions"))   # 사진·영상 있음(화면엔 '원문에서 보기'로만 안내)
            posts.append({"code": po["code"], "url": "%s/post/%s" % (THREADS_URL, po["code"]),
                          "at": int(po.get("taken_at") or 0), "text": ((po.get("caption") or {}).get("text") or "").strip(),
                          "media": media})
        if not posts or posts[0]["code"] in seen:
            continue
        seen.add(posts[0]["code"])
        out.append({"code": posts[0]["code"], "url": posts[0]["url"], "at": posts[0]["at"], "posts": posts})
    out.sort(key=lambda t: -t["at"])
    return out


def fetch_threads():
    """로그인 없이 보이는 최근 글 묶음(2026-10-28 확인: 4묶음, 더 내리면 '로그인하여 더 확인' 안내).
    30분마다 받아 캐시에 쌓으므로 새 글은 계속 모인다."""
    from playwright.sync_api import sync_playwright    # 늦게 불러온다 → 없어도 GeekNews 는 정상
    with sync_playwright() as p:
        kw = {"headless": True}
        if CHROMIUM_PATH:
            kw["executable_path"] = CHROMIUM_PATH
        browser = p.chromium.launch(**kw)
        try:
            page = browser.new_page(locale="ko-KR", user_agent=UA)
            page.goto(THREADS_URL, wait_until="networkidle", timeout=60000)
            groups = page.evaluate(_EXTRACT_JS)
        finally:
            browser.close()
    items = parse_threads(groups)
    if not items:
        raise RuntimeError("Threads 글을 못 읽음(로그인 요구·화면 구조 바뀜?)")
    return items


# ── 캐시 ─────────────────────────────────────────────────────────────────────
def _path(src):
    return os.path.join(CACHE_DIR, src + ".json")


def _read(src):
    try:
        with open(_path(src), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _key(src, x):
    return x["code"] if src == "threads" else x["id"]


def merge(src, old, new):
    """새로 받은 글 + 예전 글(같은 글은 새 것으로), 최신순 최대 MAX_KEEP 개."""
    have = {_key(src, x) for x in new}
    rows = list(new) + [x for x in old if _key(src, x) not in have]
    if src == "threads":
        rows.sort(key=lambda t: -t["at"])
    else:
        rows.sort(key=lambda t: (t.get("at") or "", int(t["id"])), reverse=True)
    return rows[:MAX_KEEP[src]]


def refresh(src):
    """바로 새로 받아 캐시에 쓴다. 다른 요청이 받는 중이면 False."""
    if src not in SOURCES:
        raise ValueError(src)
    lock = _locks[src]
    if not lock.acquire(blocking=False):
        return False
    try:
        old = _read(src)
        try:
            new = fetch_threads() if src == "threads" else fetch_geeknews()
            data = {"src": src, "fetched_at": int(time.time()), "error": "",
                    "items": merge(src, old.get("items", []), new)}
        except Exception as e:                           # 실패해도 예전 글은 그대로 두고 오류만 적는다
            data = dict(old, src=src, error=str(e)[:200], failed_at=int(time.time()))
            data.setdefault("items", [])
            data.setdefault("fetched_at", 0)
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = _path(src) + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, _path(src))
        return True
    finally:
        lock.release()


def _stale(d, src):
    last = max(d.get("fetched_at") or 0, d.get("failed_at") or 0)   # 실패한 직후에도 바로 또 두드리지 않는다
    return time.time() - last > MAX_AGE[src]


def feed(src, background=True):
    """화면용: 캐시를 돌려주고, 오래됐으면 뒤에서 새로 받기 시작한다. 캐시가 아예 없으면(처음) 이 자리에서 받는다."""
    if src not in SOURCES:
        return {"ok": False, "reason": "모르는 출처"}
    d = _read(src)
    refreshing = False
    if not d:
        refresh(src)
        d = _read(src)
    elif _stale(d, src):
        if background:
            threading.Thread(target=refresh, args=(src,), daemon=True).start()
        else:
            refresh(src)
            d = _read(src)
        refreshing = background
    return {"ok": bool(d.get("items")), "src": src, "items": d.get("items", []), "fetched_at": d.get("fetched_at", 0),
            "error": d.get("error", ""), "refreshing": refreshing or _locks[src].locked()}


if __name__ == "__main__":                              # 서버에서 손으로 확인: python3 ai_news.py threads|geeknews
    import sys
    s = sys.argv[1] if len(sys.argv) > 1 else "geeknews"
    refresh(s)
    d = _read(s)
    print("오류:", d.get("error") or "없음", "· 글", len(d.get("items", [])))
    for x in d.get("items", [])[:5]:
        print("-", (x.get("title") or x["posts"][0]["text"])[:70].replace("\n", " "))
