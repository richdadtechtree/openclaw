"""계정별 최신 신문 책갈피 한 개. 사용자 식별은 로그인 쿠키에서만 얻는다."""
import hmac
import json
import math
import re
from contextlib import closing
from datetime import date
from fastapi import Request
from fastapi.responses import JSONResponse
import gate

MAX_BODY = 4096
PAGE = re.compile(r"[A-Za-z0-9_-]{1,100}\.(?:jpg|jpeg|png|webp)", re.I)


def reply(data, status=200):
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


def account(request):
    deny = gate._check(request)
    if deny is not None:
        return None, deny
    if gate.is_ip_host(request):
        return (0, None) if gate.ip_admin_ok(request) else (None, reply({"ok": False}, 401))
    u = gate.session_user(request)
    return (u["id"], None) if u else (None, reply({"ok": False}, 401))


def validate(value):
    if not isinstance(value, dict):
        raise ValueError()
    day = value.get("date")
    if not isinstance(day, str) or len(day) != 10 or date.fromisoformat(day).isoformat() != day:
        raise ValueError()
    if value.get("edition") not in ("paper", "online") or value.get("view") not in ("summary", "page"):
        raise ValueError()
    if value.get("section") not in ("feed", "pod", "mk-ed"):
        raise ValueError()
    title = value.get("article", "")
    page = value.get("page", "")
    if not isinstance(title, str) or len(title) > 300 or not isinstance(page, str):
        raise ValueError()
    if value["view"] == "page" and (value["edition"] != "paper" or not PAGE.fullmatch(page)):
        raise ValueError()
    index, fraction, y = value.get("index", 0), value.get("fraction", 0), value.get("y", 0)
    if type(index) is not int or not 0 <= index <= 10000:
        raise ValueError()
    for number, maximum in ((fraction, 1), (y, 10000000)):
        if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= maximum:
            raise ValueError()
    return {"date": day, "edition": value["edition"], "view": value["view"], "section": value["section"],
            "article": title, "page": page if value["view"] == "page" else "",
            "index": index, "fraction": fraction, "y": y}


def install(app):
    @app.get("/api/news/bookmark")
    def get_bookmark(request: Request):
        uid, deny = account(request)
        if deny is not None:
            return deny
        with closing(gate._db()) as con:
            row = con.execute("SELECT payload,updated_at FROM news_bookmarks WHERE owner=?", (uid,)).fetchone()
        return reply({"ok": True, "bookmark": json.loads(row["payload"]) if row else None,
                      "updated_at": row["updated_at"] if row else None, "csrf": gate._csrf(uid)})

    @app.post("/api/news/bookmark")
    async def put_bookmark(request: Request):
        uid, deny = account(request)
        if deny is not None:
            return deny
        if request.headers.get("content-type", "").split(";")[0] != "application/json" or \
                request.headers.get("sec-fetch-site") == "cross-site" or not hmac.compare_digest(
                request.headers.get("x-csrf-token", "").encode(), gate._csrf(uid).encode()):
            return reply({"ok": False, "message": "새로고침한 뒤 다시 시도해 주세요."}, 403)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                return reply({"ok": False, "message": "책갈피 내용이 너무 길어요."}, 413)
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError()
            clear = body.get("action") == "clear"
            bookmark = None if clear else validate(body.get("bookmark"))
        except (ValueError, TypeError):
            return reply({"ok": False, "message": "책갈피 위치를 확인해 주세요."}, 400)
        updated = gate._now()
        with closing(gate._db()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            if uid > 0 and not con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
                return reply({"ok": False}, 401)
            if clear:
                con.execute("DELETE FROM news_bookmarks WHERE owner=?", (uid,))
            else:
                con.execute("""INSERT INTO news_bookmarks(owner,payload,updated_at) VALUES(?,?,?)
                    ON CONFLICT(owner) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at""",
                    (uid, json.dumps(bookmark, ensure_ascii=False), updated))
        return reply({"ok": True, "bookmark": bookmark, "updated_at": None if clear else updated})
