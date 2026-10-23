#!/usr/bin/env python3
"""로그인·동의·승인 게이트(stock/gate.py) 검사. 실제 구글·카카오에는 접속하지 않는다(신원 확인 함수만 가짜로 교체).

필요: fastapi + httpx (없으면 건너뜀). 개발 환경 전용.
실행: python3 scripts/test_gate.py
"""
import os
import sys
import tempfile
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "stock"))
try:
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
except Exception as e:                                   # 개발 환경에 없으면 조용히 건너뜀
    print("건너뜀(fastapi/httpx 없음): %s" % e)
    sys.exit(0)

# ── 시험용 설정: 임시 폴더·가짜 키. 서버의 진짜 .env 는 읽지 않는다 ──
os.environ.update({
    "GATE_DIR": tempfile.mkdtemp(prefix="gatetest_"), "OPENCLAW_ENV": "/nonexistent",
    "GATE_BASE_URL": "https://example.test", "GATE_GOOGLE_CLIENT_ID": "gid", "GATE_GOOGLE_CLIENT_SECRET": "gsec",
    "GATE_KAKAO_REST_KEY": "kkey", "GATE_APPROVAL": "auto",
    "PRIVACY_OPERATOR": "홍길동", "PRIVACY_CONTACT": "op@example.test"})
import gate  # noqa: E402

fails = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        fails.append(name)


def make_app():
    """진짜 app.py 대신 같은 주소 모양의 가벼운 앱(안에 무거운 시세·스케줄러 없음)."""
    app = FastAPI()
    gate.install(app)

    @app.get("/slack")
    def slack(): return {"page": "slack"}

    @app.get("/slack/data")
    def sdata(): return {"messages": ["비밀 요약"]}

    @app.get("/dig")
    def dig(): return {"page": "dig"}

    @app.get("/api/dig/item")
    def ditem(): return {"ok": True}

    @app.get("/api/news/today")
    def ntoday(): return {"ok": True}

    @app.post("/api/dig/refresh")
    def drefresh(): return {"ok": True}

    @app.get("/")
    def dash(): return {"page": "dashboard"}

    @app.get("/who", include_in_schema=False)
    def who(request: Request):
        from fastapi.responses import HTMLResponse
        return HTMLResponse(gate.who_html(request) + "|" + gate.footer_html(request))

    return app


def client(app):
    return TestClient(app, base_url="https://example.test", follow_redirects=False)


def fake_identity(uid="g-1", nick="길동"):
    gate.identity_from_code = lambda provider, code: (uid, nick)


def login(c, provider="google", uid="g-1", nick="길동", nxt="/slack"):
    """시작 → (가짜) 콜백까지 진행. 콜백 응답을 돌려준다."""
    fake_identity(uid, nick)
    s = c.get("/gate/%s/start?next=%s" % (provider, urllib.parse.quote(nxt)))
    state = urllib.parse.parse_qs(urllib.parse.urlparse(s.headers["location"]).query)["state"][0]
    return c.get("/gate/%s/callback?code=abc&state=%s" % (provider, state))


AGREE = "agree_privacy=1&agree_age=1&agree_notice=1&next=%2Fslack"
FORM = {"content-type": "application/x-www-form-urlencoded"}

