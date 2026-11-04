"""신문 지면 표시: 관리자만 날짜·지면별로 보관. 일반 이용자의 표시는 받지 않는다."""
import json
import math
import re
from contextlib import contextmanager, closing
from datetime import date as calendar_date

from fastapi import Request
from fastapi.responses import JSONResponse
import gate

MAX_BODY = 256 * 1024
PAGE_RE = re.compile(r"[A-Za-z0-9_-]{1,100}\.(?:jpg|jpeg|png|webp)", re.I)


def owner(request):
    if gate.is_ip_host(request):
        if not gate.ip_admin_ok(request):
            return None
        # IP 관리자는 기존 관리자 계정과 같은 표시를 이어 본다.
        with closing(gate._db()) as con:
            row = con.execute("SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
        return row["id"] if row else 0
    u = gate.session_user(request)
    return u["id"] if gate.is_admin(u) else None


@contextmanager
def db():
    con = gate._db()
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS news_marks(
            owner INTEGER NOT NULL, day TEXT NOT NULL, page TEXT NOT NULL,
            strokes TEXT NOT NULL, revision INTEGER NOT NULL,
            PRIMARY KEY(owner, day, page))""")
        with con:
            yield con
    finally:
        con.close()


def valid_day(day):
    return isinstance(day, str) and len(day) == 10 and calendar_date.fromisoformat(day).isoformat() == day


def validate(b):
    if not isinstance(b, dict) or not valid_day(b.get("date")):
        raise ValueError("날짜를 확인해 주세요.")
    if not isinstance(b.get("page"), str) or not PAGE_RE.fullmatch(b["page"]):
        raise ValueError("지면 이름을 확인해 주세요.")
    if type(b.get("revision")) is not int or b["revision"] < 0:
        raise ValueError("저장 버전을 확인해 주세요.")
    strokes = b.get("strokes")
    if not isinstance(strokes, list) or len(strokes) > 1000:
        raise ValueError("표시가 너무 많아요.")
    clean = []
    sticker_colors = {"WHAT": "#1d4ed8", "WHY": "#7c3aed", "HOW": "#047857", "CHECK": "#dc2626"}
    for s in strokes:
        if not isinstance(s, dict) or s.get("t") not in ("line", "oval", "free", "sticker"):
            raise ValueError("표시 종류를 확인해 주세요.")
        pts = s.get("pts")
        if not isinstance(pts, list) or not 1 <= len(pts) <= 10000 or (s["t"] != "free" and len(pts) != 2):
            raise ValueError("표시 좌표를 확인해 주세요.")
        for p in pts:
            if not isinstance(p, list) or len(p) != 2 or any(
                type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in p
            ):
                raise ValueError("표시 좌표를 확인해 주세요.")
        if s["t"] == "sticker":
            label = s.get("label")
            if label not in sticker_colors or not 0.005 <= pts[1][0]-pts[0][0] <= 0.5 or not 0.005 <= pts[1][1]-pts[0][1] <= 0.2:
                raise ValueError("스티커 종류와 크기를 확인해 주세요.")
            sticker = {"t": "sticker", "label": label, "c": sticker_colors[label], "w": 0.01, "pts": pts}
            if label == "CHECK" and "article" in s:
                article = s["article"]
                if not isinstance(article, str) or not re.fullmatch(r"[0-9A-Za-z가-힣]{1,60}", article):
                    raise ValueError("체크한 기사를 확인해 주세요.")
                sticker["article"] = article
            clean.append(sticker)
            continue
        if s.get("c") not in ("#ff5b5b", "#4da3ff", "#ffd93b"):
            raise ValueError("표시 색을 확인해 주세요.")
        w = s.get("w")
        if type(w) not in (int, float) or not math.isfinite(w) or not 0 < w <= 0.2:
            raise ValueError("표시 굵기를 확인해 주세요.")
        clean.append({"t": s["t"], "c": s["c"], "w": w, "pts": pts})
    return clean


def reply(data, code=200):
    return JSONResponse(data, status_code=code, headers={"Cache-Control": "no-store"})


def install(app):
    @app.get("/api/news/marks")
    def get_marks(request: Request, date: str = ""):
        uid = owner(request)
        if uid is None:
            return reply({"ok": False, "reason": "forbidden"}, 403)
        try:
            if not valid_day(date):
                raise ValueError()
        except ValueError:
            return reply({"ok": False, "message": "날짜를 확인해 주세요."}, 400)
        with db() as con:
            rows = con.execute("SELECT page, strokes, revision FROM news_marks WHERE owner=? AND day=?", (uid, date)).fetchall()
        return reply({"ok": True, "pages": {r["page"]: {"strokes": json.loads(r["strokes"]), "revision": r["revision"]} for r in rows}})

    @app.post("/api/news/marks")
    async def put_marks(request: Request):
        uid = owner(request)
        if uid is None:
            return reply({"ok": False, "reason": "forbidden"}, 403)
        if request.headers.get("content-type", "").split(";")[0] != "application/json" or request.headers.get("sec-fetch-site") == "cross-site":
            return reply({"ok": False, "message": "허용되지 않은 요청입니다."}, 403)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                return reply({"ok": False, "message": "표시가 너무 많아 저장하지 못했어요."}, 413)
        try:
            b = json.loads(raw)
            strokes = validate(b)
        except (ValueError, TypeError):
            return reply({"ok": False, "message": "표시 데이터를 확인해 주세요."}, 400)
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT revision FROM news_marks WHERE owner=? AND day=? AND page=?", (uid, b["date"], b["page"])).fetchone()
            revision = row["revision"] if row else 0
            if revision != b["revision"]:
                return reply({"ok": False, "message": "다른 창에서 표시가 바뀌었어요. 새로고침 후 다시 그어 주세요."}, 409)
            con.execute("INSERT OR REPLACE INTO news_marks VALUES(?,?,?,?,?)", (
                uid, b["date"], b["page"], json.dumps(strokes, separators=(",", ":")), revision + 1))
        return reply({"ok": True, "revision": revision + 1})
