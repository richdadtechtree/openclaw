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
_orig_identity = gate.identity_from_code      # 아래 시험들이 가짜로 바꾸므로 진짜 함수를 따로 보관

fails = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        fails.append(name)


def make_app():
    """진짜 app.py 대신 같은 주소 모양의 가벼운 앱(안에 무거운 시세·스케줄러 없음)."""
    app = FastAPI()
    gate.install(app)

    @app.get("/economy")
    def slack(): return {"page": "slack"}

    @app.get("/slack")
    def old_slack(): return {"page": "old"}

    @app.get("/economy/data")
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

    @app.get("/themehead", include_in_schema=False)
    def themehead(request: Request):
        from fastapi.responses import HTMLResponse
        return HTMLResponse(gate.theme_head(request))

    return app


def client(app):
    return TestClient(app, base_url="https://example.test", follow_redirects=False)


def fake_identity(uid="g-1", nick="길동"):
    gate.identity_from_code = lambda provider, code: uid          # 이름은 받지 않는다(닉네임은 가입 화면에서 직접 입력)


def login(c, provider="google", uid="g-1", nick="길동", nxt="/economy"):
    """시작 → (가짜) 콜백까지 진행. 콜백 응답을 돌려준다."""
    fake_identity(uid, nick)
    c._nick = nick                                                # 가입(동의) 때 입력할 닉네임
    s = c.get("/gate/%s/start?next=%s" % (provider, urllib.parse.quote(nxt)))
    state = urllib.parse.parse_qs(urllib.parse.urlparse(s.headers["location"]).query)["state"][0]
    return c.get("/gate/%s/callback?code=abc&state=%s" % (provider, state))


AGREE = "agree_privacy=1&agree_age=1&agree_notice=1&next=%2Feconomy"


def agree_for(cl, nick=None):
    """동의 3칸 + 닉네임을 채운 가입 본문."""
    return AGREE + "&nickname=" + urllib.parse.quote(nick or getattr(cl, "_nick", None) or "닉네임")
FORM = {"content-type": "application/x-www-form-urlencoded"}

