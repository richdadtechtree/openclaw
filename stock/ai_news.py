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
import urllib.error
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
# 2026-10-30 사용자 요청 "CHOI님이 단 댓글은 하나도 빠짐없이": 프로필엔 글마다 앞부분만 보여서,
# 최근 글은 '글 하나 화면'을 따로 열어 본인 글(이어진 글 + 남의 댓글에 단 답)을 전부 모은다.
DEEP_DAYS = 7          # 이 기간 안의 글은 30분마다 다시 열어 새로 단 댓글까지 챙긴다
DEEP_MAX = 8           # 한 번에 여는 글 화면 수(크로미움이 무거워서)
DEEP_SCROLLS = 15      # 글 화면을 아래로 내려 더 불러오는 최대 횟수(더 안 늘어나면 일찍 멈춤)
SUB_MAX = 10           # 글 하나에서 '답이 숨어 있는 댓글' 화면을 따로 여는 최대 수
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


def _gone_path(tid):
    return os.path.join(CACHE_DIR, "topics", str(tid) + ".gone")


def _mark_gone(tid):
    os.makedirs(os.path.dirname(_gone_path(tid)), exist_ok=True)
    open(_gone_path(tid), "w").close()


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
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return {"ok": False, "reason": "본문을 받지 못함: %s" % str(e)[:100]}
        _mark_gone(tid)                                  # GeekNews 에서 지운 글(2026-10-29 36169 확인) → 목록에서도 뺀다
        return {"ok": False, "gone": True, "reason": "GeekNews에서 삭제된 글"}
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


def _uname(po):
    return ((po or {}).get("user") or {}).get("username") or ""


def _info(po):
    media = bool(po.get("carousel_media") or (po.get("image_versions2") or {}).get("candidates") or po.get("video_versions"))
    return {"code": po["code"], "url": "%s/post/%s" % (THREADS_URL, po["code"]), "at": int(po.get("taken_at") or 0),
            "text": ((po.get("caption") or {}).get("text") or "").strip(), "media": media}


def walk_items(o, out):
    """아무 JSON 에서 thread_items 목록을 모두 찾는다(화면에 든 JSON·아래로 내리며 받은 데이터 모두)."""
    if isinstance(o, dict):
        ti = o.get("thread_items")
        if isinstance(ti, list):
            out.append(ti)
            return out
        for v in o.values():
            walk_items(v, out)
    elif isinstance(o, list):
        for v in o:
            walk_items(v, out)
    return out


def _reply_count(po):
    """Threads 가 그 글에 적어 둔 '달린 댓글 수'(없으면 None)."""
    info = (po or {}).get("text_post_app_info") or {}
    for k in ("direct_reply_count", "reply_count"):
        if isinstance(info.get(k), int):
            return info[k]
    return None


def parse_thread_page(groups, root, user=THREADS_USER):
    """글 하나 화면의 thread_items 묶음들 → {"posts":[이어진 글…], "replies":[남의 댓글에 단 답…]} (없으면 None).
    묶음 안에서 앞에 다른 사람 글이 있으면 그 사람에게 단 답, 아니면 본인이 이어 쓴 글로 본다."""
    chain, replies = {}, {}
    comments, root_count = {}, None             # comments = {남의 댓글 code: [그 댓글, 그 묶음에 보인 본인 답 수]}
    for items in groups or []:
        other = None
        for it in items or []:
            po = (it or {}).get("post") or {}
            if not po.get("code"):
                continue
            if po["code"] == root and _reply_count(po) is not None:
                root_count = _reply_count(po)
            if _uname(po) != user:
                other = po
                comments.setdefault(po["code"], [po, 0])
                continue
            if other is not None:
                comments[other["code"]][1] += 1
            x = _info(po)
            if other is None:
                chain[x["code"]] = x
            elif x["code"] not in chain:
                x["reply_to"] = _uname(other)
                x["reply_to_text"] = ((other.get("caption") or {}).get("text") or "").strip()[:120]
                replies[x["code"]] = x
    if root not in chain:
        return None
    posts = sorted(chain.values(), key=lambda p: (p["code"] != root, p["at"]))
    # 답이 숨어 있을 수 있는 남의 댓글: Threads 가 적은 답글 수 > 이 화면에 보인 본인 답 수(답이 남의 것일 수도 있어 '후보')
    hidden = [{"code": po["code"], "user": _uname(po), "text": ((po.get("caption") or {}).get("text") or "").strip()[:120]}
              for po, seen in comments.values() if (_reply_count(po) or 0) > seen]
    return {"posts": posts, "replies": sorted((r for c, r in replies.items() if c not in chain), key=lambda p: p["at"]),
            "hidden": hidden, "stats": {"threads_comments": root_count, "others_comments": len(comments), "groups": len(groups or [])}}


