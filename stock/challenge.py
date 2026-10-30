# -*- coding: utf-8 -*-
"""
challenge.py — 🔥 찰스 챌린지 (2026-10-30, 계획서: docs/challenge-plan.md)

[한 줄 요약]
  관리자가 '찰스'로 지정한 사람은 평일마다 그날 종이신문 사진 중 하나를 골라
  WHAT / WHY / HOW / 생각 & 투자에 적용할 점 을 쓴다. 기수 기간의 평일을 모두 채우면
  🎉 축하 팝업 + 자동으로 '무기한 일반 이용' 권한이 생긴다.

[규칙 — 계획서 3장 결정]
  D1 하루 완료 = 그날 글 1개 이상(또는 관리자 '인정')
  D2 하루에 여러 기사 가능(사진 1장당 1개, 다시 저장하면 수정)
  D3 쓰기·고치기는 '오늘 신문'만, 그날 밤 12시(한국 시간)까지
  D4 의무일 = 기수 기간의 평일 중 신문 사진이 올라온 날(휴간·공휴일·수집 실패는 자동 제외)
  D5 4칸 모두 10자 이상 2,000자 이하
  D6 같은 기수 글은 '그날 내 글을 저장한 뒤'에 열린다(지난 날은 마감됐으니 그냥 열림)
  D7 빠진 날이 있으면 완수 불가 → 관리자가 그날을 '인정'하면 구제
  D8 찰스의 이용 기한 = 기수 종료일
  D10 관리자 글(cohort_id 없음)은 모든 기수에게 보인다
  📖 모르는 용어(2026-10-30 사용자 요청): HOW 와 생각 사이에 선택 칸(최대 5개). '뜻 찾기'를 누르면
     용어 글자만 GPT(openclaw 게이트웨이, ChatGPT Plus — 별도 키·요금 없음)에 보내 쉬운 풀이를 받고
     glossary 표에 저장해 모두가 같이 쓴다(같은 용어는 한 번만 묻는다). AI 풀이는 틀릴 수 있다고 화면에 표시한다(2026-10-30 사용자 요청으로 사전 링크는 뺌).

[저장] 로그인 게이트와 같은 DB(gate.sqlite)의 cohorts / challenge_posts / challenge_excused / challenge_days 표.
[사진] 신문 사진은 14일 뒤 지워지므로(retention_cleanup.py), 글을 쓴 장은 gate 폴더의 challenge_photos/ 에 복사해 둔다.
"""

import html
import json
import os
import re
import shutil
import threading
import time
import unicodedata
import urllib.parse
from datetime import date as _date, datetime, timedelta

import urllib.error
import urllib.request

import gate

try:
    import news_files as _news
except Exception:                       # 신문 모듈이 없어도 챌린지 화면 자체는 뜬다(사진만 '없음')
    _news = None

FIELDS = (("what", "WHAT"), ("why", "WHY"), ("how", "HOW"), ("think", "생각 & 투자에 적용할 점"))
MIN_LEN, MAX_LEN = 10, 2000
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")
CELEBRATE_TEXT = "꾸준함은 인생을 바꿀 수 있습니다"
MAX_TERMS, TERM_LEN = 5, 30                # 모르는 용어: 글 하나에 5개까지, 용어 하나 30자까지
TERM_DAILY = 40                            # 한 사람이 하루에 새로 AI 에 물을 수 있는 용어 수(이미 풀이된 용어는 무료)

_rate = {}                               # {회원번호: [최근 저장 시각들]} 1분 30번 넘으면 거부
_term_rate = {}                          # {(회원번호, 날짜): 오늘 AI 에 물은 용어 수}
_term_locks = {}                         # 같은 용어를 동시에 두 번 묻지 않게
_term_locks_guard = threading.Lock()
_arch_lock = threading.Lock()


# ───────────────────────── 날짜 ─────────────────────────
def today():
    """오늘(한국 시간). 시험에서 바꿔 끼울 수 있게 함수로."""
    return gate._today()


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def is_weekday(day):
    return _d(day).weekday() < 5


def weekdays(start, end):
    out, d, e = [], _d(start), _d(end)
    while d <= e:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ───────────────────────── 기수 ─────────────────────────
def list_cohorts():
    with gate._db() as con:
        return con.execute("SELECT * FROM cohorts ORDER BY start_date DESC, id DESC").fetchall()


def get_cohort(cid):
    if not cid:
        return None
    try:
        with gate._db() as con:
            return con.execute("SELECT * FROM cohorts WHERE id=?", (int(cid),)).fetchone()
    except Exception:
        return None


