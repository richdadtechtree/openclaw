#!/usr/bin/env python3
"""🔥 찰스 챌린지(stock/challenge.py + gate.py 찰스 규칙) 검사. 가짜 날짜·가짜 신문 사진·가짜 로그인 쿠키로 시험한다.

필요: fastapi + httpx (없으면 건너뜀). 개발 환경 전용.
실행: python3 scripts/test_challenge.py
"""
import os
import re
import shutil
import sys
import tempfile
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "stock"))
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse
    from fastapi.testclient import TestClient
except Exception as e:
    print("건너뜀(fastapi/httpx 없음): %s" % e)
    sys.exit(0)

NEWS = tempfile.mkdtemp(prefix="chnews_")
os.environ.update({
    "GATE_DIR": tempfile.mkdtemp(prefix="chgate_"), "OPENCLAW_ENV": "/nonexistent", "NEWS_CACHE_DIR": NEWS,
    "GATE_BASE_URL": "https://example.test", "GATE_GOOGLE_CLIENT_ID": "gid", "GATE_GOOGLE_CLIENT_SECRET": "gsec",
    "GATE_APPROVAL": "auto", "PRIVACY_OPERATOR": "홍길동", "PRIVACY_CONTACT": "op@example.test"})
import gate       # noqa: E402
import challenge  # noqa: E402

fails = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        fails.append(name)


# ── 가짜 날짜(오늘) ──
TODAY = ["2026-11-02"]
gate._today = lambda: TODAY[0]


# ── 가짜 신문: 그날 폴더에 index.json + 사진 3장 ──
def make_jpg(path, color):
    from PIL import Image
    Image.new("RGB", (60, 90), color).save(path, "JPEG")


def paper(day, n=3):
    d = os.path.join(NEWS, day)
    os.makedirs(d, exist_ok=True)
    imgs = []
    for i in range(1, n + 1):
        name = "%02d.jpg" % i
        make_jpg(os.path.join(d, name), (i * 40, 80, 120))
        imgs.append({"name": name, "size": 100})
    import json
    with open(os.path.join(d, "index.json"), "w") as f:
        json.dump({"images": imgs}, f)


def unpaper(day):
    shutil.rmtree(os.path.join(NEWS, day), ignore_errors=True)


def make_app():
    app = FastAPI()
    gate.install(app)
    for path in ("/economy", "/dig", "/ai", "/api/news/today", "/api/dig/item", "/api/ai/feed", "/economy/data"):
        app.add_api_route(path, (lambda p=path: {"page": p}), methods=["GET"])

    @app.get("/navtest")
    def navtest(request: Request, cur: str = "dig"):
        return HTMLResponse(gate.fill_page('<nav><!--GATE_NAV:%s--><a href="/x">기본</a><!--/GATE_NAV--></nav>' % cur, request))
    return app


APP = make_app()


def user(uid_str, nick, admin=False):
    """가입 + 동의(닉네임) 끝낸 사용자와, 그 사람으로 로그인된 클라이언트."""
    u = gate.upsert_login("google", uid_str)
    gate.record_consent(u["id"], ["privacy"], nick)
    if admin:
        gate.set_admin(u["id"], True)
    c = TestClient(APP, base_url="https://example.test", follow_redirects=False)
    c.cookies.set("gate_sess", gate._session_token(u["id"]))
    return u["id"], c


def post(c, page="01.jpg", day=None, **kw):
    body = {"date": day or TODAY[0], "page": page, "what": "삼성전자 실적이 좋아졌다", "why": "반도체 가격이 올랐기 때문이다",
            "how": "다음 분기에도 이어질 것 같다", "think": "반도체 비중을 조금 늘려 볼 생각이다"}
    body.update(kw)
    return c.post("/api/challenge/post", json=body)


print("[관리자: 기수 만들기 · 찰스 지정]")
aid, ca = user("admin", "운영자", admin=True)
csrf = gate._csrf(aid)
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def act(**kw):
    kw.update(csrf=csrf)
    return ca.post("/gate/admin/act", content=urllib.parse.urlencode(kw), headers=FORM)


