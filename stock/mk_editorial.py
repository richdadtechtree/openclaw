"""
매일경제 사설 모으기 (신문 요약 페이지 맨 아래 '📰 매일경제 사설' 칸 전용) — 2026-10-20 사용자 요청

- 그날 신문(D)에 실린 사설 = 보통 **전날(D-1) 저녁**에 인터넷에 먼저 올라온다.
  → 'D-1 낮 12시 ~ D 낮 12시(한국시간)' 에 올라온 사설을 그날 사설로 본다. 없으면 D 당일 것, 그래도 없고
    오늘이면 가장 최근 것을 '최신' 표시와 함께 보여 준다(날짜를 속이지 않는다).
- 표준 라이브러리만 쓴다(urllib·html.parser) → 시스템 python3 로도 점검 가능.
- 사설 링크 찾기: ① 사설 목록 페이지 ② 뉴스 사설 주소 ③ 매경 RSS 들 — 어느 쪽이든
  'mk.co.kr/news/editorial/숫자' 모양 링크만 모은다.
- 글 읽기: 제목 = og:title(→<title>) · 올린 시각 = article:published_time(→JSON-LD datePublished→본문 '입력' 글자)
           본문 = JSON-LD articleBody → 본문 상자(news_cnt_detail·art_txt·articleBody) → 긴 <p> 글들.
  ⚠️ 2026-10-20 개발 환경에선 매경 사이트가 막혀 **실제 HTML 로는 확인 못 함** → 서버에서 아래로 확인:
      cd ~/stock/stock && venv/bin/python mk_editorial.py --probe
- 캐시: ~/stock/stock/.mk_editorial/<날짜>.json (그날 사설을 찾으면 다시 안 받음, 못 찾았으면 30분 뒤 재시도).
- 개인용 화면. 외부 공개 사이트로 바꾸면 기사 본문 게시는 저작권 문제가 될 수 있다(원문 링크를 늘 함께 준다).
"""
import html
import json
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

KST = timezone(timedelta(hours=9))
TIMEOUT = 7
RETRY_SEC = 30 * 60          # 못 찾았을 때 다시 시도하는 간격
MAX_ITEMS = 3
CACHE_DIR = os.path.expanduser(os.getenv("MK_EDITORIAL_DIR",
                               os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mk_editorial")))
BASE = os.getenv("MK_BASE", "https://www.mk.co.kr")     # 검사 때 가짜 서버로 바꾼다
LIST_URLS = [BASE + "/opinion/editorial/", BASE + "/news/editorial/",
             BASE + "/rss/30000001/", BASE + "/rss/40300001/"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
LINK_RE = re.compile(r'(?:https?:)?(?://(?:www\.|m\.)?mk\.co\.kr)?/news/editorial/(\d{5,})')

_lock = threading.Lock()
_last_try = {}               # 날짜 → 마지막으로 못 찾은 시각


def _get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        cs = r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(cs, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def find_links(log=None):
    """사설 글 번호 목록(새 글 먼저). 여러 곳을 돌며 모은다."""
    ids, errs = [], []
    for u in LIST_URLS:
        try:
            page = _get(u)
        except Exception as e:                      # 막힘·시간 초과 → 다음 곳
            errs.append("%s → %s" % (u, e))
            continue
        found = [m.group(1) for m in LINK_RE.finditer(page)]
        if log is not None:
            log.append("%s → 사설 링크 %d개" % (u, len(set(found))))
        for i in found:
            if i not in ids:
                ids.append(i)
        if len(ids) >= 6:
            break
    if log is not None:
        log.extend(errs)
    ids.sort(key=lambda s: int(s), reverse=True)     # 번호가 클수록 새 글
    return ids


# ── 글 한 편 읽기 ──────────────────────────────────────────────────────────
def _meta(page, *names):
    for n in names:
        m = re.search(r'<meta[^>]+(?:property|name|itemprop)\s*=\s*["\']%s["\'][^>]*>' % re.escape(n), page, re.I)
        if m:
            c = re.search(r'content\s*=\s*["\']([^"\']*)["\']', m.group(0), re.I)
            if c and c.group(1).strip():
                return html.unescape(c.group(1).strip())
    return ""


def _jsonld(page):
    out = {}
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>([\s\S]*?)</script>', page, re.I):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict):
                for k in ("headline", "datePublished", "articleBody"):
                    if x.get(k) and k not in out:
                        out[k] = x[k]
    return out


def _parse_time(s):
    """'2026-10-19T17:31:00+09:00' · '2026-10-19 17:31' · '2026.10.19 17:31' → KST datetime"""
    if not s:
        return None
    s = s.strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=KST)).astimezone(KST)
    except ValueError:
        pass
    m = re.search(r'(20\d\d)[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})\.?\s*(?:(\d{1,2}):(\d{2}))?', s)
    if m:
        y, mo, d, h, mi = m.groups()
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), tzinfo=KST)
    return None