print("[작은 부품]")
tok = gate._sign({"uid": 7}, 60)
check("서명 쿠키가 맞으면 읽힌다", gate._unsign(tok)["uid"] == 7)
check("한 글자라도 바꾸면 거부", gate._unsign(tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None)
check("만료된 쿠키는 거부", gate._unsign(gate._sign({"uid": 7}, -5)) is None)
check("쓰레기 값은 거부(오류 없이)", gate._unsign("abc") is None and gate._unsign("") is None and gate._unsign("a.b") is None)
check("이동 주소: 우리 화면만 허용", gate.safe_next("/dig?id=2026-10-23") == "/dig?id=2026-10-23" and gate.safe_next("/economy") == "/economy")
check("이동 주소: 외부·가짜 주소 차단",
      all(gate.safe_next(x) == "/economy" for x in ("https://evil.com", "//evil.com", "/\\evil.com", "/gate/delete", "javascript:alert(1)", "/economy//evil", "")))

print("[잠금 전: 설정이 덜 된 경우 열려 있어야 함]")
saved = {k: os.environ.pop(k) for k in ("GATE_GOOGLE_CLIENT_ID", "GATE_GOOGLE_CLIENT_SECRET", "GATE_KAKAO_REST_KEY")}
c = client(make_app())
check("키가 없으면 잠금이 꺼져 /slack 이 그냥 열림(자동반영 사고 방지)", c.get("/economy").status_code == 200)
check("이때 로그인 화면은 '설정 필요' 안내", "설정되지 않았" in c.get("/gate/login").text)
os.environ.update(saved)

print("[로그인 전]")
c = client(make_app())
r = c.get("/economy")
check("/economy → 로그인 화면으로(돌아올 주소 포함)", r.status_code == 302 and urllib.parse.unquote(r.headers["location"]) == "/gate/login?next=/economy")
check("/dig → 로그인 화면으로", c.get("/dig").status_code == 302)
check("옛 주소 /slack 도 똑같이 잠김(우회 불가)", c.get("/slack").status_code == 302 and c.get("/slack/data").status_code == 401)
check("데이터 주소는 401(JSON)", c.get("/economy/data").status_code == 401 and c.get("/api/dig/item").status_code == 401 and c.get("/api/news/today").status_code == 401)
check("POST 도 401", c.post("/api/dig/refresh").status_code == 401)
check("주가 대시보드 '/' 는 그대로 열림", c.get("/").status_code == 200)
check("처리방침은 로그인 없이 공개", c.get("/privacy").status_code == 200 and "개인정보 처리방침" in c.get("/privacy").text)
lg = c.get("/gate/login").text
check("로그인 화면에 구글·카카오 버튼", "/gate/google/start" in lg and "/gate/kakao/start" in lg)

print("[소셜 로그인 시작]")
g = c.get("/gate/google/start?next=/dig").headers["location"]
q = urllib.parse.parse_qs(urllib.parse.urlparse(g).query)
check("구글 주소로 보내고 redirect_uri 가 우리 https 주소", g.startswith("https://accounts.google.com/") and q["redirect_uri"] == ["https://example.test/gate/google/callback"])
check("구글: 이름·이메일을 요청하지 않음(openid 만)", q["scope"] == ["openid"] and "email" not in g and "profile" not in g)
k = urllib.parse.parse_qs(urllib.parse.urlparse(c.get("/gate/kakao/start").headers["location"]).query)
check("카카오: 닉네임·이메일 등 아무 정보도 요청하지 않음(scope 없음)", "scope" not in k and k["redirect_uri"] == ["https://example.test/gate/kakao/callback"])
check("상태 쿠키는 HttpOnly·Secure·SameSite=Lax", all(x in c.get("/gate/google/start").headers["set-cookie"] for x in ("HttpOnly", "Secure", "SameSite=lax")))

print("[콜백 보안]")
fake_identity()
c2 = client(make_app())
c2.get("/gate/google/start")
check("state 가 다르면 거부(CSRF)", c2.get("/gate/google/callback?code=x&state=WRONG").status_code == 400)
check("거부되면 로그인 쿠키가 안 생김", c2.get("/economy").status_code == 302)
c3 = client(make_app())
r3 = c3.get("/gate/google/callback?code=x&state=abc")
check("시작 없이 바로 콜백 와도 로그인 안 됨(오류 대신 로그인 화면으로)", r3.status_code == 302 and r3.headers["location"] == "/gate/login" and "gate_sess" not in r3.headers.get("set-cookie", ""))
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
check("동의 전에는 여전히 못 들어감", c.get("/economy").status_code == 302 and "/gate/consent" in c.get("/economy").headers["location"])
check("동의 전 데이터 주소는 403", c.get("/economy/data").status_code == 403)
cp = c.get("/gate/consent?next=/economy").text
check("동의 화면: 수집항목·목적·보유기간·거부권 표시", all(x in cp for x in ("수집 항목", "이용 목적", "보유 기간", "동의 거부")))
check("동의 화면: 필수 3칸(개인정보·만14세·이용안내)", all(x in cp for x in ("agree_privacy", "agree_age", "agree_notice")))
check("일부만 체크하면 거부(400)", c.post("/gate/consent", content="agree_privacy=1&next=%2Feconomy", headers=FORM).status_code == 400)
check("거부되면 아직 못 들어감", c.get("/economy").status_code == 302)
check("3칸 모두 체크하면 통과", c.post("/gate/consent", content=agree_for(c), headers=FORM).status_code == 303)
check("이제 /slack 열림", c.get("/economy").status_code == 200 and c.get("/economy/data").status_code == 200)
check("이제 /dig·API 열림", c.get("/dig").status_code == 200 and c.get("/api/dig/item").status_code == 200 and c.post("/api/dig/refresh").status_code == 200)
check("잠긴 응답은 공용 캐시 금지(private)", "private" in c.get("/economy/data").headers.get("cache-control", ""))
check("동의 기록이 저장됨(버전 포함)", gate.get_user(1)["consent_version"] == gate.POLICY_VERSION)
with gate._db() as con:
    cons = con.execute("SELECT * FROM consents").fetchall()
check("동의 이력 1건", len(cons) == 1 and "privacy" in cons[0]["items"])
gate.identity_from_code = lambda provider, code: (_ for _ in ()).throw(AssertionError("code 를 쓰면 안 됨"))
r = c.get("/gate/google/callback?code=OLD&state=OLD")
check("이미 로그인된 사람이 옛 콜백 주소를 다시 열면 오류 없이 바로 입장", r.status_code == 302 and r.headers["location"] == "/economy")
check("…취소(error) 주소여도 로그인돼 있으면 바로 입장", c.get("/gate/kakao/callback?error=access_denied").headers.get("location") == "/economy")
c.get("/gate/google/start?next=/dig")
check("…시작 기록이 있으면 원래 가려던 곳으로", c.get("/gate/google/callback?code=x&state=WRONG").headers.get("location") == "/dig")
fake_identity()
check("이미 동의한 사람이 로그인하면 바로 입장",client(app).get("/gate/login").status_code == 200 and login(client(app)).headers["location"] == "/economy")
check("DB 에 이메일·전화·실명 같은 열이 없음(최소 수집, 닉네임·화면 모드·챌린지 역할 열만 추가)",
      {r["name"] for r in gate._db().execute("PRAGMA table_info(users)")} == {"id", "provider", "provider_uid", "nickname", "status", "consent_version", "consent_at", "created_at", "last_login_at", "is_admin", "expires_at", "nick_set", "nick_key", "theme", "role", "cohort_id", "celebrated_at"})

print("[누가 로그인했는지 화면에 표시]")
cg = client(make_app()); login(cg, provider="google", uid="w-1", nick="누리"); cg.post("/gate/consent", content=agree_for(cg), headers=FORM)
w = cg.get("/who").text
check("구글로 들어오면 '누리 님 · 구글'이 보임(직접 정한 닉네임)", "누리 님 · 구글" in w and 'href="/gate/account"' in w)
ck = client(make_app()); login(ck, provider="kakao", uid="w-2", nick="카카오닉"); ck.post("/gate/consent", content=agree_for(ck), headers=FORM)
check("카카오로 들어오면 '카카오닉 님 · 카카오'가 보임", "카카오닉 님 · 카카오" in ck.get("/who").text)
check("로그아웃 버튼이 맨 위에 보임", 'class="logout" href="/gate/logout"' in w)
check("관리자가 아니면 '관리' 링크가 없음", "adminlink" not in w)
check("로그인 안 한 요청에는 이름이 안 보임", gate.who_html(None) == "" and "님 ·" not in client(make_app()).get("/who").text)
cx = client(make_app()); login(cx, uid="w-3", nick="엑스"); cx.post("/gate/consent", content=agree_for(cx), headers=FORM)
gate._db().execute("UPDATE users SET nickname=? WHERE provider_uid='w-3'", ("<b onmouseover=1>x</b>",)).connection.commit()   # 가정: 저장된 값이 이상한 경우
check("(혹시 저장된 값이 이상해도) 이름 속 HTML 은 이스케이프되어 표시", "<b onmouseover" not in cx.get("/who").text and "&lt;b" in cx.get("/who").text)

print("[관리자 화면: 가입자 보기·승인·차단]")
import re as _re  # noqa: E402


def mk_user(provider, uid, nick, consent=True):
    cl = client(app_adm); login(cl, provider=provider, uid=uid, nick=nick)
    if consent:
        cl.post("/gate/consent", content=agree_for(cl), headers=FORM)
    return cl, gate._unsign(cl.cookies.get("gate_sess"))["uid"]


def token_of(cl, page_text=None):
    html_ = page_text or cl.get("/gate/admin").text
    return _re.search(r'name="csrf" value="([0-9a-f]{32})"', html_).group(1)


def act(cl, uid, action, csrf, extra=""):
    return cl.post("/gate/admin/act", content="uid=%d&action=%s&csrf=%s%s" % (uid, action, csrf, extra), headers=FORM)


app_adm = make_app()
adm, adm_id = mk_user("google", "adm-1", "대표")
user_c, user_id = mk_user("kakao", "usr-1", "일반인")
check("관리자 지정 전: 일반 가입자는 /gate/admin 이 '없는 페이지'(404)", user_c.get("/gate/admin").status_code == 404 and adm.get("/gate/admin").status_code == 404)
check("로그인 안 한 사람도 404(존재를 알리지 않음)", client(app_adm).get("/gate/admin").status_code == 404)
check("서버 명령으로 관리자 지정", gate.cli(["admin", str(adm_id)]) == 0)
check("지정 뒤에는 위쪽에 '🛠 관리' 링크", "adminlink" in adm.get("/who").text and "adminlink" not in user_c.get("/who").text)
pg = adm.get("/gate/admin")
check("관리자는 가입자 목록을 봄(이름·방식·상태)", pg.status_code == 200 and "일반인" in pg.text and "카카오" in pg.text and "이용 가능" in pg.text)
check("일반 가입자는 여전히 404", user_c.get("/gate/admin").status_code == 404)
tok = token_of(adm, pg.text)
check("일반 가입자가 관리 버튼을 직접 보내도 아무 일 없음(404, 상태 그대로)",
      user_c.post("/gate/admin/act", content="uid=%d&action=block&csrf=%s" % (user_id, tok), headers=FORM).status_code == 404 and gate.get_user(user_id)["status"] == "approved")
check("확인표(csrf)가 틀리면 거부(400)", act(adm, user_id, "block", "0" * 32).status_code == 400 and gate.get_user(user_id)["status"] == "approved")
check("다른 사이트발 관리 요청은 거부", adm.post("/gate/admin/act", content="uid=%d&action=block&csrf=%s" % (user_id, tok),
                                      headers=dict(FORM, **{"sec-fetch-site": "cross-site"})).status_code == 403 and gate.get_user(user_id)["status"] == "approved")
r = act(adm, user_id, "block", tok)
check("차단: 목록으로 돌아오고 상태가 blocked", r.status_code == 303 and "m=block" in r.headers["location"] and gate.get_user(user_id)["status"] == "blocked")
check("차단된 사람은 로그인 쿠키가 있어도 즉시 못 씀", user_c.get("/economy/data").status_code == 403)
check("차단 안내 문구가 화면에 표시", "차단했어요" in adm.get(r.headers["location"]).text)
check("차단 해제(승인)로 다시 이용 가능", act(adm, user_id, "unblock", tok).status_code == 303 and user_c.get("/economy/data").status_code == 200)
check("관리자는 자기 자신을 차단·삭제할 수 없음(잠금 사고 방지)",
      "m=admin" in act(adm, adm_id, "block", tok).headers["location"] and "m=admin" in act(adm, adm_id, "delete", tok).headers["location"]
      and gate.get_user(adm_id)["status"] == "approved")
check("없는 번호는 안내만", "m=none" in act(adm, 99999, "block", tok).headers["location"])
check("모르는 동작은 무시", "m=none" in act(adm, user_id, "makeadmin", tok).headers["location"] and not gate.get_user(user_id)["is_admin"])
check("웹에서는 관리자 권한을 줄 수 없음(is_admin 변경 시도 무시)", not gate.get_user(user_id)["is_admin"])
f1 = adm.get("/gate/admin?f=pending").text
check("승인 대기 필터에는 이용 가능한 사람이 안 나옴", "일반인" not in f1)
gate.cli(["block", str(user_id)])
check("차단 필터에 차단된 사람이 나옴", "일반인" in adm.get("/gate/admin?f=blocked").text)
gate.cli(["approve", str(user_id)])
x_c, x_id = mk_user("google", "xss-1", "엑스에스")
gate._db().execute("UPDATE users SET nickname=? WHERE id=?", ("<img src=x onerror=alert(1)>", x_id)).connection.commit()
check("관리 화면에서도 (이상한 값이 저장돼 있어도) 이름 속 HTML 은 글자로만 표시", "<img src=x" not in adm.get("/gate/admin").text and "&lt;img" in adm.get("/gate/admin").text)
check("삭제: 사용자와 동의 기록이 지워짐", act(adm, x_id, "delete", tok).status_code == 303 and gate.get_user(x_id) is None
      and not gate._db().execute("SELECT * FROM consents WHERE user_id=?", (x_id,)).fetchall())
check("삭제된 사람의 쿠키는 즉시 무효", x_c.get("/economy/data").status_code == 401)
os.environ["GATE_APPROVAL"] = "manual"
n_c, n_id = mk_user("kakao", "new-2", "새가입자")
check("승인제에서 새 가입자는 승인 대기", gate.get_user(n_id)["status"] == "pending" and n_c.get("/economy/data").status_code == 403)
check("관리 화면 '승인 대기' 탭에 보이고 승인 버튼이 있음", "새가입자" in adm.get("/gate/admin?f=pending").text and 'value="approve"' in adm.get("/gate/admin?f=pending").text)
check("승인하면 바로 입장", act(adm, n_id, "approve", tok, "&f=pending").status_code == 303 and n_c.get("/economy/data").status_code == 200)
os.environ["GATE_APPROVAL"] = "auto"
gate.cli(["unadmin", str(adm_id)])
check("관리자에서 빼면 화면이 다시 404", adm.get("/gate/admin").status_code == 404 and adm.post("/gate/admin/act", content="uid=%d&action=block&csrf=%s" % (user_id, tok), headers=FORM).status_code == 404)
check("내 정보 화면에 회원 번호", ">%d<" % user_id in user_c.get("/gate/account").text)

print("[가입할 때 닉네임 입력]")
cn = client(make_app()); login(cn, uid="n-1", nick="처음닉")
un = gate.get_user(gate._unsign(cn.cookies.get("gate_sess"))["uid"])
check("로그인만 한 상태에서는 이름(닉네임)이 비어 있음 — 구글·카카오 이름을 저장하지 않음", un["nickname"] is None and un["nick_set"] == 0)
cp = cn.get("/gate/consent?next=/economy").text
check("가입 화면에 닉네임 입력 칸·안내(실명·전화번호·이메일 금지)가 있음", 'name="nickname"' in cp and "실명" in cp and "운영자에게 보여요" in cp and "같은 기수" in cp)
check("가입 화면의 수집 항목에 구글·카카오 이름은 받지 않는다고 안내", "이름·이메일은 받지 않아요" in cp)
check("닉네임 없이 동의만 하면 거부(400)하고 입장 불가", cn.post("/gate/consent", content=AGREE + "&nickname=", headers=FORM).status_code == 400 and cn.get("/economy/data").status_code == 403)
bad = {"한 글자": "가", "너무 김": "가" * 21, "특수문자": "나<b>x", "이메일 모양": "me@mail.com", "전화번호 모양": "010 1234 5678", "숫자만 길게": "20260101abc12345678", "기호만": "..__--", "예약어": "관리자", "예약어(영문 대소문자)": "ADMIN", "예약어(공백 끼움)": "운 영 자"}
for label, bn in bad.items():
    r = cn.post("/gate/consent", content=agree_for(cn, bn), headers=FORM)
    check("닉네임 거부 — " + label, r.status_code == 400 and gate.get_user(un["id"])["nick_set"] == 0)
r = cn.post("/gate/consent", content=agree_for(cn, "<b>나쁜</b>"), headers=FORM)
check("거부된 화면에도 입력값은 이스케이프되어 되돌려 줌(XSS 방지)", "<b>나쁜</b>" not in r.text and "&lt;b&gt;" in r.text and "한글·영문·숫자" in r.text)
r = cn.post("/gate/consent", content=agree_for(cn, "me@mail.com"), headers=FORM)
check("닉네임이 거부돼도 체크해 둔 동의 칸 3개는 그대로 유지", all('name="%s" value="1" checked' % k in r.text for k in ("agree_privacy", "agree_age", "agree_notice")))
r = cn.post("/gate/consent", content="agree_privacy=1&nickname=" + urllib.parse.quote("임시"), headers=FORM)
check("동의 칸이 모자라 거부돼도 체크한 칸과 입력한 닉네임은 유지", 'name="agree_privacy" value="1" checked' in r.text and 'name="agree_age" value="1">' in r.text and 'value="임시"' in r.text)
r = cn.post("/gate/consent", content=agree_for(cn, "  처음   닉  "), headers=FORM)
check("올바른 닉네임이면 가입 완료(앞뒤·중복 공백은 정리)", r.status_code == 303 and gate.get_user(un["id"])["nickname"] == "처음 닉" and gate.get_user(un["id"])["nick_set"] == 1)
check("이후 위쪽·내 정보에 입력한 닉네임이 표시", "처음 닉 님 · 구글" in cn.get("/who").text and "처음 닉" in cn.get("/gate/account").text)
cd2 = client(make_app()); login(cd2, uid="n-2", nick="x")
r = cd2.post("/gate/consent", content=agree_for(cd2, "처음닉"), headers=FORM)
check("다른 사람이 쓰는 닉네임은 거부(공백 차이도 같은 것으로 봄)", r.status_code == 400 and "이미 사용 중" in r.text)
r = cd2.post("/gate/consent", content=agree_for(cd2, "Nuri2"), headers=FORM)
check("사용 가능한 닉네임이면 가입 완료(대소문자 섞인 'Nuri2')", r.status_code == 303 and gate.get_user(gate._unsign(cd2.cookies.get("gate_sess"))["uid"])["nickname"] == "Nuri2")
ce3 = client(make_app()); login(ce3, uid="n-3", nick="x")
cc = ce3.post("/gate/consent", content=agree_for(ce3, "NURI2"), headers=FORM)
check("대소문자만 다른 닉네임('nuri2' vs 'NURI2')은 중복", cc.status_code == 400 and "이미 사용 중" in cc.text)
check("관리자 본인은 예약어 닉네임도 쓸 수 있음", gate.validate_nickname("관리자", admin=True)[0] is True)
check("자기 자신의 기존 닉네임은 중복으로 보지 않음", gate.validate_nickname("처음 닉", exclude_uid=un["id"]) == (True, "처음 닉"))
gate._db().execute("UPDATE users SET nick_set=0 WHERE id=?", (un["id"],)).connection.commit()
check("닉네임이 비어 있는(예전) 사용자는 동의가 돼 있어도 입장 전에 가입 화면으로", cn.get("/economy").status_code == 302 and "/gate/consent" in cn.get("/economy").headers["location"] and cn.get("/economy/data").status_code == 403)
gate._db().execute("UPDATE users SET nick_set=1 WHERE id=?", (un["id"],)).connection.commit()
print("[닉네임 바꾸기]")
check("내 정보에 닉네임 변경 칸", 'action="/gate/nickname"' in cn.get("/gate/account").text)
r = cn.post("/gate/nickname", content="nickname=" + urllib.parse.quote("새로운닉"), headers=FORM)
check("닉네임 변경 성공", r.status_code == 303 and "m=nick_ok" in r.headers["location"] and gate.get_user(un["id"])["nickname"] == "새로운닉" and "닉네임을 바꿨어요" in cn.get(r.headers["location"]).text)
r = cn.post("/gate/nickname", content="nickname=" + urllib.parse.quote("nuri2"), headers=FORM)
check("남이 쓰는 닉네임으로는 변경 불가", "m=dup" in r.headers["location"] and gate.get_user(un["id"])["nickname"] == "새로운닉" and "이미 사용 중" in cn.get(r.headers["location"]).text)
r = cn.post("/gate/nickname", content="nickname=a%40b.com", headers=FORM)
check("이메일 모양으로는 변경 불가", "m=chars" in r.headers["location"] and gate.get_user(un["id"])["nickname"] == "새로운닉")
check("로그인 안 한 사람의 닉네임 변경은 로그인 화면으로", client(make_app()).post("/gate/nickname", content="nickname=abc", headers=FORM).status_code == 302)
check("다른 사이트발 닉네임 변경 요청은 거부", cn.post("/gate/nickname", content="nickname=" + urllib.parse.quote("해킹닉"), headers=dict(FORM, **{"sec-fetch-site": "cross-site"})).status_code == 403 and gate.get_user(un["id"])["nickname"] == "새로운닉")
check("잘못된 m 값은 화면에 반사되지 않음", "<script>" not in cn.get("/gate/account?m=<script>").text)
print("[구글·카카오에서 이름을 받지 않음]")
_pf, _gj = gate._post_form, gate._get_json
gate.identity_from_code = _orig_identity
gate._post_form = lambda url, data, timeout=15: {"access_token": "tok"}
gate._get_json = lambda url, token, timeout=15: ({"sub": "g-sub-1", "name": "홍길동", "given_name": "길동", "email": "real@mail.com", "picture": "http://x"} if "google" in url else
                                               {"id": 987654, "kakao_account": {"profile": {"nickname": "실명입니다"}, "email": "real@kakao.com"}})
try:
    gid, kid = gate.identity_from_code("google", "c"), gate.identity_from_code("kakao", "c")
finally:
    gate._post_form, gate._get_json = _pf, _gj
check("구글 응답에 이름·이메일이 들어 있어도 고유번호만 사용", gid == "g-sub-1" and isinstance(gid, str))
check("카카오 응답에 닉네임·이메일이 들어 있어도 회원번호만 사용", kid == "987654")
u_real = gate.upsert_login("google", "g-sub-1")
check("가입 처리에 이름을 쓰지 않음(닉네임 비어 있음)", u_real["nickname"] is None and u_real["nick_set"] == 0)

print("[이용 기한: 승인할 때 정하고, 지나면 막힘]")
import datetime as _dt  # noqa: E402
adm2, adm2_id = mk_user("google", "adm-2", "대표둘")
gate.cli(["admin", str(adm2_id)])
tok2 = token_of(adm2)
plus = gate._add_days
yday = (gate.datetime.now(gate.KST) - gate.timedelta(days=1)).strftime("%Y-%m-%d")
check("기한 입력 해석: 무기한 / 일수 / 날짜", gate.parse_term("none") == (True, None) and gate.parse_term("30") == (True, plus(30))
      and gate.parse_term("custom", plus(5)) == (True, plus(5)) and gate.parse_term(plus(9)) == (True, plus(9)))
check("기한 입력 거부: 지난 날짜·엉뚱한 글자·음수·너무 큰 수·없는 날짜·10년 넘는 날짜·빈 날짜",
      all(gate.parse_term(*a) == (False, None) for a in (("custom", yday), ("abc",), ("-5",), ("99999",), ("custom", "2026-13-45"), ("custom", ""), ("2099-01-01",), ("0",))))
os.environ["GATE_APPROVAL"] = "manual"
px, pid = mk_user("kakao", "term-1", "기한테스트")
check("승인제에서 새 가입자는 승인 대기, 기한 없음", gate.get_user(pid)["status"] == "pending" and gate.get_user(pid)["expires_at"] is None)
page = adm2.get("/gate/admin?f=pending").text
check("승인 대기 줄에 '기한을 고르는 칸 + 승인 버튼'이 있음", 'name="term"' in page and 'value="30"' in page and 'value="custom"' in page and 'name="until"' in page)
r = act(adm2, pid, "approve", tok2, "&term=30")
check("30일로 승인: 기한이 오늘+30일로 저장", r.status_code == 303 and gate.get_user(pid)["status"] == "approved" and gate.get_user(pid)["expires_at"] == plus(30))
check("승인 안내 문구에 기한이 날짜로 표시", plus(30) in adm2.get(r.headers["location"]).text)
check("기한 안에서는 정상 이용, 위쪽에 D-표시는 아직 없음(30일 남음)", px.get("/economy/data").status_code == 200 and "D-" not in px.get("/who").text)
check("내 정보에 이용 기한 표시", plus(30) in px.get("/gate/account").text)
gate.set_access(pid, "approved", plus(3))
check("3일 남으면 위쪽에 '기한 D-3' 표시", "기한 D-3" in px.get("/who").text)
gate.set_access(pid, "approved", plus(0))
check("오늘이 마지막 날이면 '오늘까지' 표시하고 오늘은 아직 이용 가능", "오늘까지" in px.get("/who").text and px.get("/economy/data").status_code == 200)
old_cookie = gate._sign({"uid": pid, "iat": int(_dt.datetime.now().timestamp()) - 10 * 86400}, 86400 * 355)
gate.set_access(pid, "approved", yday)
r = px.get("/economy/data")
check("기한이 지나면 데이터 주소는 403(expired)", r.status_code == 403 and r.json().get("reason") == "expired")
r = px.get("/economy")
check("기한이 지나면 화면은 '이용 기간이 끝났어요' 안내(403)", r.status_code == 403 and "이용 기간이 끝났어요" in r.text and yday in r.text)
check("로그인 화면으로 와도 같은 안내(무한 돌림 방지)", "이용 기간이 끝났어요" in px.get("/gate/login").text)
cx = client(app_adm); cx.cookies.set("gate_sess", old_cookie)
check("기한이 지난 사람의 로그인 쿠키는 연장되지 않음", "set-cookie" not in cx.get("/economy/data").headers)
ap = adm2.get("/gate/admin").text
check("관리 화면: '기한 만료' 탭에 1명, 줄에 '만료됨' 표시", "기한 만료 1" in ap and "만료됨 (%s)" % yday in ap)
check("만료 탭에는 만료된 사람이 나오고 '이용 가능' 탭에는 안 나옴", "기한테스트" in adm2.get("/gate/admin?f=expired").text and "기한테스트" not in adm2.get("/gate/admin?f=approved").text)
check("만료된 줄에는 '기한 변경' 칸이 있음", 'value="term"' in adm2.get("/gate/admin?f=expired").text)
r = act(adm2, pid, "term", tok2, "&term=")
check("'기한 선택…' 그대로 누르면 거부하고 기한은 그대로(실수로 무기한 방지)", "m=badterm" in r.headers["location"] and gate.get_user(pid)["expires_at"] == yday)
r = act(adm2, pid, "term", tok2, "&term=custom&until=" + yday)
check("지난 날짜로는 기한을 못 바꿈", "m=baddate" in r.headers["location"] and gate.get_user(pid)["expires_at"] == yday)
r = act(adm2, pid, "term", tok2, "&term=custom&until=" + plus(10))
check("날짜 지정으로 기한을 늘리면 바로 다시 이용 가능", "m=term" in r.headers["location"] and gate.get_user(pid)["expires_at"] == plus(10) and px.get("/economy/data").status_code == 200)
r = act(adm2, pid, "term", tok2, "&term=none")
check("무기한으로 바꾸기", gate.get_user(pid)["expires_at"] is None and "무기한" in adm2.get(r.headers["location"]).text)
gate.cli(["block", str(pid)])
r = act(adm2, pid, "term", tok2, "&term=7")
check("차단된 사람의 기한은 바꿀 수 없음(먼저 차단 해제)", "m=badstate" in r.headers["location"] and gate.get_user(pid)["expires_at"] is None)
r = act(adm2, pid, "unblock", tok2, "&term=90")
check("차단 해제할 때도 기한을 정할 수 있음", gate.get_user(pid)["status"] == "approved" and gate.get_user(pid)["expires_at"] == plus(90))
r = act(adm2, pid, "approve", tok2, "&term=abc")
check("이상한 기한 값은 거부", "m=baddate" in r.headers["location"] and gate.get_user(pid)["expires_at"] == plus(90))
check("안내 문구로 되돌려 보여 주는 날짜는 날짜 모양일 때만(글자 반사 방지)", "<script>" not in adm2.get("/gate/admin?m=approve&d=<script>alert(1)</script>").text)
gate._db().execute("UPDATE users SET expires_at=? WHERE id=?", (yday, adm2_id)).connection.commit()
gate.cli(["admin", str(adm2_id)])
check("관리자는 기한이 없고 기한으로 잠기지 않음", gate.get_user(adm2_id)["expires_at"] is None and adm2.get("/gate/admin").status_code == 200)
check("서버 명령: approve 번호 일수", gate.cli(["approve", str(pid), "45"]) == 0 and gate.get_user(pid)["expires_at"] == plus(45))
check("서버 명령: approve 번호 날짜", gate.cli(["approve", str(pid), plus(20)]) == 0 and gate.get_user(pid)["expires_at"] == plus(20))
check("서버 명령: 잘못된 기한은 거부하고 그대로", gate.cli(["approve", str(pid), "2000-01-01"]) == 2 and gate.get_user(pid)["expires_at"] == plus(20))
check("서버 명령: approve 번호 none = 무기한", gate.cli(["approve", str(pid), "none"]) == 0 and gate.get_user(pid)["expires_at"] is None)
os.environ["GATE_APPROVAL"] = "auto"; os.environ["GATE_AUTO_DAYS"] = "14"
_, aid = mk_user("google", "auto-1", "체험사용자")
check("자동 승인 + 체험 기간 설정(GATE_AUTO_DAYS=14)이면 새 가입자는 14일 뒤까지", gate.get_user(aid)["status"] == "approved" and gate.get_user(aid)["expires_at"] == plus(14))
os.environ["GATE_AUTO_DAYS"] = "0"
_, bid = mk_user("google", "auto-2", "무기한사용자")
check("체험 기간을 안 쓰면(기본) 무기한", gate.get_user(bid)["expires_at"] is None)
check("처리방침에 '이용 기한'이 운영자가 부여하는 정보로 명시", "이용 기한" in client(app_adm).get("/privacy").text and "운영자가 부여하는 정보" in client(app_adm).get("/privacy").text)
check("처리방침 버전이 올라가 예전 동의자는 다시 동의해야 함", gate.POLICY_VERSION == "2026-10-30.1")

print("[예전 DB 이어 쓰기(서버에 이미 있는 가입자 보호)]")
import sqlite3 as _sq  # noqa: E402
_keep = os.environ["GATE_DIR"]
_old = tempfile.mkdtemp(prefix="gateold_")
_con = _sq.connect(os.path.join(_old, "gate.sqlite"))
_con.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, provider_uid TEXT NOT NULL, nickname TEXT,
  status TEXT NOT NULL DEFAULT 'pending', consent_version TEXT, consent_at TEXT, created_at TEXT NOT NULL, last_login_at TEXT, UNIQUE(provider, provider_uid));
  INSERT INTO users(provider,provider_uid,nickname,status,consent_version,created_at) VALUES('google','old-7','예전가입자','approved','2026-10-23.2','2026-10-23T10:00:00');""")
_con.commit(); _con.close()
os.environ["GATE_DIR"] = _old
try:
    row = gate._db().execute("SELECT * FROM users WHERE provider_uid='old-7'").fetchone()
    check("예전 DB 에 새 열이 자동으로 추가되고 가입 상태는 그대로(기한 없음=무기한)",
          row["status"] == "approved" and row["is_admin"] == 0 and row["expires_at"] is None and not gate.is_expired(row) and row["nick_set"] == 0)
    check("예전에 저장된 구글·카카오 이름(실명일 수 있음)은 지워짐 — 닉네임을 새로 정할 때까지 비어 있음", row["nickname"] is None and row["nick_key"] is None)
    check("두 번 열어도 오류 없음", gate._db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1)
finally:
    os.environ["GATE_DIR"] = _keep

print("[로그인 서버가 거절했을 때: 이유가 서버 기록에 남음]")
import contextlib  # noqa: E402
import io as _io  # noqa: E402
import urllib.error as _ue  # noqa: E402
import urllib.request as _ur  # noqa: E402
_real_urlopen = _ur.urlopen


def _boom(req, timeout=15):
    raise _ue.HTTPError(req.full_url, 401, "Unauthorized", {}, _io.BytesIO(b'{"error":"invalid_client","error_description":"Bad client credentials","error_code":"KOE010"}'))


gate.identity_from_code = _orig_identity
_ur.urlopen = _boom
try:
    cz = client(make_app())
    st = urllib.parse.parse_qs(urllib.parse.urlparse(cz.get("/gate/kakao/start").headers["location"]).query)["state"][0]
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = cz.get("/gate/kakao/callback?code=SECRETCODE&state=" + st)
    logged = buf.getvalue()
finally:
    _ur.urlopen = _real_urlopen
check("카카오가 거절하면 사용자에게는 안내 화면(502)", r.status_code == 502 and "연결하지 못했어요" in r.text)
check("서버 기록에 거절 이유(KOE010)와 어느 단계인지가 남음", "KOE010" in logged and "kauth.kakao.com/oauth/token" in logged and "HTTP 401" in logged)
check("기록에 키·시크릿·인가 코드는 남지 않음", all(x not in logged for x in ("kkey", "gsec", "SECRETCODE")))
check("화면에는 내부 오류 내용이 새지 않음", "KOE010" not in r.text and "kauth" not in r.text)

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
check("탈퇴 뒤 옛 쿠키로는 못 들어감", c.get("/economy").status_code == 302)

print("[다른 사이트에서 온 요청]")
c = client(make_app()); login(c); c.post("/gate/consent", content=agree_for(c), headers=FORM)
check("다른 사이트발 POST 거부(CSRF)", c.post("/api/dig/refresh", headers={"sec-fetch-site": "cross-site"}).status_code == 403
      and c.post("/gate/delete", content="confirm=1", headers=dict(FORM, **{"sec-fetch-site": "cross-site"})).status_code == 403)
check("같은 사이트 POST 는 정상", c.post("/api/dig/refresh", headers={"sec-fetch-site": "same-origin"}).status_code == 200)
r = login(client(make_app()), nxt="https://evil.com")
check("로그인 뒤 외부 주소로 안 튕김", "evil" not in r.headers["location"])

print("[이름에 악성 글자]")
c = client(make_app()); login(c, uid="x-9", nick="스크립트"); c.post("/gate/consent", content=agree_for(c), headers=FORM)
gate._db().execute("UPDATE users SET nickname=? WHERE provider_uid='x-9'", ("<script>alert(1)</script>",)).connection.commit()
acc = c.get("/gate/account").text
check("(혹시 저장된 값이 이상해도) 내 정보에서 HTML 이 글자로만 표시(XSS 방지)", "<script>alert(1)</script>" not in acc and "&lt;script&gt;" in acc)

print("[승인 방식 manual (나중 단계)]")
os.environ["GATE_APPROVAL"] = "manual"
app = make_app(); c = client(app)
r = login(c, uid="new-1", nick="새사람"); c.post("/gate/consent", content=agree_for(c), headers=FORM)
check("가입은 되지만 '승인 대기'", gate.get_user(gate._unsign(c.cookies.get("gate_sess"))["uid"])["status"] == "pending")
check("승인 전: 화면은 대기 페이지로, 데이터는 403", c.get("/economy").headers["location"] == "/gate/pending" and c.get("/economy/data").status_code == 403)
check("대기 페이지 표시", "승인을 기다리고" in c.get("/gate/pending").text)
uid = gate._unsign(c.cookies.get("gate_sess"))["uid"]
check("운영 명령 approve 로 승인", gate.cli(["approve", str(uid)]) == 0)
check("승인 뒤 바로 입장", c.get("/economy").status_code == 200)
gate.cli(["block", str(uid)])
check("차단하면 403", c.get("/economy").status_code == 403 and c.get("/economy/data").status_code == 403)
gate.cli(["approve", str(uid)])
os.environ["GATE_APPROVAL"] = "auto"

print("[auto 로 가입한 사람은 manual 로 바꿔도 유지]")
os.environ["GATE_APPROVAL"] = "auto"
c = client(make_app()); login(c, uid="old-1", nick="먼저온사람"); c.post("/gate/consent", content=agree_for(c), headers=FORM)
os.environ["GATE_APPROVAL"] = "manual"
c2 = client(make_app()); r = login(c2, uid="old-1", nick="먼저온사람")
check("이미 승인된 사람은 manual 전환 뒤 다시 로그인해도 바로 입장", r.headers["location"] == "/economy" and c2.get("/economy").status_code == 200)
c3 = client(make_app()); login(c3, uid="late-1", nick="나중사람"); c3.post("/gate/consent", content=agree_for(c3), headers=FORM)
check("전환 뒤 가입한 사람은 승인 대기", c3.get("/economy").headers["location"] == "/gate/pending")
os.environ["GATE_APPROVAL"] = "auto"

print("[로그인 유지: 한 번 로그인·승인되면 계속]")
import time as _t  # noqa: E402
c = client(make_app()); r = login(c, uid="keep-1", nick="오래쓰는사람")
check("로그인 쿠키 유효기간이 1년(365일)", "Max-Age=31536000" in r.headers["set-cookie"])
c.post("/gate/consent", content=agree_for(c), headers=FORM)
uid = gate._unsign(c.cookies.get("gate_sess"))["uid"]
check("방금 발급된 쿠키는 매 요청마다 갈아 끼우지 않음", "set-cookie" not in c.get("/economy/data").headers)
old_tok = gate._sign({"uid": uid, "iat": int(_t.time()) - 10 * 86400}, 86400 * 355)      # 10일 전에 발급, 아직 355일 남음
c2 = client(make_app()); c2.cookies.set("gate_sess", old_tok)
r = c2.get("/economy/data")
check("10일 지난 쿠키로 쓰면 기간이 1년으로 자동 연장", r.status_code == 200 and "Max-Age=31536000" in r.headers.get("set-cookie", ""))
check("연장된 쿠키도 같은 사용자", gate._unsign(r.cookies.get("gate_sess"))["uid"] == uid)
legacy = gate._sign({"uid": uid}, 86400)                                                   # 예전 방식(iat 없음) 쿠키도 이어서 사용 + 연장
c3 = client(make_app()); c3.cookies.set("gate_sess", legacy)
r = c3.get("/economy/data")
check("예전 쿠키(발급시각 없음)도 정상 사용되고 1년짜리 새 쿠키로 교체", r.status_code == 200 and "gate_sess=" in r.headers.get("set-cookie", "") and "Max-Age=31536000" in r.headers["set-cookie"])
check("1년 안 쓰고 만료되면 로그인 필요", client(make_app()).get("/economy/data", headers={"cookie": "gate_sess=" + gate._sign({"uid": uid}, -5)}).status_code == 401)
gate.cli(["block", str(uid)])
c4 = client(make_app()); c4.cookies.set("gate_sess", old_tok)
r = c4.get("/economy/data")
check("차단된 사용자는 연장도 입장도 안 됨", r.status_code == 403 and "set-cookie" not in r.headers)
gate.cli(["approve", str(uid)])
c5 = client(make_app()); c5.cookies.set("gate_sess", old_tok)
r = c5.get("/gate/logout")
check("로그아웃 응답은 쿠키를 지움(연장하지 않음)", "Max-Age=0" in r.headers.get("set-cookie", "") and "Max-Age=31536000" not in r.headers.get("set-cookie", ""))
gate.delete_user(uid)
c6 = client(make_app()); c6.cookies.set("gate_sess", old_tok)
r = c6.get("/economy/data")
check("탈퇴한 사용자의 옛 쿠키는 연장 없이 거부", r.status_code == 401 and "set-cookie" not in r.headers)

print("[처리방침 문구가 바뀐 경우]")
c = client(make_app()); login(c, uid="v-1", nick="버전닉"); c.post("/gate/consent", content=agree_for(c), headers=FORM)
check("동의 후 입장", c.get("/economy").status_code == 200)
old = gate.POLICY_VERSION; gate.POLICY_VERSION = "2099-01-01"
check("버전이 바뀌면 다시 동의해야 함", c.get("/economy").status_code == 302 and "consent" in c.get("/economy").headers["location"])
gate.POLICY_VERSION = old

print("[계정별 화면 모드 저장]")
app_t = make_app()
ct = client(app_t); login(ct, uid="t-1", nick="테마닉"); ct.post("/gate/consent", content=agree_for(ct), headers=FORM)
tj = {"content-type": "application/json"}
check("처음엔 저장된 모드가 없어 머리글이 비어 있음(브라우저 기억/기기 설정을 따름)", ct.get("/themehead").text == "")
r = ct.post("/gate/theme", content='{"theme":"dark"}', headers=tj)
check("다크 저장", r.status_code == 200 and r.json() == {"ok": True, "theme": "dark"})
th = ct.get("/themehead").text
check("저장한 모드가 머리글 스크립트로 먼저 적용됨", 'window.__GATE_THEME="dark"' in th and 'setAttribute("data-theme"' in th)
check("다른 기기(새 브라우저)에서 같은 계정으로 로그인해도 같은 모드", (lambda c2: (login(c2, uid="t-1", nick="테마닉"), 'window.__GATE_THEME="dark"' in c2.get("/themehead").text)[1])(client(app_t)))
other = client(app_t); login(other, uid="t-2", nick="다른닉"); other.post("/gate/consent", content=agree_for(other), headers=FORM)
check("다른 계정에는 영향 없음", other.get("/themehead").text == "")
check("자동(기기 설정)·화이트도 저장", ct.post("/gate/theme", content='{"theme":"auto"}', headers=tj).status_code == 200 and '__GATE_THEME="auto"' in ct.get("/themehead").text
      and ct.post("/gate/theme", content='{"theme":"light"}', headers=tj).status_code == 200 and '__GATE_THEME="light"' in ct.get("/themehead").text)
for bad in ('{"theme":"<script>"}', '{"theme":1}', '[]', 'not json', ''):
    check("엉뚱한 값은 거부하고 기존 값 유지: %r" % bad, ct.post("/gate/theme", content=bad, headers=tj).status_code == 400 and '__GATE_THEME="light"' in ct.get("/themehead").text)
check("로그인 안 한 사람은 저장 불가(401)", client(app_t).post("/gate/theme", content='{"theme":"dark"}', headers=tj).status_code == 401)
check("다른 사이트에서 보낸 요청은 거부", ct.post("/gate/theme", content='{"theme":"dark"}', headers={**tj, "sec-fetch-site": "cross-site"}).status_code == 403)
check("내 정보 화면에 화면 모드 표시", "화이트" in ct.get("/gate/account").text)
with gate._db() as con:
    con.execute("UPDATE users SET theme='<img src=x onerror=1>' WHERE nickname='테마닉'")
check("DB 에 이상한 값이 있어도 머리글에 나오지 않음(허용 목록만)", ct.get("/themehead").text == "")
check("처리방침에 화면 모드 저장 명시", "화면 모드" in ct.get("/privacy").text)

print("[서버 IP 접속: 관리자 비밀번호]")
IPPW = "Correct-Horse-9-Staple"
def ipclient(app, base="http://203.0.113.5:8000"):
    return TestClient(app, base_url=base, follow_redirects=False)
app_ip = make_app()
os.environ.pop("GATE_IP_ADMIN_PASSWORD", None)
ci = ipclient(app_ip)
r = ci.get("/economy")
check("비밀번호를 안 정하면 IP 접속은 통째로 막힘(403)", r.status_code == 403 and "IP" in r.text)
check("그때 데이터 주소도 403(JSON)", ci.get("/economy/data").status_code == 403 and ci.get("/api/dig/item").status_code == 403)
os.environ["GATE_IP_ADMIN_PASSWORD"] = "short-pw"
check("12자 미만 비밀번호는 쓰지 않음(여전히 막힘)", ipclient(app_ip).get("/economy").status_code == 403)
os.environ["GATE_IP_ADMIN_PASSWORD"] = IPPW
ci = ipclient(app_ip)
r = ci.get("/economy")
check("IP 로 /economy → 관리자 로그인 화면으로", r.status_code == 302 and r.headers["location"].startswith("/gate/ip-login"))
check("IP 로 데이터 주소 → 401", ci.get("/economy/data").status_code == 401 and ci.get("/api/news/today").status_code == 401 and ci.get("/dig").status_code == 302)
page = ci.get("/gate/ip-login")
check("로그인 화면: 비밀번호 칸 + http 경고", page.status_code == 200 and 'type="password"' in page.text and "암호화되지 않았어요" in page.text)
check("https 로 열면 경고 없음", "암호화되지 않았어요" not in ipclient(app_ip, "https://203.0.113.5").get("/gate/ip-login").text)
check("도메인에서는 IP 로그인 화면이 없는 것처럼(404)", client(app_ip).get("/gate/ip-login").status_code == 404)
check("IP 접속에서 구글/카카오 로그인 주소는 IP 로그인으로 보냄", ci.get("/gate/login").headers["location"] == "/gate/ip-login"
      and ci.get("/gate/google/start").headers["location"] == "/gate/ip-login" and ci.get("/gate/account").headers["location"] == "/gate/ip-login")
check("IP 접속에서 쓰기 요청(/gate/theme 등)은 403", ci.post("/gate/theme", content='{"theme":"dark"}', headers=tj).status_code == 403)
FORMD = {"content-type": "application/x-www-form-urlencoded"}
r = ci.post("/gate/ip-login", content="password=wrong-password-123&next=%2Feconomy", headers=FORMD)
check("틀린 비밀번호는 거부(쿠키 없음)", r.status_code == 303 and "m=bad" in r.headers["location"] and "gate_ipadm" not in r.headers.get("set-cookie", ""))
check("아직 입장 못 함", ci.get("/economy").status_code == 302)
r = ci.post("/gate/ip-login", content="password=" + IPPW + "&next=%2Feconomy", headers=FORMD)
ck = r.headers.get("set-cookie", "")
check("맞는 비밀번호 → 입장(303) + 12시간 쿠키(HttpOnly·Strict)", r.status_code == 303 and r.headers["location"] == "/economy"
      and "gate_ipadm=" in ck and "HttpOnly" in ck and "SameSite=strict" in ck.replace("samesite", "SameSite") and "Max-Age=43200" in ck)
check("http 이므로 Secure 표시는 없음(있으면 http 에서 쿠키가 안 붙음)", "secure" not in ck.lower())
check("입장 후 페이지·데이터 주소 모두 열림", ci.get("/economy").status_code == 200 and ci.get("/economy/data").status_code == 200
      and ci.get("/dig").status_code == 200 and ci.get("/api/dig/item").status_code == 200)
check("쿠키 값에 비밀번호가 들어 있지 않음", IPPW not in ck and IPPW not in str(ci.cookies))
check("위쪽 표시: IP 관리자 모드 + 관리 + 로그아웃", all(x in ci.get("/who").text for x in ("IP 관리자 모드", "/gate/admin", "/gate/ip-logout")))
# 쿠키를 도메인 접속으로 가져가도 소용없음
cd = client(app_ip); cd.cookies.set("gate_ipadm", ci.cookies.get("gate_ipadm"))
check("IP 쿠키를 도메인 접속에 붙여도 통과 못 함", cd.get("/economy").status_code == 302 and "/gate/login" in cd.get("/economy").headers["location"])
check("도메인에서 보낸 가짜 Host: 숫자 IP 로 바꿔도 비밀번호 없이는 못 들어감", ipclient(app_ip).get("/economy").status_code == 302)
check("옛 /slack 주소도 IP 접속에서 똑같이 잠김", ipclient(app_ip).get("/slack").status_code == 302 and ipclient(app_ip).get("/slack/data").status_code == 401)
r = ci.get("/gate/admin")
check("IP 관리자 모드에서 가입자 관리 화면 열림", r.status_code == 200 and "가입자" in r.text)
check("도메인에서 같은 쿠키로는 관리 화면이 없는 것처럼(404)", cd.get("/gate/admin").status_code == 404)
check("비밀번호 없는 IP 접속자에겐 관리 화면이 없는 것처럼(404)", ipclient(app_ip).get("/gate/admin").status_code == 404)
tk = _re.search(r'name="csrf" value="([0-9a-f]+)"', r.text)
victim_c, victim = mk_user("google", "ip-victim", "대상자")
if tk:
    r2 = ci.post("/gate/admin/act", content="uid=%d&action=block&csrf=%s" % (victim, tk.group(1)), headers=FORMD)
    check("IP 관리자 모드로 차단 처리 가능", r2.status_code == 303 and gate.get_user(victim)["status"] == "blocked")
    r2 = ci.post("/gate/admin/act", content="uid=%d&action=approve&csrf=%s" % (victim, "0" * 32), headers=FORMD)
    check("확인표가 틀리면 처리 안 됨", r2.status_code == 400 and gate.get_user(victim)["status"] == "blocked")
else:
    check("관리 화면에 확인표가 있음", False)
r = ci.get("/gate/ip-logout")
check("로그아웃하면 다시 잠김", r.status_code == 302 and ci.get("/economy").status_code == 302)
# 비밀번호를 바꾸면 기존 로그인은 모두 무효
cj = ipclient(app_ip); cj.post("/gate/ip-login", content="password=" + IPPW + "&next=%2Feconomy", headers=FORMD)
check("(준비) 다시 입장", cj.get("/economy").status_code == 200)
os.environ["GATE_IP_ADMIN_PASSWORD"] = IPPW + "-new"
check("비밀번호를 바꾸면 예전 로그인 쿠키는 즉시 무효", cj.get("/economy").status_code == 302)
os.environ["GATE_IP_ADMIN_PASSWORD"] = IPPW
# 연속 실패 잠금
ck5 = ipclient(app_ip); gate._ip_fail.clear()
for i in range(5):
    ck5.post("/gate/ip-login", content="password=nope-nope-nope-%d" % i, headers=FORMD)
r = ck5.post("/gate/ip-login", content="password=" + IPPW, headers=FORMD)
check("5번 틀리면 잠겨서, 맞는 비밀번호도 잠시 거부", "m=locked" in r.headers["location"] and "gate_ipadm" not in r.headers.get("set-cookie", ""))
gate._ip_fail.clear()
check("잠금이 풀리면 다시 입장 가능", "gate_ipadm" in ck5.post("/gate/ip-login", content="password=" + IPPW, headers=FORMD).headers.get("set-cookie", ""))
check("다른 사이트에서 날아온 로그인 시도는 거부", ipclient(app_ip).post("/gate/ip-login", content="password=" + IPPW, headers={**FORMD, "sec-fetch-site": "cross-site"}).status_code == 403)
check("로그인 뒤 이동 주소는 우리 화면만(열린 리디렉션 차단)", ipclient(app_ip).post("/gate/ip-login", content="password=" + IPPW + "&next=https%3A%2F%2Fevil.com", headers=FORMD).headers["location"] == "/economy")
check("서버 내부 열쇠(PDF 만들기)는 그대로 통과", ipclient(app_ip, "http://127.0.0.1:8000").get("/dig", headers={"x-gate-internal": gate.internal_key()}).status_code == 200)
check("IPv6 주소 호스트도 IP 로 판정", ipclient(app_ip, "http://[::1]:8000").get("/economy").status_code == 302 and gate.is_ip_host(type("R", (), {"headers": {"host": "[2001:db8::1]:8000"}})()))
check("도메인 호스트는 IP 로 오인하지 않음", not gate.is_ip_host(type("R", (), {"headers": {"host": "mystatus-btr.duckdns.org"}})()) and not gate.is_ip_host(type("R", (), {"headers": {"host": ""}})()))
os.environ.pop("GATE_IP_ADMIN_PASSWORD", None)

print("[서버 내부 열쇠 (PDF 만들기용)]")
c = client(make_app())
key = gate.internal_key()
check("내부 열쇠가 있으면 로그인 없이 통과", c.get("/dig", headers={"x-gate-internal": key}).status_code == 200)
check("틀린 열쇠는 거부", c.get("/dig", headers={"x-gate-internal": "x" * 40}).status_code == 302)
check("열쇠 파일은 본인만 읽기(600)", oct(os.stat(os.path.join(gate.gate_dir(), "internal.key")).st_mode)[-3:] == "600")
check("로컬 접속이라는 이유로는 통과시키지 않음(nginx 뒤 우회 방지)", c.get("/economy", headers={"x-forwarded-for": "127.0.0.1"}).status_code == 302)

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
