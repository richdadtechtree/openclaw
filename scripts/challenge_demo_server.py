#!/usr/bin/env python3
"""🔥 챌린지 화면 시험용 가짜 서버(개발 환경 전용). 진짜 서버의 .env·DB 는 건드리지 않는다.

임시 폴더에 가짜 신문(사진 12장)·기수(이번 주 월~금)·사용자(관리자·찰스 2명·일반)를 만들고
로그인 쿠키를 JSON 으로 알려 준다. scripts/test_challenge_view.js 가 이 서버를 띄워 화면을 검사한다.

실행: python3 scripts/challenge_demo_server.py --port 8765 --cookies /tmp/x.json [--today 2026-11-04]
"""
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "stock"))

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--cookies", required=True)
ap.add_argument("--today", default="2026-11-04")       # 수요일
a = ap.parse_args()

NEWS = tempfile.mkdtemp(prefix="chdemo_news_")
os.environ.update({
    "GATE_DIR": tempfile.mkdtemp(prefix="chdemo_gate_"), "OPENCLAW_ENV": "/nonexistent", "NEWS_CACHE_DIR": NEWS,
    "GATE_BASE_URL": "http://localhost:%d" % a.port, "GATE_GOOGLE_CLIENT_ID": "gid", "GATE_GOOGLE_CLIENT_SECRET": "gsec",
    "GATE_APPROVAL": "auto", "PRIVACY_OPERATOR": "시험 운영자", "PRIVACY_CONTACT": "op@example.test"})
import gate       # noqa: E402
import challenge  # noqa: E402
from datetime import date, timedelta  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

TODAY = [a.today]
gate._today = lambda: TODAY[0]


def paper(day, n=12):
    from PIL import Image, ImageDraw
    d = os.path.join(NEWS, day)
    os.makedirs(d, exist_ok=True)
    imgs = []
    for i in range(1, n + 1):
        name = "%02d.jpg" % i
        im = Image.new("RGB", (900, 1300), (250, 248, 240))
        dr = ImageDraw.Draw(im)
        dr.rectangle([40, 40, 860, 160], fill=(30, 40, 60))
        dr.text((60, 80), "PAGE %d  %s" % (i, day), fill=(255, 255, 255))
        for y in range(200, 1260, 26):
            dr.line([60, y, 840 if (y // 26) % 7 else 500, y], fill=(150, 150, 150), width=3)
        im.save(os.path.join(d, name), "JPEG", quality=70)
        imgs.append({"name": name, "size": os.path.getsize(os.path.join(d, name))})
    with open(os.path.join(d, "index.json"), "w") as f:
        json.dump({"images": imgs}, f)


t = date.fromisoformat(a.today)
mon = t - timedelta(days=t.weekday())
for k in range(5):                     # 이번 주 월~금 신문(미래 날짜는 화면에 안 쓰이고, 날짜를 넘기는 검사용)
    paper((mon + timedelta(days=k)).isoformat())
challenge.add_cohort("1기", mon.isoformat(), (mon + timedelta(days=4)).isoformat())
cid = challenge.list_cohorts()[0]["id"]


def mk(uid, nick, role=None, admin=False):
    u = gate.upsert_login("google", uid)
    gate.record_consent(u["id"], ["privacy"], nick)
    if admin:
        gate.set_admin(u["id"], True)
    if role == "charles":
        challenge.set_charles(u["id"], True, cid)
    return u["id"]


ids = {"admin": mk("adm", "운영자", admin=True), "a": mk("a", "찰스에이", "charles"), "b": mk("b", "찰스비", "charles"),
       "g": mk("g", "일반인")}
# 지난 날(월요일)엔 A·B 가 이미 썼다고 해 둔다 → 달력에 ✅, B 는 화요일을 빼먹음(✗)
with gate._db() as con:
    for who in ("a", "b"):
        con.execute("INSERT INTO challenge_posts(user_id,cohort_id,day,page,what,why,how,think,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (ids[who], cid, mon.isoformat(), "01.jpg", "월요일 기사 요약입니다(%s)" % who, "중요한 이유를 적었습니다", "앞으로의 전망입니다",
                     "투자에 적용할 점입니다", mon.isoformat() + "T08:00:00", mon.isoformat() + "T08:00:00"))
    if t.weekday() >= 2:
        con.execute("INSERT INTO challenge_posts(user_id,cohort_id,day,page,what,why,how,think,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (ids["a"], cid, (mon + timedelta(days=1)).isoformat(), "02.jpg", "화요일 기사입니다", "이유입니다 이유입니다", "전망입니다 전망입니다",
                     "생각입니다 생각입니다", "x", "x"))

app = FastAPI()
gate.install(app)
for p in ("/economy", "/dig", "/ai"):
    app.add_api_route(p, (lambda p=p: HTMLResponse("<h1>%s</h1>" % p)), methods=["GET"])


@app.post("/__today")
def set_today(d: str):
    TODAY[0] = d
    return {"ok": True}


with open(a.cookies, "w") as f:
    json.dump({k: gate._session_token(v) for k, v in ids.items()}, f)

import uvicorn  # noqa: E402
uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