def parse_comment_page(groups, comment, user=THREADS_USER):
    """남의 댓글 하나 화면 → 그 댓글에 본인이 단 답들(누구에게 단 답인지 붙여서)."""
    out = {}
    for items in groups or []:
        prev = comment
        for it in items or []:
            po = (it or {}).get("post") or {}
            if not po.get("code") or po["code"] == comment["code"]:
                continue
            if _uname(po) != user:
                prev = {"code": po["code"], "user": _uname(po), "text": ((po.get("caption") or {}).get("text") or "").strip()[:120]}
                continue
            x = _info(po)
            x["reply_to"], x["reply_to_text"] = prev["user"], prev["text"]
            out[x["code"]] = x
    return list(out.values())


def parse_threads(groups, user=THREADS_USER):
    """thread_items 묶음들 → [{code,url,at,posts:[{code,url,at,text,media}]}] (그 사람이 쓴 글만, 최신 묶음 먼저)."""
    seen, out = set(), []
    for items in groups or []:
        posts = []
        for it in items or []:
            po = (it or {}).get("post") or {}
            if ((po.get("user") or {}).get("username") or "") != user or not po.get("code"):
                continue
            posts.append(_info(po))                       # media = 사진·영상 있음(화면엔 '원문에서 보기'로만 안내)
        if not posts or posts[0]["code"] in seen:
            continue
        seen.add(posts[0]["code"])
        out.append({"code": posts[0]["code"], "url": posts[0]["url"], "at": posts[0]["at"], "posts": posts})
    out.sort(key=lambda t: -t["at"])
    return out


def _json_chunks(text):
    """받은 데이터 글 → JSON 덩어리들(앞에 for(;;); 가 붙거나 줄마다 JSON 인 경우도)."""
    text = re.sub(r"^\s*for\s*\(;;\);", "", text or "")
    try:
        return [json.loads(text)]
    except ValueError:
        out = []
        for ln in text.splitlines():
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
        return out


# 접힌 답글 펼치기: '답글 N개 보기·더 보기·View more replies' 같은 단추만 누른다(로그인·가입·앱 단추는 절대 안 누름)
_EXPAND_JS = """() => {
  let n = 0;
  document.querySelectorAll('[role=button],button,a,span').forEach(b => {
    const t = (b.innerText || '').trim();
    if (!t || t.length > 30 || b.dataset.ocx) return;
    if (/로그인|가입|Log ?in|Sign ?up|앱|App|열기|Open/i.test(t)) return;
    if (/(답글|댓글|repl).*(보기|더|more|view)|^(더 보기|View more|Show more|See more)/i.test(t) || /^View \\d+ (more )?repl/i.test(t)) {
      b.dataset.ocx = '1'; try { b.click(); n++; } catch (e) {} }
  });
  return n;
}"""
_WALL_JS = """() => /로그인하여 .*(확인|보기)|Log in to see|Log in or sign up/i.test(document.body.innerText || '')"""