check("잘못된 기수(종료 < 시작) 거부", "m=cohort_bad" in act(action="cohort_add", name="1기", start="2026-11-06", end="2026-11-02").headers["location"])
check("기수 추가", "m=cohort_add" in act(action="cohort_add", name="1기", start="2026-11-02", end="2026-11-06").headers["location"])
check("같은 이름 기수 거부", "m=cohort_dup" in act(action="cohort_add", name="1기", start="2026-11-02", end="2026-11-06").headers["location"])
act(action="cohort_add", name="2기", start="2026-11-02", end="2026-11-20")
c1 = [c for c in challenge.list_cohorts() if c["name"] == "1기"][0]
c2 = [c for c in challenge.list_cohorts() if c["name"] == "2기"][0]
a_id, cA = user("A", "찰스에이")
b_id, cB = user("B", "찰스비")
x_id, cX = user("X", "다른기수")
g_id, cG = user("G", "일반인")
check("기수 없이 찰스 지정은 거부", "m=charles_nocohort" in act(action="charles", uid=a_id, on="1").headers["location"])
for uid, cid in ((a_id, c1["id"]), (b_id, c1["id"]), (x_id, c2["id"])):
    act(action="charles", uid=uid, on="1", cohort=cid)
ua = gate.get_user(a_id)
check("찰스 지정 → 역할·기수·이용 기한=기수 종료일", ua["role"] == "charles" and ua["cohort_id"] == c1["id"] and ua["expires_at"] == "2026-11-06")
adm = ca.get("/gate/admin").text
check("관리 화면에 기수 칸·찰스 칸이 보임", "찰스 기수" in adm and "🔥 찰스 · 기수" in adm and "1기" in adm)
check("관리 화면 '찰스' 필터", "찰스에이" in ca.get("/gate/admin?f=charles").text and "일반인" not in ca.get("/gate/admin?f=charles").text)
check("소속이 있는 기수는 삭제 불가", "m=cohort_busy" in act(action="cohort_del", cid=c1["id"]).headers["location"])

print("[권한: 찰스는 디그·챌린지만]")
nav = cA.get("/navtest").text
check("찰스 탭 = 디그·챌린지만", "/dig" in nav and "/challenge" in nav and "/economy" not in nav and "/ai" not in nav)
check("일반 사용자 탭 = 신문·디그·AI(챌린지 없음)", "/economy" in cG.get("/navtest").text and "/challenge" not in cG.get("/navtest").text)
check("관리자 탭 = 4개 모두", all(x in ca.get("/navtest").text for x in ("/economy", "/dig", "/ai", "/challenge")))
check("지금 화면 강조(aria-current)", 'href="/dig" aria-current="page"' in nav)
r = cA.get("/economy")
check("찰스가 신문 요약 주소를 치면 챌린지로", r.status_code == 302 and r.headers["location"] == "/challenge")
check("찰스는 신문·AI 데이터 403", cA.get("/api/news/today").status_code == 403 and cA.get("/api/ai/feed").status_code == 403)
check("찰스는 디그 열림", cA.get("/dig").status_code == 200 and cA.get("/api/dig/item").status_code == 200)
check("찰스는 챌린지 화면 열림", cA.get("/challenge").status_code == 200 and "챌린지" in cA.get("/challenge").text)
check("챌린지 화면 탭도 역할대로(찰스: 신문 요약 없음)", "/economy" not in cA.get("/challenge").text.split("</nav>")[0])
r = cG.get("/challenge")
check("일반 사용자는 챌린지 못 들어감", r.status_code == 302 and r.headers["location"] == "/economy" and cG.get("/api/challenge/me").status_code == 403)
check("로그인 안 하면 챌린지 → 로그인", TestClient(APP, base_url="https://example.test", follow_redirects=False).get("/challenge").headers["location"].startswith("/gate/login"))
check("로그인 후 돌아갈 곳에 /challenge 허용", gate.safe_next("/challenge") == "/challenge")

