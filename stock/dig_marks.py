"""경제 공부(디그) 글 + 신문 요약 화면의 사설 형광펜: 관리자만 서버에 보관 (2026-11-09 사용자 요청).

글자를 끌어 선택해 노랑·빨강·파랑으로 칠한 표시를 호(날짜)별로 저장한다. 일반 이용자는 읽기·쓰기 모두 못 하고(403),
관리자가 칠한 표시는 일반 이용자 화면에 나오지 않는다. 신문 지면 형광펜(news_marks.py)과 같은 관리자 판별
(로그인 관리자 또는 서버 IP 관리자 = 첫 관리자 계정)과 같은 저장소(gate.sqlite)를 쓴다.

표시 하나 = 글 덩어리(문단·제목·요약 줄…) 번호 u + 그 덩어리 글자 안 시작 s·끝 e + 색 c + 확인용 앞부분 글 q.
  · 글자 위치(글자 수)로 저장하므로 화면 크기·글자 크기·다크/화이트가 달라도 같은 글자에 붙는다.
  · 메일을 다시 읽어 글이 바뀌면 q 가 안 맞아 그 표시는 화면이 건너뛴다(엉뚱한 자리에 칠하지 않음).
저장은 호 하나당 한 줄(JSON) + 저장 버전(revision) — 다른 창에서 먼저 저장했으면 409 로 알려 덮어쓰지 않는다.
"""
import json
import re
from contextlib import closing, contextmanager

from fastapi import Request
from fastapi.responses import JSONResponse
import gate
from news_marks import owner                 # 관리자 판별(로그인 관리자 / IP 관리자 → 첫 관리자 계정)

MAX_BODY = 128 * 1024
MAX_MARKS = 800                              # 한 호에 칠할 수 있는 조각 수
ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}")     # 디그 호 번호 = 날짜(dig_mail 과 같은 모양)
COLORS = ("y", "r", "b")                     # 노랑·빨강·파랑
ED_PREFIX = "ed-"                            # 사설 표시는 같은 표에 이 글자를 앞에 붙여 저장(같은 날짜의 디그 표시와 분리)


@contextmanager
def db():
    con = gate._db()
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS dig_marks(
            owner INTEGER NOT NULL, issue TEXT NOT NULL, marks TEXT NOT NULL, revision INTEGER NOT NULL,
            PRIMARY KEY(owner, issue))""")
        with con:
            yield con
    finally:
        con.close()


def validate(b):
    """요청 본문 검사. 통과하면 깨끗이 다듬은 표시 목록을 돌려주고, 아니면 ValueError(사용자에게 보일 말)."""
    if not isinstance(b, dict) or not isinstance(b.get("id"), str) or not ID_RE.fullmatch(b["id"]):
        raise ValueError("호 번호를 확인해 주세요.")
    if type(b.get("revision")) is not int or b["revision"] < 0:
        raise ValueError("저장 버전을 확인해 주세요.")
    marks = b.get("marks")
    if not isinstance(marks, list) or len(marks) > MAX_MARKS:
        raise ValueError("표시가 너무 많아요.")
    clean = []
    for m in marks:
        if not isinstance(m, dict):
            raise ValueError("표시 모양을 확인해 주세요.")
        u, s, e, c, q = m.get("u"), m.get("s"), m.get("e"), m.get("c"), m.get("q")
        if any(type(v) is not int for v in (u, s, e)) or not (0 <= u <= 5000 and 0 <= s < e <= 20000):
            raise ValueError("표시 위치를 확인해 주세요.")
        if c not in COLORS:
            raise ValueError("표시 색을 확인해 주세요.")
        if not isinstance(q, str) or len(q) > 60:
            raise ValueError("표시 글자를 확인해 주세요.")
        clean.append({"u": u, "s": s, "e": e, "c": c, "q": q})
    return clean


def reply(data, code=200):
    return JSONResponse(data, status_code=code, headers={"Cache-Control": "no-store"})


def load(uid, issue):
    with db() as con:
        row = con.execute("SELECT marks, revision FROM dig_marks WHERE owner=? AND issue=?", (uid, issue)).fetchone()
    return (json.loads(row["marks"]), row["revision"]) if row else ([], 0)


def _get(request, day, prefix):
    uid = owner(request)
    if uid is None:
        return reply({"ok": False, "reason": "forbidden"}, 403)
    if not ID_RE.fullmatch(day or ""):
        return reply({"ok": False, "message": "호 번호를 확인해 주세요."}, 400)
    marks, rev = load(uid, prefix + day)
    return reply({"ok": True, "marks": marks, "revision": rev})


async def _put(request, prefix):
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
        marks = validate(b)
    except (ValueError, TypeError):
        return reply({"ok": False, "message": "표시 데이터를 확인해 주세요."}, 400)
    key = prefix + b["id"]
    with db() as con:
        row = con.execute("SELECT revision FROM dig_marks WHERE owner=? AND issue=?", (uid, key)).fetchone()
        cur = row["revision"] if row else 0
        if cur != b["revision"]:                       # 다른 창이 먼저 저장했다 → 덮어쓰지 않고 최신을 알려 줌
            cur_marks = json.loads(con.execute("SELECT marks FROM dig_marks WHERE owner=? AND issue=?", (uid, key)).fetchone()["marks"]) if row else []
            return reply({"ok": False, "conflict": True, "message": "다른 창에서 먼저 저장했어요.", "marks": cur_marks, "revision": cur}, 409)
        con.execute("INSERT OR REPLACE INTO dig_marks(owner, issue, marks, revision) VALUES(?,?,?,?)",
                    (uid, key, json.dumps(marks, ensure_ascii=False, separators=(",", ":")), cur + 1))
    return reply({"ok": True, "revision": cur + 1, "count": len(marks)})


def install(app):
    # ① 경제 공부(디그) 글: 호 번호(날짜) 그대로 저장
    @app.get("/api/dig/marks")
    def get_dig_marks(request: Request, id: str = ""):
        """관리자가 칠한 표시. 관리자가 아니면 403 → 화면은 형광펜 단추 자체를 안 보인다."""
        return _get(request, id, "")

    @app.post("/api/dig/marks")
    async def put_dig_marks(request: Request):
        """본문 {"id":"YYYY-MM-DD","revision":N,"marks":[...]} → 통째로 저장(버전이 맞을 때만)."""
        return await _put(request, "")

    # ② 신문 요약 화면 맨 아래 '사설'(2026-11-09 사용자 요청: 디그와 같은 방식): 같은 표에 'ed-' 를 붙여 따로 저장 → 같은 날짜의 디그와 안 섞임
    @app.get("/api/news/edmarks")
    def get_ed_marks(request: Request, date: str = ""):
        return _get(request, date, ED_PREFIX)

    @app.post("/api/news/edmarks")
    async def put_ed_marks(request: Request):
        """본문 {"id":"YYYY-MM-DD"(사설 날짜),"revision":N,"marks":[...]}"""
        return await _put(request, ED_PREFIX)