def _open_collect(page, url, scrolls=0, info=None):
    """화면을 열고(필요하면 아래로 내리며 접힌 답글도 펼치며) 화면 JSON + 받은 데이터 속 thread_items 를 모두 모은다.
    더 내려도 새 데이터가 안 오면 일찍 멈춘다. info(dict)에 로그인 벽·내린 횟수를 적는다."""
    resps = []

    def on_resp(r):                                      # ⚠️ list.append 를 바로 넘기면 Playwright 가 오류(내장 함수엔 표시를 못 붙임)
        resps.append(r)
    page.on("response", on_resp)
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        idle, done = 0, 0
        for done in range(1, scrolls + 1):
            before = len(resps)
            try:
                clicked = page.evaluate(_EXPAND_JS)
            except Exception:
                clicked = 0
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(1200)
            idle = idle + 1 if (len(resps) == before and not clicked) else 0
            if idle >= 3:                                # 세 번 연속 아무것도 안 늘면 끝
                break
        groups = page.evaluate(_EXTRACT_JS)
        if info is not None:
            info["scrolls"] = done
            try:
                info["login_wall"] = bool(page.evaluate(_WALL_JS))
            except Exception:
                pass
    finally:
        page.remove_listener("response", on_resp)
    for r in resps:                                      # 내리면서 받은 댓글 데이터(graphql 등)
        try:
            if "json" not in (r.headers.get("content-type") or "") and "graphql" not in r.url:
                continue
            for obj in _json_chunks(r.text()):
                walk_items(obj, groups)
        except Exception:
            pass
    return groups


def fetch_threads(deep=()):
    """로그인 없이 보이는 최근 글 묶음(2026-10-28 확인: 4묶음, 더 내리면 '로그인하여 더 확인' 안내).
    + 프로필의 글과 deep(최근 글 code 목록)은 글 하나 화면을 열어 본인 글을 전부 모은다.
    반환 (items, details={code: {"posts":…, "replies":…}}). 글 하나 화면이 실패해도 그 글만 건너뛴다."""
    from playwright.sync_api import sync_playwright    # 늦게 불러온다 → 없어도 GeekNews 는 정상
    details = {}
    with sync_playwright() as p:
        kw = {"headless": True}
        if CHROMIUM_PATH:
            kw["executable_path"] = CHROMIUM_PATH
        browser = p.chromium.launch(**kw)
        try:
            page = browser.new_page(locale="ko-KR", user_agent=UA)
            items = parse_threads(_open_collect(page, THREADS_URL))
            if not items:
                raise RuntimeError("Threads 글을 못 읽음(로그인 요구·화면 구조 바뀜?)")
            codes = []
            for c in [x["code"] for x in items] + list(deep):
                if c not in codes:
                    codes.append(c)
            for code in codes[:DEEP_MAX]:
                try:
                    info = {}
                    d = parse_thread_page(_open_collect(page, "%s/post/%s" % (THREADS_URL, code), DEEP_SCROLLS, info), code)
                    if not d:
                        continue
                    have = {r["code"] for r in d["replies"]}
                    opened = 0
                    for cm in d["hidden"][:SUB_MAX]:          # 답이 숨어 있는 댓글은 그 댓글 화면을 따로 열어 본인 답을 찾는다
                        try:
                            for r in parse_comment_page(_open_collect(page, "https://www.threads.com/@%s/post/%s" % (cm["user"], cm["code"]), 4), cm):
                                if r["code"] not in have and r["code"] not in {p["code"] for p in d["posts"]}:
                                    d["replies"].append(r)
                                    have.add(r["code"])
                            opened += 1
                        except Exception as e:
                            print("[ai_news] 댓글 화면 %s 실패: %r" % (cm["code"], e))
                    d["replies"].sort(key=lambda r: r["at"])
                    d["stats"].update(info, hidden=len(d["hidden"]), sub_opened=opened)
                    details[code] = d
                except Exception as e:
                    print("[ai_news] 글 화면 %s 실패: %r" % (code, e))
        finally:
            browser.close()
    return items, details


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