print("[오늘 쓰기 · 같은 기수 글 잠금(D6)]")
paper("2026-11-02")
me = cA.get("/api/challenge/me").json()
check("진행도: 1기 평일 5일, 오늘 차례", me["progress"]["total"] == 5 and me["progress"]["days"][0]["state"] == "today" and me["can_write"])
d = cA.get("/api/challenge/day").json()
check("오늘 사진 3장 · 쓸 수 있음", len(d["images"]) == 3 and d["writable"] and d["images"][0]["thumb"].startswith("/api/challenge/photo"))
check("사진 받기", cA.get(d["images"][0]["full"]).headers["content-type"] == "image/jpeg")
check("이상한 이름은 거부", cA.get("/api/challenge/photo?date=2026-11-02&name=../index.json").status_code == 404)
r = post(cA, what="짧음")
check("10자 미만 칸은 거부(어느 칸인지 알려 줌)", r.status_code == 400 and r.json()["field"] == "what")
check("없는 사진은 거부", post(cA, page="99.jpg").status_code == 400)
check("일반 사용자는 저장 불가", post(cG).status_code == 403)
check("A 저장", post(cA).json()["ok"])
check("같은 사진 다시 저장 = 수정(글 1개 유지)", post(cA, what="삼성전자 실적이 정말 좋아졌다").json()["day"]["mine"]["01.jpg"]["what"] == "삼성전자 실적이 정말 좋아졌다")
db = cB.get("/api/challenge/day").json()
check("B: 내 글 쓰기 전엔 잠김(글 수만 보임)", db["others"]["locked"] and db["others"]["count"] == 1 and db["others"]["posts"] == [])
check("B: 사진 위 '다른 글 수' 배지", db["images"][0]["others"] == 1)
post(cB, page="02.jpg")
db = cB.get("/api/challenge/day").json()
check("B: 내 글 저장 뒤엔 A 글이 열림", not db["others"]["locked"] and db["others"]["posts"][0]["nick"] == "찰스에이")
dx = cX.get("/api/challenge/day").json()
check("다른 기수(X)에겐 1기 글이 안 보임(개수도 0)", dx["others"]["count"] == 0)
post(ca, page="03.jpg", what="운영자가 쓴 오늘의 핵심 기사")
da = cA.get("/api/challenge/day").json()
check("운영자 글은 모든 기수에게(A 에게 '운영자' 표시)", any(p["admin"] and p["nick"] == "운영자" for p in da["others"]["posts"]))
check("운영자 글은 다른 기수(X)에게도 보임(잠금 상태 개수)", cX.get("/api/challenge/day").json()["others"]["count"] == 1)
dadm = ca.get("/api/challenge/day").json()
check("관리자는 모든 기수 글을 바로 봄", not dadm["others"]["locked"] and len(dadm["others"]["posts"]) == 2)
check("관리자 기수 고르기(2기만)", ca.get("/api/challenge/day?cohort=%d" % c2["id"]).json()["others"]["count"] == 0)
check("지운 글은 사라짐", cB.post("/api/challenge/delete", json={"date": "2026-11-02", "page": "02.jpg"}).json()["ok"]
      and cB.get("/api/challenge/day").json()["others"]["locked"])
post(cB, page="02.jpg")
check("글을 쓴 장은 사진 보관(신문 캐시가 지워져도 보이게)", os.path.isfile(os.path.join(os.environ["GATE_DIR"], "challenge_photos", "2026-11-02", "01.jpg.arc")))