print("[작은 부품]")
tok = gate._sign({"uid": 7}, 60)
check("서명 쿠키가 맞으면 읽힌다", gate._unsign(tok)["uid"] == 7)
check("한 글자라도 바꾸면 거부", gate._unsign(tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None)
check("만료된 쿠키는 거부", gate._unsign(gate._sign({"uid": 7}, -5)) is None)
check("쓰레기 값은 거부(오류 없이)", gate._unsign("abc") is None and gate._unsign("") is None and gate._unsign("a.b") is None)
check("이동 주소: 우리 화면만 허용", gate.safe_next("/dig?id=2026-10-23") == "/dig?id=2026-10-23" and gate.safe_next("/slack") == "/slack")
check("이동 주소: 외부·가짜 주소 차단",
      all(gate.safe_next(x) == "/slack" for x in ("https://evil.com", "//evil.com", "/\\evil.com", "/gate/delete", "javascript:alert(1)", "/slack//evil", "")))

print("[잠금 전: 설정이 덜 된 경우 열려 있어야 함]")
saved = {k: os.environ.pop(k) for k in ("GATE_GOOGLE_CLIENT_ID", "GATE_GOOGLE_CLIENT_SECRET", "GATE_KAKAO_REST_KEY")}
c = client(make_app())
check("키가 없으면 잠금이 꺼져 /slack 이 그냥 열림(자동반영 사고 방지)", c.get("/slack").status_code == 200)
check("이때 로그인 화면은 '설정 필요' 안내", "설정되지 않았" in c.get("/gate/login").text)
os.environ.update(saved)

print("[로그인 전]")
c = client(make_app())
r = c.get("/slack")
check("/slack → 로그인 화면으로(돌아올 주소 포함)", r.status_code == 302 and urllib.parse.unquote(r.headers["location"]) == "/gate/login?next=/slack")
check("/dig → 로그인 화면으로", c.get("/dig").status_code == 302)
check("데이터 주소는 401(JSON)", c.get("/slack/data").status_code == 401 and c.get("/api/dig/item").status_code == 401 and c.get("/api/news/today").status_code == 401)
check("POST 도 401", c.post("/api/dig/refresh").status_code == 401)
check("주가 대시보드 '/' 는 그대로 열림", c.get("/").status_code == 200)
check("처리방침은 로그인 없이 공개", c.get("/privacy").status_code == 200 and "개인정보 처리방침" in c.get("/privacy").text)
lg = c.get("/gate/login").text
check("로그인 화면에 구글·카카오 버튼", "/gate/google/start" in lg and "/gate/kakao/start" in lg)

print("[소셜 로그인 시작]")
g = c.get("/gate/google/start?next=/dig").headers["location"]
q = urllib.parse.parse_qs(urllib.parse.urlparse(g).query)
check("구글 주소로 보내고 redirect_uri 가 우리 https 주소", g.startswith("https://accounts.google.com/") and q["redirect_uri"] == ["https://example.test/gate/google/callback"])
check("구글: 이메일 범위를 요청하지 않음(최소 수집)", q["scope"] == ["openid profile"] and "email" not in g)
k = urllib.parse.parse_qs(urllib.parse.urlparse(c.get("/gate/kakao/start").headers["location"]).query)
check("카카오: 닉네임만 요청", k["scope"] == ["profile_nickname"] and k["redirect_uri"] == ["https://example.test/gate/kakao/callback"])
check("상태 쿠키는 HttpOnly·Secure·SameSite=Lax", all(x in c.get("/gate/google/start").headers["set-cookie"] for x in ("HttpOnly", "Secure", "SameSite=lax")))

print("[콜백 보안]")
fake_identity()
c2 = client(make_app())
c2.get("/gate/google/start")
check("state 가 다르면 거부(CSRF)", c2.get("/gate/google/callback?code=x&state=WRONG").status_code == 400)
check("거부되면 로그인 쿠키가 안 생김", c2.get("/slack").status_code == 302)
c3 = client(make_app())
check("시작 없이 바로 콜백 와도 거부", c3.get("/gate/google/callback?code=x&state=abc").status_code == 400)
check("사용자가 취소(error)해도 거부", c3.get("/gate/google/callback?error=access_denied&state=a").status_code == 400)
c4 = client(make_app())
s = c4.get("/gate/google/start")
st = urllib.parse.parse_qs(urllib.parse.urlparse(s.headers["location"]).query)["state"][0]
check("구글 상태로 카카오 콜백을 부르면 거부", c4.get("/gate/kakao/callback?code=x&state=%s" % st).status_code == 400)

print("[가입 → 동의 → 입장 (자동 승인)]")
app = make_app()
c = client(app)
r = login(c)
check("로그인 직후엔 동의 화면으로", r.status_code == 302 and r.headers["location"].startswith("/gate/consent"))
check("세션 쿠키 보안 속성", all(x in r.headers["set-cookie"] for x in ("HttpOnly", "Secure", "SameSite=lax")))
check("동의 전에는 여전히 못 들어감", c.get("/slack").status_code == 302 and "/gate/consent" in c.get("/slack").headers["location"])
check("동의 전 데이터 주소는 403", c.get("/slack/data").status_code == 403)
cp = c.get("/gate/consent?next=/slack").text
check("동의 화면: 수집항목·목적·보유기간·거부권 표시", all(x in cp for x in ("수집 항목", "이용 목적", "보유 기간", "동의 거부")))
check("동의 화면: 필수 3칸(개인정보·만14세·이용안내)", all(x in cp for x in ("agree_privacy", "agree_age", "agree_notice")))
check("일부만 체크하면 거부(400)", c.post("/gate/consent", content="agree_privacy=1&next=%2Fslack", headers=FORM).status_code == 400)
check("거부되면 아직 못 들어감", c.get("/slack").status_code == 302)
check("3칸 모두 체크하면 통과", c.post("/gate/consent", content=AGREE, headers=FORM).status_code == 303)
check("이제 /slack 열림", c.get("/slack").status_code == 200 and c.get("/slack/data").status_code == 200)
check("이제 /dig·API 열림", c.get("/dig").status_code == 200 and c.get("/api/dig/item").status_code == 200 and c.post("/api/dig/refresh").status_code == 200)
check("잠긴 응답은 공용 캐시 금지(private)", "private" in c.get("/slack/data").headers.get("cache-control", ""))
check("동의 기록이 저장됨(버전 포함)", gate.get_user(1)["consent_version"] == gate.POLICY_VERSION)
with gate._db() as con:
    cons = con.execute("SELECT * FROM consents").fetchall()
check("동의 이력 1건", len(cons) == 1 and "privacy" in cons[0]["items"])
check("이미 동의한 사람이 로그인하면 바로 입장", client(app).get("/gate/login").status_code == 200 and login(client(app)).headers["location"] == "/slack")
check("DB 에 이메일·전화 같은 열이 없음(최소 수집)",
      {r["name"] for r in gate._db().execute("PRAGMA table_info(users)")} == {"id", "provider", "provider_uid", "nickname", "status", "consent_version", "consent_at", "created_at", "last_login_at"})

print("[누가 로그인했는지 화면에 표시]")
cg = client(make_app()); login(cg, provider="google", uid="w-1", nick="길동"); cg.post("/gate/consent", content=AGREE, headers=FORM)
w = cg.get("/who").text
check("구글로 들어오면 '길동 님 · 구글'이 보임", "길동 님 · 구글" in w and 'href="/gate/account"' in w)
ck = client(make_app()); login(ck, provider="kakao", uid="w-2", nick="카카오닉"); ck.post("/gate/consent", content=AGREE, headers=FORM)
check("카카오로 들어오면 '카카오닉 님 · 카카오'가 보임", "카카오닉 님 · 카카오" in ck.get("/who").text)
check("로그인 안 한 요청에는 이름이 안 보임", gate.who_html(None) == "" and "님 ·" not in client(make_app()).get("/who").text)
cx = client(make_app()); login(cx, uid="w-3", nick="<b onmouseover=1>x</b>"); cx.post("/gate/consent", content=AGREE, headers=FORM)
check("이름 속 HTML 은 이스케이프되어 표시", "<b onmouseover" not in cx.get("/who").text and "&lt;b" in cx.get("/who").text)

print("[내 정보·탈퇴]")
acc = c.get("/gate/account").text
check("내 정보에 닉네임 표시", "길동" in acc)
me = gate._unsign(c.cookies.get("gate_sess"))["uid"]                 # 이 시험의 사용자(다른 시험이 만든 사용자와 섞이지 않게 번호로 구분)
others = gate._db().execute("SELECT COUNT(*) FROM users WHERE id<>?", (me,)).fetchone()[0]
check("확인 체크 없이 탈퇴 누르면 안 지워짐", c.post("/gate/delete", content="", headers=FORM).status_code == 303 and gate.get_user(me) is not None)
r = c.post("/gate/delete", content="confirm=1", headers=FORM)
check("탈퇴하면 그 사용자와 동의 기록이 모두 삭제", r.status_code == 200 and gate.get_user(me) is None
      and not gate._db().execute("SELECT * FROM consents WHERE user_id=?", (me,)).fetchall())
check("다른 사용자의 정보는 건드리지 않음", gate._db().execute("SELECT COUNT(*) FROM users WHERE id<>?", (me,)).fetchone()[0] == others)
check("탈퇴 뒤 옛 쿠키로는 못 들어감", c.get("/slack").status_code == 302)

print("[다른 사이트에서 온 요청]")
c = client(make_app()); login(c); c.post("/gate/consent", content=AGREE, headers=FORM)
check("다른 사이트발 POST 거부(CSRF)", c.post("/api/dig/refresh", headers={"sec-fetch-site": "cross-site"}).status_code == 403
      and c.post("/gate/delete", content="confirm=1", headers=dict(FORM, **{"sec-fetch-site": "cross-site"})).status_code == 403)
check("같은 사이트 POST 는 정상", c.post("/api/dig/refresh", headers={"sec-fetch-site": "same-origin"}).status_code == 200)
r = login(client(make_app()), nxt="https://evil.com")
check("로그인 뒤 외부 주소로 안 튕김", "evil" not in r.headers["location"])

print("[이름에 악성 글자]")
c = client(make_app()); login(c, uid="x-9", nick="<script>alert(1)</script>"); c.post("/gate/consent", content=AGREE, headers=FORM)
acc = c.get("/gate/account").text
check("닉네임 속 HTML 이 글자로만 표시(XSS 방지)", "<script>alert(1)</script>" not in acc and "&lt;script&gt;" in acc)

print("[승인 방식 manual (나중 단계)]")
os.environ["GATE_APPROVAL"] = "manual"
app = make_app(); c = client(app)
r = login(c, uid="new-1", nick="새사람"); c.post("/gate/consent", content=AGREE, headers=FORM)
check("가입은 되지만 '승인 대기'", gate.get_user(gate._unsign(c.cookies.get("gate_sess"))["uid"])["status"] == "pending")
check("승인 전: 화면은 대기 페이지로, 데이터는 403", c.get("/slack").headers["location"] == "/gate/pending" and c.get("/slack/data").status_code == 403)
check("대기 페이지 표시", "승인을 기다리고" in c.get("/gate/pending").text)
uid = gate._unsign(c.cookies.get("gate_sess"))["uid"]
check("운영 명령 approve 로 승인", gate.cli(["approve", str(uid)]) == 0)
check("승인 뒤 바로 입장", c.get("/slack").status_code == 200)
gate.cli(["block", str(uid)])
check("차단하면 403", c.get("/slack").status_code == 403 and c.get("/slack/data").status_code == 403)
gate.cli(["approve", str(uid)])
os.environ["GATE_APPROVAL"] = "auto"

print("[auto 로 가입한 사람은 manual 로 바꿔도 유지]")
os.environ["GATE_APPROVAL"] = "auto"
c = client(make_app()); login(c, uid="old-1", nick="먼저온사람"); c.post("/gate/consent", content=AGREE, headers=FORM)
os.environ["GATE_APPROVAL"] = "manual"
c2 = client(make_app()); r = login(c2, uid="old-1", nick="먼저온사람")
check("이미 승인된 사람은 manual 전환 뒤 다시 로그인해도 바로 입장", r.headers["location"] == "/slack" and c2.get("/slack").status_code == 200)
c3 = client(make_app()); login(c3, uid="late-1", nick="나중사람"); c3.post("/gate/consent", content=AGREE, headers=FORM)
check("전환 뒤 가입한 사람은 승인 대기", c3.get("/slack").headers["location"] == "/gate/pending")
os.environ["GATE_APPROVAL"] = "auto"

print("[로그인 유지: 한 번 로그인·승인되면 계속]")
import time as _t  # noqa: E402
c = client(make_app()); r = login(c, uid="keep-1", nick="오래쓰는사람")
check("로그인 쿠키 유효기간이 1년(365일)", "Max-Age=31536000" in r.headers["set-cookie"])
c.post("/gate/consent", content=AGREE, headers=FORM)
uid = gate._unsign(c.cookies.get("gate_sess"))["uid"]
check("방금 발급된 쿠키는 매 요청마다 갈아 끼우지 않음", "set-cookie" not in c.get("/slack/data").headers)
old_tok = gate._sign({"uid": uid, "iat": int(_t.time()) - 10 * 86400}, 86400 * 355)      # 10일 전에 발급, 아직 355일 남음
c2 = client(make_app()); c2.cookies.set("gate_sess", old_tok)
r = c2.get("/slack/data")
check("10일 지난 쿠키로 쓰면 기간이 1년으로 자동 연장", r.status_code == 200 and "Max-Age=31536000" in r.headers.get("set-cookie", ""))
check("연장된 쿠키도 같은 사용자", gate._unsign(r.cookies.get("gate_sess"))["uid"] == uid)
legacy = gate._sign({"uid": uid}, 86400)                                                   # 예전 방식(iat 없음) 쿠키도 이어서 사용 + 연장
c3 = client(make_app()); c3.cookies.set("gate_sess", legacy)
r = c3.get("/slack/data")
check("예전 쿠키(발급시각 없음)도 정상 사용되고 1년짜리 새 쿠키로 교체", r.status_code == 200 and "gate_sess=" in r.headers.get("set-cookie", "") and "Max-Age=31536000" in r.headers["set-cookie"])
check("1년 안 쓰고 만료되면 로그인 필요", client(make_app()).get("/slack/data", headers={"cookie": "gate_sess=" + gate._sign({"uid": uid}, -5)}).status_code == 401)
gate.cli(["block", str(uid)])
c4 = client(make_app()); c4.cookies.set("gate_sess", old_tok)
r = c4.get("/slack/data")
check("차단된 사용자는 연장도 입장도 안 됨", r.status_code == 403 and "set-cookie" not in r.headers)
gate.cli(["approve", str(uid)])
c5 = client(make_app()); c5.cookies.set("gate_sess", old_tok)
r = c5.get("/gate/logout")
check("로그아웃 응답은 쿠키를 지움(연장하지 않음)", "Max-Age=0" in r.headers.get("set-cookie", "") and "Max-Age=31536000" not in r.headers.get("set-cookie", ""))
gate.delete_user(uid)
c6 = client(make_app()); c6.cookies.set("gate_sess", old_tok)
r = c6.get("/slack/data")
check("탈퇴한 사용자의 옛 쿠키는 연장 없이 거부", r.status_code == 401 and "set-cookie" not in r.headers)

print("[처리방침 문구가 바뀐 경우]")
c = client(make_app()); login(c, uid="v-1"); c.post("/gate/consent", content=AGREE, headers=FORM)
check("동의 후 입장", c.get("/slack").status_code == 200)
old = gate.POLICY_VERSION; gate.POLICY_VERSION = "2099-01-01"
check("버전이 바뀌면 다시 동의해야 함", c.get("/slack").status_code == 302 and "consent" in c.get("/slack").headers["location"])
gate.POLICY_VERSION = old

print("[서버 내부 열쇠 (PDF 만들기용)]")
c = client(make_app())
key = gate.internal_key()
check("내부 열쇠가 있으면 로그인 없이 통과", c.get("/dig", headers={"x-gate-internal": key}).status_code == 200)
check("틀린 열쇠는 거부", c.get("/dig", headers={"x-gate-internal": "x" * 40}).status_code == 302)
check("열쇠 파일은 본인만 읽기(600)", oct(os.stat(os.path.join(gate.gate_dir(), "internal.key")).st_mode)[-3:] == "600")
check("로컬 접속이라는 이유로는 통과시키지 않음(nginx 뒤 우회 방지)", c.get("/slack", headers={"x-forwarded-for": "127.0.0.1"}).status_code == 302)

print("[처리방침 필수 항목]")
pv = c.get("/privacy").text
check("보호책임자 이름·연락처 표시", "홍길동" in pv and "op@example.test" in pv)
check("법정 항목: 수집항목·목적·보유기간·제3자·권리·쿠키·안전조치·책임자·변경", all(x in pv for x in ("항목", "목적", "보유", "제3자", "열람", "쿠키", "안전성", "보호책임자", "변경")))
check("접속 기록(IP)이 자동 생성됨을 명시하고 보관 기간 표시", "접속 기록" in pv and "IP" in pv and "14일" in pv)
check("수집하지 않는 것을 명시(이메일 등)", "이메일" in pv and "수집하지 않습니다" in pv)
os.environ["PRIVACY_OPERATOR"] = ""
check("운영자 정보가 비면 빨간 안내(빈칸 공개 방지)", "PRIVACY_OPERATOR" in client(make_app()).get("/privacy").text)

print("\n결과:", "전부 통과" if not fails else "실패 %d개: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