def _union(a, b):
    """글 목록 두 개를 합침(같은 code 는 b 가 이김) — 이번에 못 읽은 댓글이 있어도 예전에 모은 건 남긴다."""
    if not all(x.get("code") for x in (a or []) + (b or [])):   # 번호 없는 옛 형식이면 새 것을 그대로
        return list(b or a or [])
    m = {x["code"]: x for x in a or []}
    m.update({x["code"]: x for x in b or []})
    return list(m.values())


def merge(src, old, new):
    """새로 받은 글 + 예전 글(같은 글은 새 것으로), 최신순 최대 MAX_KEEP 개.
    Threads 는 같은 글이면 이어진 글·댓글에 단 답을 합친다(프로필엔 앞부분만 보이므로 예전에 모은 걸 잃지 않게)."""
    have = {_key(src, x) for x in new}
    if src == "threads":
        prev = {x["code"]: x for x in old}
        new = [dict(x, posts=sorted(_union(prev[x["code"]].get("posts"), x.get("posts")), key=lambda p: (p.get("code") != x["code"], p.get("at", 0))),
                    replies=sorted(_union(prev[x["code"]].get("replies"), x.get("replies")), key=lambda p: p.get("at", 0)),
                    full_at=x.get("full_at") or prev[x["code"]].get("full_at"), stats=x.get("stats") or prev[x["code"]].get("stats"))
               if x["code"] in prev else x for x in new]
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
            if src == "threads":
                olds = old.get("items", [])
                recent = [x["code"] for x in sorted(olds, key=lambda t: -t["at"]) if time.time() - x.get("at", 0) < DEEP_DAYS * 86400]
                got = fetch_threads(deep=recent)
                new, details = got if isinstance(got, tuple) else (got, {})
                byc = {x["code"]: x for x in olds}
                for code, d in details.items():           # 글 하나 화면에서 모은 '전부'를 해당 글에 붙인다
                    base = next((x for x in new if x["code"] == code), None) or byc.get(code)
                    if base is None:
                        continue
                    full = dict(base, posts=d["posts"], replies=d["replies"], full_at=int(time.time()), stats=d.get("stats") or {})
                    new = [full if x["code"] == code else x for x in new] if any(x["code"] == code for x in new) else new + [full]
            else:
                new = fetch_geeknews()
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
    items = d.get("items", [])
    if src == "geeknews":                                # 본문을 열다 삭제된 것으로 확인된 글은 빼고 보여 준다
        items = [x for x in items if not os.path.exists(_gone_path(x["id"]))]
    return {"ok": bool(items), "src": src, "items": items, "fetched_at": d.get("fetched_at", 0),
            "error": d.get("error", ""), "refreshing": refreshing or _locks[src].locked()}


if __name__ == "__main__":                              # 서버에서 손으로 확인: python3 ai_news.py threads|geeknews
    import sys
    s = sys.argv[1] if len(sys.argv) > 1 else "geeknews"
    refresh(s)
    d = _read(s)
    print("오류:", d.get("error") or "없음", "· 글", len(d.get("items", [])))
    for x in d.get("items", [])[:5]:
        st = x.get("stats") or {}
        extra = ("  [이어진 글 %d · 댓글에 단 답 %d%s]" % (len(x.get("posts") or []), len(x.get("replies") or []),
                                                    " · 글 화면 확인함" if x.get("full_at") else "")) if s == "threads" else ""
        if s == "threads" and st:                        # 점검: Threads 가 센 전체 댓글 수와 비교할 단서
            extra += ("\n    └ Threads 전체 댓글 %s개 · 화면에 보인 남의 댓글 %s개 · 답이 숨어 있을 수 있는 댓글 %s개(따로 연 것 %s)"
                      " · 내린 횟수 %s · 로그인 벽 %s" % (st.get("threads_comments", "?"), st.get("others_comments", "?"),
                                                    st.get("hidden", "?"), st.get("sub_opened", "?"), st.get("scrolls", "?"),
                                                    "있음" if st.get("login_wall") else "없음"))
        print("-", (x.get("title") or x["posts"][0]["text"])[:70].replace("\n", " ") + extra)