class _BoxText(HTMLParser):
    """class 이름에 KEYS 중 하나가 든 상자(div·section·article) 안의 글만 문단으로 모은다."""
    KEYS = ("news_cnt_detail", "art_txt", "article_body", "articlebody", "news_body", "view_txt")
    SKIP = ("script", "style", "figure", "figcaption", "iframe", "button", "noscript")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0          # 상자 안 깊이(0=상자 밖)
        self.skip = 0
        self.paras, self.cur = [], []

    def _flush(self):
        t = re.sub(r'\s+', ' ', "".join(self.cur)).strip()
        if t:
            self.paras.append(t)
        self.cur = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.depth:
            if tag in self.SKIP:
                self.skip += 1
            if tag in ("div", "section", "article"):
                self.depth += 1
            if tag in ("p", "br", "div"):
                self._flush()
            return
        cls = ((a.get("class") or "") + " " + (a.get("itemprop") or "")).lower()
        if tag in ("div", "section", "article") and any(k in cls for k in self.KEYS):
            self.depth = 1

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in ("p", "div"):
            self._flush()
        if tag in ("div", "section", "article"):
            self.depth -= 1
            if not self.depth:
                self._flush()

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.cur.append(data)


_JUNK = re.compile(r'(무단\s*전재|재배포\s*금지|ⓒ|Copyright|저작권|기자\s*[\w.]+@|구독|좋아요|공유하기|글자크기|이 기사)', re.I)


def _clean_paras(paras):
    out = []
    for p in paras:
        p = p.strip()
        if len(p) < 2 or _JUNK.search(p):
            continue
        if out and out[-1] == p:
            continue
        out.append(p)
    return out


def parse_article(page, url=""):
    ld = _jsonld(page)
    title = _meta(page, "og:title", "twitter:title") or ld.get("headline", "")
    if not title:
        m = re.search(r'<title[^>]*>([\s\S]*?)</title>', page, re.I)
        title = html.unescape(m.group(1)).strip() if m else ""
    title = re.sub(r'\s*[-|–]\s*매일경제.*$', '', title).strip()
    title = re.sub(r'^\s*\[사설\]\s*', '', title).strip()

    pub = _parse_time(_meta(page, "article:published_time", "og:article:published_time", "pubdate", "date")
                      or ld.get("datePublished", ""))
    if not pub:
        m = re.search(r'입력\s*[:：]?\s*(20\d\d[.\-]\s*\d{1,2}[.\-]\s*\d{1,2}\.?\s*\d{1,2}:\d{2})', page)
        pub = _parse_time(m.group(1)) if m else None

    body = []
    if isinstance(ld.get("articleBody"), str) and len(ld["articleBody"]) > 200:
        body = [p for p in re.split(r'\n\s*\n|\n', html.unescape(ld["articleBody"]))]
    if not body:
        bx = _BoxText()
        try:
            bx.feed(page)
            bx._flush()
        except Exception:
            pass
        body = bx.paras
    if sum(len(p) for p in body) < 200:                 # 상자를 못 찾음 → 긴 <p> 글들
        ps = [re.sub(r'<[^>]+>', '', html.unescape(x)) for x in re.findall(r'<p[^>]*>([\s\S]*?)</p>', page, re.I)]
        body = [re.sub(r'\s+', ' ', p).strip() for p in ps if len(p.strip()) >= 40]
    body = _clean_paras(body)
    return {"title": title, "url": url, "published": pub.isoformat() if pub else "",
            "paras": body, "chars": sum(len(p) for p in body)}