def _check_cohort(name, start, end):
    name = re.sub(r"\s+", " ", (name or "")).strip()
    if not (1 <= len(name) <= 20) or not gate.valid_date(start or "") or not gate.valid_date(end or ""):
        return None
    if start > end or (_d(end) - _d(start)).days > 366:
        return None
    return name


def add_cohort(name, start, end, memo=""):
    """성공하면 ('ok', id), 아니면 ('bad'|'dup', None)."""
    n = _check_cohort(name, start, end)
    if not n:
        return "bad", None
    try:
        with gate._db() as con:
            cur = con.execute("INSERT INTO cohorts(name,start_date,end_date,memo,created_at) VALUES(?,?,?,?,?)",
                              (n, start, end, (memo or "")[:200], gate._now()))
            return "ok", cur.lastrowid
    except Exception:
        return "dup", None


def edit_cohort(cid, name, start, end):
    """기간을 바꾸면 그 기수 찰스들의 이용 기한(= 종료일)도 같이 바꾼다(D8)."""
    n = _check_cohort(name, start, end)
    if not n or not get_cohort(cid):
        return "bad"
    try:
        with gate._db() as con:
            con.execute("UPDATE cohorts SET name=?, start_date=?, end_date=? WHERE id=?", (n, start, end, int(cid)))
            con.execute("UPDATE users SET expires_at=? WHERE cohort_id=? AND role='charles' AND is_admin=0", (end, int(cid)))
        return "ok"
    except Exception:
        return "dup"


def delete_cohort(cid):
    with gate._db() as con:
        if con.execute("SELECT 1 FROM users WHERE cohort_id=?", (int(cid),)).fetchone():
            return "busy"
        con.execute("DELETE FROM cohorts WHERE id=?", (int(cid),))
    return "ok"


def set_charles(uid, on, cohort_id=None):
    """관리 화면 ☑ 찰스. 켜면: 찰스 + 기수 + 승인 + 이용 기한 = 기수 종료일. 끄면: 일반 사용자(기한은 그대로)."""
    if on:
        c = get_cohort(cohort_id)
        if not c:
            return "nocohort"
        with gate._db() as con:
            con.execute("UPDATE users SET role='charles', cohort_id=?, status='approved', expires_at=?, celebrated_at=NULL, apply=NULL "
                        "WHERE id=? AND is_admin=0", (c["id"], c["end_date"], int(uid)))
        return "on"
    with gate._db() as con:
        con.execute("UPDATE users SET role=NULL WHERE id=? AND is_admin=0", (int(uid),))
    return "off"


def excuse(uid, day, admin_id):
    """관리자가 빠진 날을 '인정'(D7)."""
    if not gate.valid_date(day or ""):
        return False
    with gate._db() as con:
        con.execute("INSERT OR REPLACE INTO challenge_excused(user_id,day,by_admin,at) VALUES(?,?,?,?)",
                    (int(uid), day, int(admin_id or 0), gate._now()))
    u = gate.get_user(uid)
    if u:
        maybe_graduate(u)
    return True


# ───────────────────────── 신문 사진 ─────────────────────────
def _arch_dir(day):
    return os.path.join(gate.gate_dir(), "challenge_photos", day)


def paper_pages(day):
    """그날 신문 사진 이름 목록(없으면 None). 평일에 신문이 있었다는 사실은 기록해 둔다
    (신문 캐시는 14일 뒤 지워지므로, 지난 날의 '신문 있었음'을 이 기록으로 기억)."""
    idx = _news.load_index(day) if (_news is not None and gate.valid_date(day or "")) else None
    names = [im["name"] for im in (idx or {}).get("images") or [] if im.get("name")]
    if not names:
        return None
    try:
        with gate._db() as con:
            con.execute("INSERT OR IGNORE INTO challenge_days(day,pages,seen_at) VALUES(?,?,?)", (day, len(names), gate._now()))
    except Exception:
        pass
    return names


def paper_day(day, con=None):
    """그날 신문이 있었나(D4)."""
    if paper_pages(day):
        return True
    try:
        if con is not None:
            return bool(con.execute("SELECT 1 FROM challenge_days WHERE day=?", (day,)).fetchone())
        with gate._db() as c2:
            return bool(c2.execute("SELECT 1 FROM challenge_days WHERE day=?", (day,)).fetchone())
    except Exception:
        return False


def archived_pages(day):
    d = _arch_dir(day)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".arc") and NAME_RE.match(f[:-4]))