print("[다음 날: 마감 · 지난 날 · 빠진 날 · 신문 없는 날]")
TODAY[0] = "2026-11-03"
paper("2026-11-03")
check("지난 날엔 쓸 수 없음", post(cA, day="2026-11-02").json()["reason"] == "closed")
check("지난 날 글은 내가 안 썼어도 열림(마감)", not cX.get("/api/challenge/day?date=2026-11-02").json()["others"]["locked"])
check("기수 기간 밖 날짜는 못 봄", cA.get("/api/challenge/day?date=2026-10-01").status_code == 403)
TODAY[0] = "2026-11-04"           # 11-03 에 A 가 안 씀 → 빠짐 / 11-04 는 신문 없음(휴간)
p = cA.get("/api/challenge/me").json()["progress"]
st = {x["day"]: x["state"] for x in p["days"]}
check("11-02 완료 · 11-03 빠짐 · 11-04 신문 대기", st["2026-11-02"] == "done" and st["2026-11-03"] == "missed" and st["2026-11-04"] == "wait")
TODAY[0] = "2026-11-05"
paper("2026-11-05")
st = {x["day"]: x["state"] for x in cA.get("/api/challenge/me").json()["progress"]["days"]}
check("신문 없던 평일(11-04)은 자동 제외", st["2026-11-04"] == "nopaper" and cA.get("/api/challenge/me").json()["progress"]["total"] == 4)
check("관리 화면에 빠진 날 [인정] 단추", "11-03 인정" in ca.get("/gate/admin").text)
check("관리자가 빠진 날 인정", "m=excuse" in act(action="excuse", uid=a_id, day="2026-11-03").headers["location"])
st = {x["day"]: x["state"] for x in cA.get("/api/challenge/me").json()["progress"]["days"]}
check("인정한 날은 '인정'으로", st["2026-11-03"] == "excused")

print("[완수 → 축하 · 무기한 · 모든 탭]")
post(cA)                                          # 11-05
TODAY[0] = "2026-11-06"
paper("2026-11-06")
me = cA.get("/api/challenge/me").json()
check("마지막 날 쓰기 전엔 아직 완수 아님", not me["progress"]["completed"] and not me["celebrate"])
r = post(cA).json()                               # 11-06 마지막 평일
check("마지막 날 저장 → 완수 + 축하 팝업", r["me"]["role"] == "graduate" and r["me"]["celebrate"] and r["me"]["celebrate_text"] == "꾸준함은 인생을 바꿀 수 있습니다")
ua = gate.get_user(a_id)
check("완수자 = 무기한 일반 이용", ua["role"] == "graduate" and ua["expires_at"] is None and ua["status"] == "approved")
check("완수자는 신문 요약 열림 + 탭 4개", cA.get("/economy").status_code == 200 and "/economy" in cA.get("/navtest").text and "/challenge" in cA.get("/navtest").text)
cA.post("/api/challenge/celebrated")
check("축하 팝업은 한 번만", not cA.get("/api/challenge/me").json()["celebrate"])
check("완수자는 더 이상 쓰지 않음(읽기 전용)", post(cA, page="02.jpg").status_code == 400)
check("관리 화면에 '🎓 완수'", "🎓 1기 완수" in ca.get("/gate/admin?f=graduate").text)

print("[완수 못 한 찰스: 기간 끝 → 기한 종료]")
TODAY[0] = "2026-11-09"
r = cB.get("/challenge")
check("B(빠진 날 있음)는 종료일 다음 날 '이용 기간 종료'", r.status_code == 403 and "이용 기간" in r.text)
check("관리자가 기수 기간을 늘리면 그 기수 찰스 기한도 같이", "m=cohort_edit" in act(action="cohort_edit", cid=c1["id"], name="1기", start="2026-11-02", end="2026-11-13").headers["location"]
      and gate.get_user(b_id)["expires_at"] == "2026-11-13")

print("[마지막 날이 휴간이면 다음 날 자동 완수]")
act(action="cohort_add", name="3기", start="2026-11-16", end="2026-11-20")
c3 = [c for c in challenge.list_cohorts() if c["name"] == "3기"][0]
y_id, cY = user("Y", "찰스와이")
act(action="charles", uid=y_id, on="1", cohort=c3["id"])
for day in ("2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"):
    TODAY[0] = day
    paper(day)
    post(cY)
TODAY[0] = "2026-11-21"                            # 11-20(금) 신문 없음, 토요일에 접속
r = cY.get("/challenge")
check("기한이 지났어도 완수 조건이면 기한 화면 대신 완수 처리", r.status_code == 200 and gate.get_user(y_id)["role"] == "graduate")