def fetch_article(aid):
    url = "%s/news/editorial/%s" % (BASE, aid)
    a = parse_article(_get(url), url)
    a["id"] = aid
    return a


# ── 날짜 고르기 + 캐시 ─────────────────────────────────────────────────────
def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def pick_for_date(items, date):
    """그날 신문 사설 = D-1 12:00 ~ D 12:00 에 올라온 글. 없으면 D 당일, 그래도 없으면 빈 목록."""
    d0 = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=KST)
    lo, hi = d0 - timedelta(hours=12), d0 + timedelta(hours=12)
    def t(a):
        return _parse_time(a.get("published") or "")
    win = [a for a in items if t(a) and lo <= t(a) < hi]
    if not win:
        win = [a for a in items if t(a) and t(a).strftime("%Y-%m-%d") == date]
    win.sort(key=lambda a: t(a))
    return win[:MAX_ITEMS]


def _cache_path(date):
    return os.path.join(CACHE_DIR, date + ".json")


def get_editorials(date="", log=None):
    """{"ok", "date", "items":[{title,url,published,paras}], "stale": 최신 것으로 대신했나, "error"}"""
    date = date or today_kst()
    if not re.fullmatch(r"20\d\d-\d\d-\d\d", date):
        return {"ok": False, "date": date, "items": [], "error": "날짜 형식"}
    p = _cache_path(date)
    try:
        with open(p, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("items") and not c.get("stale"):
            return c
    except (OSError, ValueError):
        c = None
    with _lock:
        if log is None and time.time() - _last_try.get(date, 0) < RETRY_SEC:
            return c or {"ok": False, "date": date, "items": [], "error": "잠시 뒤 다시 찾아요"}
        _last_try[date] = time.time()
        try:
            ids = find_links(log)
        except Exception as e:
            ids = []
            if log is not None:
                log.append("링크 찾기 실패: %s" % e)
        arts = []
        for aid in ids[:8]:
            try:
                a = fetch_article(aid)
            except Exception as e:
                if log is not None:
                    log.append("글 %s 읽기 실패: %s" % (aid, e))
                continue
            if a["title"] and a["chars"] >= 150:
                arts.append(a)
            elif log is not None:
                log.append("글 %s: 제목·본문 부족(제목 %r, %d자)" % (aid, a["title"][:20], a["chars"]))
        items = pick_for_date(arts, date)
        stale = False
        if not items and date == today_kst() and arts:      # 오늘 사설이 아직 → 가장 최근 것(표시함)
            arts.sort(key=lambda a: a.get("published") or "", reverse=True)
            items, stale = arts[:2], True
        res = {"ok": bool(items), "date": date, "items": items, "stale": stale,
               "fetched": datetime.now(KST).isoformat(timespec="seconds"),
               "error": "" if items else ("사설 링크를 못 찾음" if not ids else "그날 사설이 아직 없음")}
        if items:
            try:
                os.makedirs(CACHE_DIR, exist_ok=True)
                tmp = p + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(res, f, ensure_ascii=False)
                os.replace(tmp, p)
            except OSError:
                pass
        return res


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    d = args[0] if args else today_kst()
    if "--probe" in sys.argv:
        _last_try.clear()
        try:
            os.remove(_cache_path(d))
        except OSError:
            pass
    log = []
    r = get_editorials(d, log=log)
    for line in log:
        print(" ·", line)
    print("\n날짜 %s → %s%s" % (d, "찾음 %d편" % len(r["items"]) if r["ok"] else "못 찾음: " + r.get("error", ""),
                              " (오늘 것이 아직이라 최신 것)" if r.get("stale") else ""))
    for a in r["items"]:
        print("\n■ %s\n  %s · %s · 문단 %d개 %d자\n  %s…" % (a["title"], a["published"], a["url"],
              len(a["paras"]), a["chars"], (a["paras"][0] if a["paras"] else "")[:90]))
    sys.exit(0 if r["ok"] else 2)