def _archive(day, name):
    """글을 쓴 장의 사진을 챌린지 폴더에 보관(긴 변 1600px JPG, Pillow 가 없으면 원본 복사). 이미 있으면 그대로."""
    if _news is None:
        return
    src = _news.resolve(day, name)
    if not src:
        return
    d = _arch_dir(day)
    dst = os.path.join(d, name + ".arc")
    with _arch_lock:
        if os.path.isfile(dst):
            return
        try:
            os.makedirs(d, exist_ok=True)
            tmp = dst + ".tmp"
            try:
                from PIL import Image
                with Image.open(src) as im:
                    if getattr(im, "is_animated", False):
                        im.seek(0)
                    im = im.convert("RGB")
                    im.thumbnail((1600, 1600 * 6))
                    im.save(tmp, "JPEG", quality=82, optimize=True)
            except Exception:
                shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
        except Exception as e:
            print("[challenge] 사진 보관 실패 %s/%s: %r" % (day, name, e))


def photo_path(day, name, thumb=False):
    """사진 파일 경로: 신문 캐시 → (지워졌으면) 챌린지 보관본. 이름은 허용 목록/보관 목록에 있을 때만."""
    if not gate.valid_date(day or "") or not NAME_RE.match(name or ""):
        return None
    if _news is not None:
        p = _news.ensure_thumb(day, name) if thumb else _news.resolve(day, name)
        if p:
            return p
    p = os.path.join(_arch_dir(day), name + ".arc")
    return p if os.path.isfile(p) else None