print("[보관 사진 · 탈퇴 · 화면]")
unpaper("2026-11-02")
d = ca.get("/api/challenge/day?date=2026-11-02")
check("신문 캐시가 지워진 날도 글 단 사진은 보관본으로 보임", d.status_code == 200 and d.json()["archived"] and "01.jpg" in [i["name"] for i in d.json()["images"]])
check("보관본 사진 받기", ca.get("/api/challenge/photo?date=2026-11-02&name=01.jpg").status_code == 200)
with gate._db() as con:
    n0 = con.execute("SELECT COUNT(*) FROM challenge_posts WHERE user_id=?", (b_id,)).fetchone()[0]
gate.delete_user(b_id)
with gate._db() as con:
    n1 = con.execute("SELECT COUNT(*) FROM challenge_posts WHERE user_id=?", (b_id,)).fetchone()[0]
check("탈퇴하면 챌린지 글도 삭제", n0 > 0 and n1 == 0)
check("처리방침에 챌린지 글·같은 기수 공개 명시", all(x in cA.get("/privacy").text for x in ("챌린지 글", "같은 기수 참가자")))
html_src = open(os.path.join(ROOT, "stock", "challenge_view.html"), encoding="utf-8").read()
check("화면은 남이 쓴 글을 이스케이프해서 넣음(esc)", "esc(p[f[0]])" in html_src and "innerHTML=esc" not in html_src)
check("축하 문구가 화면에 있음", "꾸준함은 인생을 바꿀 수 있습니다" in html_src)
for f in ("slack_digest_live.html", "dig_view.html", "ai_view.html", "challenge_view.html"):
    t = open(os.path.join(ROOT, "stock", f), encoding="utf-8").read()
    check("%s: 탭 자리표(GATE_NAV)가 짝 맞음" % f, len(re.findall(r"<!--GATE_NAV:\w+-->", t)) == 1 and t.count("<!--/GATE_NAV-->") == 1)

print("[📖 모르는 용어 · AI 풀이]")
TODAY[0] = "2026-11-10"
act(action="cohort_add", name="4기", start="2026-11-09", end="2026-11-20")
c4 = [c for c in challenge.list_cohorts() if c["name"] == "4기"][0]
z_id, cZ = user("Z", "찰스제트")
w_id, cW = user("W", "찰스더블유")
for uid in (z_id, w_id):
    act(action="charles", uid=uid, on="1", cohort=c4["id"])
paper("2026-11-10")
CALLS = []


def fake_gpt(system, user_msg):
    CALLS.append(user_msg)
    if "망가짐" in user_msg:
        return "죄송해요 잘 모르겠어요"                        # JSON 이 아닌 답
    term = user_msg.split("\n")[0].replace("용어: ", "")
    return '```json\n{"short":"%s 의 한 줄 뜻","easy":"쉬운 풀이 문장입니다. 비유도 있어요.","invest":"이럴 땐 금리를 보세요","unsure":false}\n```' % term


challenge.gpt_chat = fake_gpt
check("용어 입력 다듬기: 쉼표·줄바꿈 구분, 같은 말(띄어쓰기·대소문자) 한 번만", challenge.parse_terms("기준금리, 기준 금리\nPER,per") == ["기준금리", "PER"])
r = cZ.post("/api/challenge/terms", json={"terms": ["기준금리", "PER"]}).json()
check("뜻 찾기 → AI 풀이 2개(사전 링크 포함)", r["ok"] and all(i["ok"] for i in r["items"]) and r["items"][0]["short"] == "기준금리 의 한 줄 뜻"
      and r["items"][0]["dict"].startswith("https://terms.naver.com/search.naver?query="))
check("AI 에는 용어 글자만 보냄(닉네임·글 없음)", all("찰스" not in c and "삼성전자" not in c for c in CALLS) and CALLS[0].startswith("용어: 기준금리"))
n = len(CALLS)
r = cW.post("/api/challenge/terms", json={"terms": ["기준 금리"]}).json()
check("이미 풀이된 용어는 다시 묻지 않음(다른 사람·띄어쓰기 달라도)", len(CALLS) == n and r["items"][0]["ok"])
r = cZ.post("/api/challenge/terms", json={"terms": ["망가짐"]}).json()
check("AI 답이 이상하면 실패로 + 사전 링크 안내(지어내지 않음)", not r["items"][0]["ok"] and "사전" in r["items"][0]["reason"])
with gate._db() as con:
    check("실패한 풀이는 저장 안 함", con.execute("SELECT COUNT(*) FROM glossary WHERE key='망가짐'").fetchone()[0] == 0)