def _sniff(path):
    try:
        with open(path, "rb") as f:
            h = f.read(12)
    except OSError:
        return "application/octet-stream"
    if h[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if h[:4] == b"GIF8":
        return "image/gif"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


# ───────────────────────── 📖 모르는 용어 ─────────────────────────
def term_key(t):
    """같은 용어 판단용 키: 대소문자·띄어쓰기 차이 무시('PER'='per', '기준 금리'='기준금리')."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", t or "")).casefold()


def parse_terms(raw):
    """입력(목록 또는 쉼표·줄바꿈 글) → 다듬은 용어 목록(중복 제거, 5개·30자 제한). 잘못되면 ValueError(이유)."""
    if raw is None or raw == "":
        return []
    items = raw if isinstance(raw, list) else re.split(r"[,\n、，]+", str(raw))
    out, seen = [], set()
    for x in items:
        t = re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(x or ""))).strip(" ·-•")
        if not t:
            continue
        if len(t) > TERM_LEN:
            raise ValueError("termlen")
        if term_key(t) in seen:
            continue
        seen.add(term_key(t))
        out.append(t)
    if len(out) > MAX_TERMS:
        raise ValueError("termmany")
    return out


def dict_url(t):
    """AI 풀이를 사람이 확인할 수 있는 사전 검색 주소(네이버 지식백과 — 시사경제용어사전·한경 경제용어사전 등이 함께 나온다)."""
    return "https://terms.naver.com/search.naver?query=" + urllib.parse.quote(t)


def glossary_get(terms):
    """{키: 풀이} — 이미 저장된 풀이만."""
    keys = [term_key(t) for t in terms if t]
    if not keys:
        return {}
    with gate._db() as con:
        rows = con.execute("SELECT * FROM glossary WHERE key IN (%s)" % ",".join("?" * len(keys)), keys).fetchall()
    return {r["key"]: {"term": r["term"], "short": r["short"], "easy": r["easy"], "invest": r["invest"], "source": r["source"]} for r in rows}


TERM_SYSTEM = (
    "너는 한국 경제 신문을 처음 읽는 사람을 돕는 경제 용어 선생님이다. 중학생도 알아들을 쉬운 한국어로 설명한다.\n"
    "규칙: ① 정확한 일반적 정의만 쓴다. 특정 수치·날짜·최근 사건을 지어내지 않는다. ② 잘 모르거나 뜻이 여러 개라 애매하면 unsure 를 true 로 한다.\n"
    "③ 반드시 아래 JSON 한 덩어리로만 답한다(다른 글 금지).\n"
    '{"short":"한 줄 뜻(40자 이내)","easy":"쉬운 풀이 2~3문장(비유 하나 포함, 200자 이내)",'
    '"invest":"신문·투자에서 이 말이 나오면 무엇을 보면 되는지 1문장(120자 이내)","unsure":false}')


def gpt_chat(system, user):
    """openclaw 게이트웨이(ChatGPT Plus, mer_blog_slack.py 와 같은 방식) → 답 글. 실패는 예외. 시험에서 바꿔 끼운다."""
    token = gate._env("GATEWAY_TOKEN")
    if not token:
        raise RuntimeError("GATEWAY_TOKEN 이 .env 에 없습니다")
    url = gate._env("CHALLENGE_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions")
    model = gate._env("CHALLENGE_TERM_AGENT", gate._env("MER_SUMMARY_AGENT", "openclaw/debate-gpt"))
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = None
    for payload in ({"model": model, "messages": msgs, "max_tokens": 500, "temperature": 0.2}, {"model": model, "messages": msgs}):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            last = RuntimeError("게이트웨이 HTTP %d" % e.code)
            if e.code < 500:
                break
    raise last


def _parse_term_answer(txt):
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    clip = lambda k, n: re.sub(r"\s+", " ", str(d.get(k) or "")).strip()[:n]     # noqa: E731
    out = {"short": clip("short", 80), "easy": clip("easy", 400), "invest": clip("invest", 240)}
    if not out["short"] or not out["easy"]:
        return None
    if d.get("unsure") is True:
        out["short"] = "(AI 도 확실하지 않아요) " + out["short"]
    return out


def _term_lock(key):
    with _term_locks_guard:
        return _term_locks.setdefault(key, threading.Lock())


def lookup_terms(v, terms):
    """용어들의 풀이를 돌려준다. 저장된 건 그대로, 없는 건 AI 에 묻고 저장(용어 글자만 보냄).
    결과: [{"term","key","ok","short","easy","invest","source","dict","reason"}]"""
    out = []
    have = glossary_get(terms)
    day_key = (v["uid"], today())
    for t in terms:
        k = term_key(t)
        item = {"term": t, "key": k, "dict": dict_url(t)}
        if k in have:
            out.append(dict(item, ok=True, **have[k]))
            continue
        if _term_rate.get(day_key, 0) >= TERM_DAILY:
            out.append(dict(item, ok=False, reason="오늘은 뜻 찾기를 많이 썼어요. 내일 다시 눌러 주세요."))
            continue
        with _term_lock(k):
            again = glossary_get([t])                    # 기다리는 동안 다른 사람이 이미 찾았을 수 있다
            if k in again:
                out.append(dict(item, ok=True, **again[k]))
                continue
            _term_rate[day_key] = _term_rate.get(day_key, 0) + 1
            try:
                ans = _parse_term_answer(gpt_chat(TERM_SYSTEM, "용어: " + t + "\n(한국 경제 신문 기사에 나온 말)"))
            except Exception as e:
                print("[challenge] 용어 풀이 실패 %r: %r" % (t, e))
                ans = None
            if not ans:
                out.append(dict(item, ok=False, reason="AI 풀이를 받지 못했어요. 잠시 후 🔍 뜻 찾기를 다시 눌러 주세요."))
                continue
            with gate._db() as con:
                con.execute("INSERT OR IGNORE INTO glossary(key,term,short,easy,invest,source,created_at) VALUES(?,?,?,?,?,?,?)",
                            (k, t, ans["short"], ans["easy"], ans["invest"], "ai", gate._now()))
            out.append(dict(item, ok=True, source="ai", **ans))
    return out


def cohort_glossary(v, cohort_filter=None):
    """📖 기수 용어장: 우리 기수(+운영자) 글에 나온 모르는 용어를 모아 풀이와 함께.
    잠금 규칙은 글과 같다(D6) — 오늘 다른 사람 글의 용어는 내가 오늘 글을 쓴 뒤에만 보인다."""
    now = today()
    with gate._db() as con:
        q = ("SELECT p.user_id, p.day, p.terms FROM challenge_posts p JOIN users u ON u.id=p.user_id "
             "WHERE p.terms IS NOT NULL AND p.terms<>'[]'")
        args = []
        if v["admin"]:
            if cohort_filter:
                q += " AND (p.cohort_id=? OR p.cohort_id IS NULL)"
                args.append(int(cohort_filter))
        else:
            q += " AND (p.user_id=? OR p.cohort_id=? OR (p.cohort_id IS NULL AND u.is_admin=1))"
            args += [v["uid"], v["cohort_id"] or -1]
        rows = con.execute(q, args).fetchall()
        wrote_today = bool(v["uid"]) and bool(con.execute("SELECT 1 FROM challenge_posts WHERE user_id=? AND day=?", (v["uid"], now)).fetchone())
    open_today = v["admin"] or v["role"] == "graduate" or wrote_today
    agg = {}
    for r in rows:
        if r["day"] >= now and r["user_id"] != v["uid"] and not open_today:
            continue
        try:
            terms = json.loads(r["terms"] or "[]")
        except Exception:
            continue
        for t in terms:
            k = term_key(t)
            a = agg.setdefault(k, {"term": t, "key": k, "count": 0, "people": set(), "first": r["day"], "last": r["day"], "mine": False})
            a["count"] += 1
            a["people"].add(r["user_id"])
            a["first"], a["last"] = min(a["first"], r["day"]), max(a["last"], r["day"])
            a["mine"] = a["mine"] or r["user_id"] == v["uid"]
    gl = glossary_get([a["term"] for a in agg.values()])
    out = []
    for k, a in agg.items():
        g = gl.get(k, {})
        out.append({"term": a["term"], "key": k, "count": a["count"], "people": len(a["people"]), "first": a["first"], "last": a["last"],
                    "mine": a["mine"], "short": g.get("short"), "easy": g.get("easy"), "invest": g.get("invest"), "dict": dict_url(a["term"])})
    out.sort(key=lambda x: x["term"])
    return {"ok": True, "items": out, "can_lookup": bool(v["uid"]) and (can_write(v) or v["admin"])}


# ───────────────────────── 진행도·완수 ─────────────────────────
def _done_days(con, uid):
    days = {r[0] for r in con.execute("SELECT DISTINCT day FROM challenge_posts WHERE user_id=?", (uid,))}
    exc = {r[0] for r in con.execute("SELECT day FROM challenge_excused WHERE user_id=?", (uid,))}
    return days, exc


def progress(u, now=None):
    """기수 기간의 평일마다 상태를 매긴다.
    done 완료 · excused 인정 · missed 빠짐 · nopaper 신문 없음(제외) · today 오늘(아직) · wait 오늘(신문 아직) · future 남은 날"""
    c = get_cohort(u["cohort_id"]) if u is not None and "cohort_id" in u.keys() else None
    if not c:
        return None
    now = now or today()
    out, missed = [], []
    with gate._db() as con:
        done, exc = _done_days(con, u["id"])
        for day in weekdays(c["start_date"], c["end_date"]):
            if day > now:
                st = "future"
            elif day in done:
                st = "done"
            elif day in exc:
                st = "excused"
            elif day == now:
                st = "today" if paper_day(day, con) else "wait"
            elif paper_day(day, con):
                st = "missed"
                missed.append(day)
            else:
                st = "nopaper"
            out.append({"day": day, "state": st})
    ok = sum(1 for x in out if x["state"] in ("done", "excused"))
    total = sum(1 for x in out if x["state"] != "nopaper")
    # 완수: 남은 날·오늘 할 일이 없고, 빠진 날이 없고, 1일 이상 했을 때
    pending = any(x["state"] in ("future", "today", "wait") for x in out)
    completed = (not pending) and not missed and ok > 0
    return {"cohort": {"id": c["id"], "name": c["name"], "start": c["start_date"], "end": c["end_date"]},
            "days": out, "done": ok, "total": total, "missed": missed, "completed": completed,
            "active": c["start_date"] <= now <= c["end_date"]}


def maybe_graduate(u):
    """찰스가 완수했으면 '완수자 + 무기한 이용'으로 바꾼다. 바꿨으면 True."""
    if u is None or gate.role_of(u) != "charles" or u["is_admin"]:
        return False
    p = progress(u)
    if not p or not p["completed"]:
        return False
    with gate._db() as con:
        con.execute("UPDATE users SET role='graduate', status='approved', expires_at=NULL WHERE id=? AND role='charles'", (u["id"],))
    print("[challenge] 🎓 완수: 회원 %d (%s)" % (u["id"], p["cohort"]["name"]))
    return True


# ───────────────────────── 보는 사람 ─────────────────────────
def viewer(request):
    """지금 화면을 보는 사람(챌린지 기준). 볼 수 없으면 None."""
    if gate.is_ip_host(request):
        if gate.ip_admin_ok(request):
            return {"uid": 0, "admin": True, "role": None, "cohort_id": None, "nick": "IP 관리자", "user": None}
        return None
    u = gate.session_user(request)
    if not u or not gate.can_challenge(u):
        return None
    return {"uid": u["id"], "admin": gate.is_admin(u), "role": gate.role_of(u), "cohort_id": u["cohort_id"],
            "nick": gate.disp(u), "user": u}


def can_write(v, day=None):
    """오늘 글을 쓸 수 있나: 관리자(IP 관리자 제외) 또는 기간 중인 찰스."""
    day = day or today()
    if v is None or v["uid"] == 0:
        return False
    if v["admin"]:
        return True
    if v["role"] != "charles":
        return False
    c = get_cohort(v["cohort_id"])
    return bool(c and c["start_date"] <= day <= c["end_date"])


_WD = "월화수목금토일"


def _md(day):
    d = _d(day)
    return "%d월 %d일(%s)" % (d.month, d.day, _WD[d.weekday()])


def why_cant_write(v, day=None):
    """글을 못 쓰는 이유(쓸 수 있으면 빈 글). 화면이 '왜 입력 칸이 없는지' 알려 주는 데 쓴다."""
    day = day or today()
    if v is None or v["uid"] == 0:
        return "IP 관리자 모드에서는 글을 쓸 수 없어요(도메인 주소로 로그인해 주세요)."
    if v["admin"]:
        return ""
    if v["role"] == "graduate":
        return "🎓 챌린지를 완수했어요. 글은 기록으로 읽기만 할 수 있어요."
    if v["role"] != "charles":
        return "찰스만 글을 쓸 수 있어요."
    c = get_cohort(v["cohort_id"])
    if not c:
        return "기수가 정해지지 않았어요. 운영자에게 문의해 주세요."
    if day < c["start_date"]:
        return "%s 챌린지는 %s부터 시작해요. 그날부터 글을 쓸 수 있어요." % (c["name"], _md(c["start_date"]))
    if day > c["end_date"]:
        return "%s 챌린지 기간(%s까지)이 끝났어요." % (c["name"], _md(c["end_date"]))
    return ""


def day_allowed(v, day):
    """이 날짜를 볼 수 있나. 찰스·완수자는 자기 기수 기간 + 오늘."""
    if v["admin"]:
        return True
    c = get_cohort(v["cohort_id"])
    return day == today() or bool(c and c["start_date"] <= day <= c["end_date"])


def _post_dict(r, with_author=True):
    d = {"page": r["page"], "updated": r["updated_at"], "created": r["created_at"]}
    for k, _ in FIELDS:
        d[k] = r[k]
    try:
        d["terms"] = json.loads(r["terms"] or "[]")
    except Exception:
        d["terms"] = []
    if with_author:
        d["nick"] = r["nickname"] or "(닉네임 없음)"
        d["admin"] = bool(r["is_admin"])
        d["cohort"] = r["cohort_name"] or ""
    return d


def day_view(v, day, cohort_filter=None):
    """그날 화면에 필요한 것 한 번에: 사진 목록·내 글·같은 기수 글(D6 잠금 포함)."""
    now = today()
    names = paper_pages(day)
    archived = False
    if not names:
        names = archived_pages(day)
        archived = bool(names)
    with gate._db() as con:
        mine_rows = con.execute("SELECT * FROM challenge_posts WHERE user_id=? AND day=? ORDER BY page", (v["uid"], day)).fetchall() if v["uid"] else []
        q = ("SELECT p.*, u.nickname, u.is_admin, c.name AS cohort_name FROM challenge_posts p JOIN users u ON u.id=p.user_id "
             "LEFT JOIN cohorts c ON c.id=p.cohort_id WHERE p.day=? AND p.user_id<>?")
        args = [day, v["uid"]]
        if v["admin"]:
            if cohort_filter:
                q += " AND (p.cohort_id=? OR p.cohort_id IS NULL)"
                args.append(int(cohort_filter))
        else:
            q += " AND (p.cohort_id=? OR (p.cohort_id IS NULL AND u.is_admin=1))"
            args.append(v["cohort_id"] or -1)
        others = con.execute(q + " ORDER BY p.updated_at DESC", args).fetchall()
    mine = {r["page"]: _post_dict(r, False) for r in mine_rows}
    unlocked = v["admin"] or v["role"] == "graduate" or day < now or bool(mine)
    per_page = {}
    for r in others:
        per_page[r["page"]] = per_page.get(r["page"], 0) + 1
    images = [{"name": n, "thumb": "/api/challenge/photo?date=%s&name=%s&size=thumb" % (day, n),
               "full": "/api/challenge/photo?date=%s&name=%s" % (day, n),
               "mine": n in mine, "others": per_page.get(n, 0)} for n in (names or [])]
    shown = [t for p in list(mine.values()) + ([_post_dict(r) for r in others] if unlocked else []) for t in p.get("terms") or []]
    gl = glossary_get(shown)
    glossary = {term_key(t): dict(gl.get(term_key(t), {}), term=t, dict=dict_url(t)) for t in shown}
    return {"ok": True, "date": day, "today": day == now, "weekday": is_weekday(day), "ready": bool(names) and not archived,
            "glossary": glossary,
            "archived": archived, "images": images, "mine": mine,
            "writable": can_write(v, day) and day == now and is_weekday(day) and bool(names) and not archived,
            "why_not": ("주말에는 쓰지 않아요." if not is_weekday(day) else
                        "지난 날은 마감됐어요(읽기 전용)." if day < now else
                        "앞으로 올 날이에요." if day > now else
                        "오늘 신문이 아직 도착하지 않았어요." if not names or archived else
                        why_cant_write(v, day)),
            "others": {"locked": not unlocked, "count": len(others),
                       "posts": [_post_dict(r) for r in others] if unlocked else []}}


def _clean(t):
    return re.sub(r"[ \t]+\n", "\n", str(t or "").replace("\r\n", "\n")).strip()


def save_post(v, day, page, data):
    """글 저장(같은 장이면 수정). 성공하면 ('ok', None), 아니면 (이유, 칸 이름)."""
    if not can_write(v, day):
        return "nowrite", None
    if day != today() or not is_weekday(day):
        return "closed", None
    names = paper_pages(day) or []
    if page not in names:
        return "nopage", None
    vals = {}
    for k, label in FIELDS:
        t = _clean(data.get(k))
        if len(t) < MIN_LEN:
            return "short", k
        if len(t) > MAX_LEN:
            return "long", k
        vals[k] = t
    try:
        terms = parse_terms(data.get("terms"))
    except ValueError as e:
        return str(e), "terms"
    hist = [x for x in _rate.get(v["uid"], []) if time.time() - x < 60]
    if len(hist) >= 30:
        return "rate", None
    _rate[v["uid"]] = hist + [time.time()]
    cohort = None if v["admin"] else v["cohort_id"]
    now = gate._now()
    with gate._db() as con:
        con.execute("INSERT INTO challenge_posts(user_id,cohort_id,day,page,what,why,how,think,terms,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,day,page) DO UPDATE SET "
                    "what=excluded.what, why=excluded.why, how=excluded.how, think=excluded.think, terms=excluded.terms, updated_at=excluded.updated_at",
                    (v["uid"], cohort, day, page, vals["what"], vals["why"], vals["how"], vals["think"],
                     json.dumps(terms, ensure_ascii=False), now, now))
    _archive(day, page)
    return "ok", None


def delete_post(v, day, page):
    if not can_write(v, day) or day != today():
        return False
    with gate._db() as con:
        return con.execute("DELETE FROM challenge_posts WHERE user_id=? AND day=? AND page=?", (v["uid"], day, page)).rowcount > 0


def me_info(v):
    u = v["user"]
    if u is not None and gate.role_of(u) == "charles":
        if maybe_graduate(u):
            u = gate.get_user(u["id"])
            v = dict(v, role="graduate", user=u)
    p = progress(u) if (u is not None and u["cohort_id"]) else None
    celebrate = bool(u is not None and gate.role_of(u) == "graduate" and not u["celebrated_at"])
    d = today()
    out = {"ok": True, "nick": v["nick"], "admin": v["admin"], "role": v["role"], "today": d, "weekday": is_weekday(d),
           "can_write": can_write(v, d), "why_not": why_cant_write(v, d), "progress": p, "celebrate": celebrate, "celebrate_text": CELEBRATE_TEXT,
           "limits": {"min": MIN_LEN, "max": MAX_LEN, "terms": MAX_TERMS, "term_len": TERM_LEN}}
    if v["admin"]:
        out["cohorts"] = [{"id": c["id"], "name": c["name"], "start": c["start_date"], "end": c["end_date"]} for c in list_cohorts()]
    return out


# ───────────────────────── 웹 주소 ─────────────────────────
_ERR = {"nowrite": "지금은 글을 쓸 수 없어요(챌린지 기간이 아니거나 참가자가 아니에요).",
        "closed": "오늘 신문에만 쓸 수 있어요. 지난 날은 마감됐어요(밤 12시).",
        "nopage": "그 사진을 찾을 수 없어요. 새로고침해 주세요.",
        "short": "%s 칸을 %d자 이상 써 주세요.", "long": "%s 칸은 %d자까지 쓸 수 있어요.",
        "rate": "너무 빨리 저장하고 있어요. 잠시 후 다시 눌러 주세요.",
        "termlen": "모르는 용어는 하나에 %d자까지 써 주세요." % TERM_LEN,
        "termmany": "모르는 용어는 글 하나에 %d개까지예요." % MAX_TERMS}


def install(app):
    from fastapi import Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

    def deny():
        return JSONResponse({"ok": False, "reason": "forbidden"}, status_code=403)

    @app.get("/challenge", response_class=HTMLResponse)
    def challenge_page(request: Request):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "challenge_view.html")
        try:
            with open(p, encoding="utf-8") as f:
                return HTMLResponse(gate.fill_page(f.read(), request), headers={"Cache-Control": "no-store"})
        except Exception as e:
            return HTMLResponse("<h1>챌린지 화면 로드 실패</h1><pre>%s</pre>" % html.escape(str(e)), status_code=500)

    @app.get("/api/challenge/me")
    def api_me(request: Request):
        v = viewer(request)
        return JSONResponse(me_info(v)) if v else deny()

    @app.get("/api/challenge/day")
    def api_day(request: Request, date: str = "", cohort: str = ""):
        v = viewer(request)
        if not v:
            return deny()
        day = date or today()
        if not gate.valid_date(day):
            return JSONResponse({"ok": False, "reason": "날짜 형식은 YYYY-MM-DD"}, status_code=400)
        if not day_allowed(v, day):
            return JSONResponse({"ok": False, "reason": "range"}, status_code=403)
        return JSONResponse(day_view(v, day, cohort if (v["admin"] and cohort.isdigit()) else None))

    @app.get("/api/challenge/photo")
    def api_photo(request: Request, date: str = "", name: str = "", size: str = ""):
        v = viewer(request)
        if not v:
            return deny()
        if not gate.valid_date(date or "") or not day_allowed(v, date):
            return JSONResponse({"ok": False}, status_code=403)
        p = photo_path(date, name, thumb=(size == "thumb"))
        if not p:
            return JSONResponse({"ok": False, "reason": "그런 사진이 없어요"}, status_code=404)
        return FileResponse(p, media_type=_sniff(p), headers={"Cache-Control": "private, max-age=3600"})

    async def _json(request):
        try:
            d = json.loads((await request.body() or b"{}")[:20000])
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    @app.post("/api/challenge/post")
    async def api_post(request: Request):
        v = viewer(request)
        if not v:
            return deny()
        d = await _json(request)
        day, page = str(d.get("date") or ""), str(d.get("page") or "")
        code, field = save_post(v, day, page, d)
        if code != "ok":
            label = dict(FIELDS).get(field, "모르는 용어")
            msg = _ERR[code] % ((label, MIN_LEN) if code == "short" else (label, MAX_LEN)) if code in ("short", "long") else _ERR[code]
            return JSONResponse({"ok": False, "reason": code, "field": field, "message": msg}, status_code=400)
        return JSONResponse({"ok": True, "me": me_info(viewer(request)), "day": day_view(viewer(request), day)})

    @app.get("/api/challenge/glossary")
    def api_glossary(request: Request, cohort: str = ""):
        v = viewer(request)
        if not v:
            return deny()
        return JSONResponse(cohort_glossary(v, cohort if (v["admin"] and cohort.isdigit()) else None))

    @app.post("/api/challenge/terms")
    async def api_terms(request: Request):
        """📖 모르는 용어 뜻 찾기. 본문 {"terms":[...]} → 풀이 목록. 글을 쓸 수 있는 사람(찰스·관리자)만."""
        v = viewer(request)
        if not v or not (can_write(v) or v["admin"]) or not v["uid"]:
            return deny()
        d = await _json(request)
        try:
            terms = parse_terms(d.get("terms"))
        except ValueError as e:
            return JSONResponse({"ok": False, "reason": str(e), "message": _ERR[str(e)]}, status_code=400)
        import asyncio
        items = await asyncio.get_running_loop().run_in_executor(None, lookup_terms, v, terms)   # AI 기다리는 동안 서버가 멈추지 않게
        return JSONResponse({"ok": True, "items": items})

    @app.post("/api/challenge/delete")
    async def api_delete(request: Request):
        v = viewer(request)
        if not v:
            return deny()
        d = await _json(request)
        ok = delete_post(v, str(d.get("date") or ""), str(d.get("page") or ""))
        return JSONResponse({"ok": ok}, status_code=200 if ok else 400)

    @app.post("/api/challenge/celebrated")
    def api_celebrated(request: Request):
        v = viewer(request)
        if not v or not v["uid"]:
            return deny()
        with gate._db() as con:
            con.execute("UPDATE users SET celebrated_at=? WHERE id=? AND celebrated_at IS NULL", (gate._now(), v["uid"]))
        return JSONResponse({"ok": True})