check("용어 6개는 거부", cZ.post("/api/challenge/terms", json={"terms": list("가나다라마바")}).status_code == 400)
check("31자 용어는 거부", cZ.post("/api/challenge/terms", json={"terms": ["가" * 31]}).status_code == 400)
check("일반 사용자는 뜻 찾기 불가", cG.post("/api/challenge/terms", json={"terms": ["PER"]}).status_code == 403)
r = post(cZ, terms=["기준금리", "PER"])
check("글에 용어 저장", r.json()["ok"] and r.json()["day"]["mine"]["01.jpg"]["terms"] == ["기준금리", "PER"])
check("용어 없이도 저장 가능(선택 칸)", post(cW, page="02.jpg").json()["ok"])
check("저장할 때 용어 6개는 거부", post(cZ, terms=list("가나다라마바")).json()["reason"] == "termmany")
dw = cW.get("/api/challenge/day").json()
zp = [p for p in dw["others"]["posts"] if p["nick"] == "찰스제트"][0]
check("같은 기수 글에 용어 + 풀이가 같이 옴", zp["terms"] == ["기준금리", "PER"] and dw["glossary"]["per"]["short"] == "PER 의 한 줄 뜻")
check("처리방침에 '용어 글자만 AI 에 보냄' 명시", "용어 글자만" in cZ.get("/privacy").text)
challenge._term_rate[(z_id, "2026-11-10")] = challenge.TERM_DAILY
r = cZ.post("/api/challenge/terms", json={"terms": ["새로운말"]}).json()
check("하루 한도를 넘으면 AI 대신 사전 안내", not r["items"][0]["ok"] and "많이" in r["items"][0]["reason"])
check("한도여도 이미 풀이된 용어는 보임", cZ.post("/api/challenge/terms", json={"terms": ["PER"]}).json()["items"][0]["ok"])

print("[📖 우리 기수 용어장]")
challenge._term_rate.clear()
v_id, cV = user("V", "찰스브이")
act(action="charles", uid=v_id, on="1", cohort=c4["id"])
post(cW, page="03.jpg", terms=["PER", "환율"])
gw = cW.get("/api/challenge/glossary").json()
per = [x for x in gw["items"] if x["key"] == "per"]
check("용어장: 우리 기수 용어 모음(같은 용어는 하나로, 몇 번·몇 명)", sorted(x["term"] for x in gw["items"]) == ["PER", "기준금리", "환율"]
      and per and per[0]["count"] == 2 and per[0]["people"] == 2 and per[0]["short"] == "PER 의 한 줄 뜻")
check("용어장: 내가 쓴 용어 표시", per[0]["mine"] and not [x for x in gw["items"] if x["key"] == "기준금리"][0]["mine"])
check("용어장: 풀이 없는 용어(환율)는 비어 있고 사전 링크는 있음", [x for x in gw["items"] if x["term"] == "환율"][0]["short"] is None
      and "terms.naver.com" in [x for x in gw["items"] if x["term"] == "환율"][0]["dict"])
check("용어장: 오늘 글을 안 쓴 찰스에겐 오늘 다른 사람 용어가 안 보임(D6)", cV.get("/api/challenge/glossary").json()["items"] == [])
check("용어장: 다른 기수엔 안 보임", cX.get("/api/challenge/glossary").json()["items"] == [] if gate.get_user(x_id)["expires_at"] >= TODAY[0] else True)
check("용어장: 관리자는 모든 기수", len(ca.get("/api/challenge/glossary").json()["items"]) >= 3)
check("용어장: 일반 사용자는 못 봄", cG.get("/api/challenge/glossary").status_code == 403)
TODAY[0] = "2026-11-11"
check("용어장: 다음 날엔 지난 날 용어가 열림", len(cV.get("/api/challenge/glossary").json()["items"]) == 3)

print("\n결과: %s" % ("전부 통과" if not fails else "실패 %d개: %s" % (len(fails), fails)))
sys.exit(1 if fails else 0)
