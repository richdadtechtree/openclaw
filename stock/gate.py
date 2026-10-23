"""로그인(구글·카카오) + 개인정보 동의 + 승인 게이트 (2026-10-23 사용자 요청).

잠그는 곳: /slack(신문 요약) · /dig(경제 공부) 와 그 화면이 쓰는 /api/news/* · /api/dig/* · /slack/* 주소.
          (주가 대시보드 '/' 와 나머지는 그대로 둔다)

흐름
  처음 방문 → /gate/login (구글·카카오) → 소셜 로그인 → /gate/consent (개인정보 동의 3칸) → 입장
  승인 방식  GATE_APPROVAL=auto   : 로그인 + 동의만 하면 바로 입장 (지금)
             GATE_APPROVAL=manual : 가입하면 '승인 대기' → 운영자가 `python3 gate.py approve <번호>` 해야 입장 (나중에)

개인정보 최소 수집: 소셜 로그인 고유번호 + 닉네임/이름만 저장한다(이메일은 아예 요청하지 않음).
저장 위치: ~/.openclaw/secret/gate/  (secret/ 은 git 이 절대 올리지 않는 폴더 — 서명 열쇠·사용자 DB 보호)

안전장치
  * 설정이 덜 됐으면(주소·키 없음) 잠금이 꺼진 채 '열려' 있다 → git 자동 반영 직후 갑자기 못 들어가는 사고 방지(경고만 출력).
  * 표준 라이브러리만 사용(새 설치 없음). 쿠키는 직접 HMAC 서명(변조·만료 검사).
  * 쿠키 HttpOnly + SameSite=Lax + (https 일 때) Secure, 다른 사이트에서 온 POST 는 거부, 로그인 후 이동 주소는 안전한 것만.
  * 서버 내부 작업(PDF 만들기)은 내부 열쇠 헤더로만 통과 — nginx 뒤에선 모든 요청이 127.0.0.1 로 보이므로 '로컬이면 통과' 는 쓰지 않는다.

운영 명령: python3 gate.py check | list | pending | approve N | block N | unblock N | delete N | stats
"""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 처리방침·동의 문구를 고치면 이 날짜를 바꾼다 → 모든 사용자가 새 문구에 다시 동의해야 입장한다.
POLICY_VERSION = "2026-10-23.2"      # 동의 기록에 남는 버전(문구를 고칠 때마다 올린다)
POLICY_EFFECTIVE = "2026-10-23"        # 처리방침에 보이는 시행일

COOKIE_SESSION = "gate_sess"          # ⚠️ PT 대시보드(Flask)의 'session' 쿠키와 같은 도메인에서 겹치지 않게 이름을 다르게
COOKIE_STATE = "gate_state"
SESSION_DAYS = 365                    # 로그인 유지 기간(마지막으로 쓴 뒤 1년). 한 번 로그인·승인되면 계속 쓰는 한 다시 로그인할 일이 없다
RENEW_AFTER_DAYS = 7                  # 쓸 때마다가 아니라 7일에 한 번만 기간을 새로 늘린다(불필요한 쿠키 재발급 방지)
STATE_MINUTES = 10

_env_loaded = False


def _load_env():
    """~/.openclaw/.env 의 KEY=VALUE 를 환경변수로(이미 있는 값은 덮지 않음). python-dotenv 없이 직접 읽는다."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    path = os.path.expanduser(os.getenv("OPENCLAW_ENV", "~/.openclaw/.env"))
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.replace("export ", "").strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def _env(name, default=""):
    _load_env()
    return (os.getenv(name, default) or "").strip()


def gate_dir():
    d = os.path.expanduser(os.getenv("GATE_DIR", "~/.openclaw/secret/gate"))
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def cfg():
    """지금 설정 상태. 호출할 때마다 읽는다(.env 를 고치고 재시작하면 바로 반영)."""
    base = _env("GATE_BASE_URL").rstrip("/")
    google = bool(_env("GATE_GOOGLE_CLIENT_ID") and _env("GATE_GOOGLE_CLIENT_SECRET"))
    kakao = bool(_env("GATE_KAKAO_REST_KEY"))
    return {
        "base": base,
        "https": base.startswith("https://"),
        "google": google,
        "kakao": kakao,
        "approval": "manual" if _env("GATE_APPROVAL", "auto").lower() == "manual" else "auto",
        "enabled": _env("GATE_ENABLED", "1") != "0" and bool(base) and (google or kakao),
        "operator": _env("PRIVACY_OPERATOR"),
        "contact": _env("PRIVACY_CONTACT"),
    }


# ───────────────────────── 서명 쿠키 ─────────────────────────
_secret_cache = None


def _secret():
    """쿠키 서명 열쇠(없으면 한 번 만들어 저장). 이 파일이 바뀌면 모두 로그아웃된다."""
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache
    p = os.path.join(gate_dir(), "secret.key")
    try:
        with open(p, "rb") as f:
            k = f.read().strip()
    except OSError:
        k = b""
    if len(k) < 32:
        k = secrets.token_hex(32).encode()
        with open(p, "wb") as f:
            f.write(k)
        os.chmod(p, 0o600)
    _secret_cache = k
    return k


def internal_key():
    """서버 내부 작업(PDF 만들기 등)이 로그인 없이 통과할 때 쓰는 열쇠. 잠금이 꺼져 있으면 None."""
    if not cfg()["enabled"]:
        return None
    p = os.path.join(gate_dir(), "internal.key")
    try:
        with open(p, encoding="utf-8") as f:
            k = f.read().strip()
    except OSError:
        k = ""
    if len(k) < 32:
        k = secrets.token_urlsafe(40)
        with open(p, "w", encoding="utf-8") as f:
            f.write(k)
        os.chmod(p, 0o600)
    return k


def _sign(payload, max_age):
    body = dict(payload, exp=int(time.time()) + int(max_age))
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + "." + sig


def _unsign(token):
    """서명이 맞고 만료 전이면 payload, 아니면 None."""
    try:
        raw, sig = (token or "").rsplit(".", 1)
        good = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if int(data.get("exp", 0)) < time.time():
            return None
        return data
    except Exception:
        return None


_NEXT_OK = re.compile(r"^/(slack|dig)(/[A-Za-z0-9_\-./]*)?(\?[A-Za-z0-9_\-=&%.]*)?$")


def safe_next(target, default="/slack"):
    """로그인 뒤 돌아갈 곳. 우리 두 화면 주소만 허용(다른 사이트로 보내는 '열린 리디렉션' 차단)."""
    t = (target or "").strip()
    return t if _NEXT_OK.match(t) and "//" not in t and "\\" not in t else default


# ───────────────────────── 사용자 DB ─────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL, provider_uid TEXT NOT NULL, nickname TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  consent_version TEXT, consent_at TEXT,
  created_at TEXT NOT NULL, last_login_at TEXT,
  UNIQUE(provider, provider_uid));
CREATE TABLE IF NOT EXISTS consents(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
  version TEXT NOT NULL, items TEXT NOT NULL, agreed_at TEXT NOT NULL);
"""


def _now():
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S")


def _db():
    path = os.path.join(gate_dir(), "gate.sqlite")
    fresh = not os.path.exists(path)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    if fresh:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return con


def _clean_name(s):
    s = re.sub(r"[\x00-\x1f\x7f]", "", str(s or "")).strip()
    return s[:40] or "이름 없음"


def upsert_login(provider, uid, nickname):
    """소셜 로그인에 성공했을 때: 처음이면 가입(승인 방식에 따라 상태 결정), 아니면 닉네임·최근 로그인만 갱신."""
    with _db() as con:
        row = con.execute("SELECT * FROM users WHERE provider=? AND provider_uid=?", (provider, str(uid))).fetchone()
        if row:
            con.execute("UPDATE users SET nickname=?, last_login_at=? WHERE id=?", (_clean_name(nickname), _now(), row["id"]))
        else:
            status = "approved" if cfg()["approval"] == "auto" else "pending"
            con.execute("INSERT INTO users(provider,provider_uid,nickname,status,created_at,last_login_at) VALUES(?,?,?,?,?,?)",
                        (provider, str(uid), _clean_name(nickname), status, _now(), _now()))
        return con.execute("SELECT * FROM users WHERE provider=? AND provider_uid=?", (provider, str(uid))).fetchone()


def get_user(uid):
    try:
        with _db() as con:
            return con.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()
    except Exception:
        return None


def record_consent(uid, items):
    with _db() as con:
        con.execute("INSERT INTO consents(user_id,version,items,agreed_at) VALUES(?,?,?,?)",
                    (uid, POLICY_VERSION, json.dumps(items, ensure_ascii=False), _now()))
        con.execute("UPDATE users SET consent_version=?, consent_at=? WHERE id=?", (POLICY_VERSION, _now(), uid))


def delete_user(uid):
    """탈퇴: 사용자 정보와 동의 기록을 모두 지운다(보관하지 않음)."""
    with _db() as con:
        con.execute("DELETE FROM consents WHERE user_id=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))


def set_status(uid, status):
    with _db() as con:
        return con.execute("UPDATE users SET status=? WHERE id=?", (status, uid)).rowcount


# ───────────────────────── 소셜 로그인(구글·카카오) ─────────────────────────
def _post_form(url, data, timeout=15):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url, token, timeout=15):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def redirect_uri(provider):
    return "%s/gate/%s/callback" % (cfg()["base"], provider)


def authorize_url(provider, state):
    c = cfg()
    if provider == "google":
        # openid + profile 만: 고유번호(sub)와 이름. ⚠️ email 범위는 일부러 요청하지 않는다(최소 수집).
        q = {"client_id": _env("GATE_GOOGLE_CLIENT_ID"), "redirect_uri": redirect_uri("google"), "response_type": "code",
             "scope": "openid profile", "state": state, "prompt": "select_account"}
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)
    if provider == "kakao":
        q = {"client_id": _env("GATE_KAKAO_REST_KEY"), "redirect_uri": redirect_uri("kakao"), "response_type": "code",
             "scope": "profile_nickname", "state": state}
        return "https://kauth.kakao.com/oauth/authorize?" + urllib.parse.urlencode(q)
    raise ValueError(provider)


def identity_from_code(provider, code):
    """인가 코드 → (고유번호, 닉네임). 네트워크 호출이라 시험에서는 이 함수를 가짜로 바꾼다."""
    if provider == "google":
        tok = _post_form("https://oauth2.googleapis.com/token", {
            "code": code, "client_id": _env("GATE_GOOGLE_CLIENT_ID"), "client_secret": _env("GATE_GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri("google"), "grant_type": "authorization_code"})
        info = _get_json("https://openidconnect.googleapis.com/v1/userinfo", tok["access_token"])
        return info["sub"], info.get("name") or info.get("given_name") or "구글 사용자"
    if provider == "kakao":
        data = {"grant_type": "authorization_code", "client_id": _env("GATE_KAKAO_REST_KEY"),
                "redirect_uri": redirect_uri("kakao"), "code": code}
        if _env("GATE_KAKAO_CLIENT_SECRET"):
            data["client_secret"] = _env("GATE_KAKAO_CLIENT_SECRET")
        tok = _post_form("https://kauth.kakao.com/oauth/token", data)
        info = _get_json("https://kapi.kakao.com/v2/user/me", tok["access_token"])
        prof = (info.get("kakao_account") or {}).get("profile") or {}
        return str(info["id"]), prof.get("nickname") or (info.get("properties") or {}).get("nickname") or "카카오 사용자"
    raise ValueError(provider)


# ───────────────────────── 화면(HTML) ─────────────────────────
_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2230;--sub:#5b6577;--line:#e3e7ee;--blue:#2f7be0;--red:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--card:#1b2029;--ink:#e8ebf1;--sub:#9aa5b8;--line:#2b3340;--blue:#6aa6f5;--red:#ff7b6b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Pretendard,"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;line-height:1.7;word-break:keep-all}
main{max-width:640px;margin:0 auto;padding:28px 16px 80px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px 22px;margin-bottom:16px}
h1{font-size:22px;margin:0 0 6px} h2{font-size:16px;margin:22px 0 6px} p{margin:0 0 12px} .sub{color:var(--sub);font-size:14px}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;padding:13px 16px;margin:10px 0;border-radius:10px;
     font-size:16px;font-weight:700;text-decoration:none;border:1px solid var(--line);cursor:pointer;font-family:inherit}
.google{background:#fff;color:#1f1f1f}.kakao{background:#fee500;color:#191919;border-color:#fee500}
.primary{background:var(--blue);color:#fff;border-color:var(--blue)} .danger{background:transparent;color:var(--red);border-color:var(--red)}
table{width:100%;border-collapse:collapse;font-size:14px;margin:8px 0 14px} th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:rgba(127,127,127,.08);width:30%}
label.chk{display:flex;gap:10px;align-items:flex-start;padding:12px;border:1px solid var(--line);border-radius:10px;margin:8px 0;cursor:pointer}
label.chk input{margin-top:5px;width:18px;height:18px;flex:none}
.warn{color:var(--red);font-weight:700} a{color:var(--blue)} .foot{text-align:center;font-size:13px;color:var(--sub);margin-top:18px}
ul{padding-left:20px;margin:0 0 12px} li{margin:3px 0}
"""


def _page(title, body, status=200):
    from fastapi.responses import HTMLResponse
    doc = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>%s</title><style>%s</style></head><body><main>%s</main></body></html>') % (html.escape(title), _CSS, body)
    return HTMLResponse(doc, status_code=status, headers={"Cache-Control": "no-store"})


def _foot():
    return '<div class="foot"><a href="/privacy">개인정보 처리방침</a></div>'


def _ph(value, hint):
    """운영자가 .env 에 아직 안 적은 값은 눈에 띄는 빨간 안내로 보여 준다(빈칸으로 공개되는 사고 방지)."""
    return html.escape(value) if value else '<span class="warn">[%s]</span>' % html.escape(hint)


def privacy_html():
    c = cfg()
    op = _ph(c["operator"], "운영자 이름을 .env 의 PRIVACY_OPERATOR 에 입력하세요")
    ct = _ph(c["contact"], "연락처(이메일)를 .env 의 PRIVACY_CONTACT 에 입력하세요")
    return """
<div class="card"><h1>개인정보 처리방침</h1>
<p class="sub">시행일 %(eff)s · 버전 %(ver)s</p>
<p>「경제 공부 · 신문 요약」 서비스(이하 '서비스')는 「개인정보 보호법」에 따라 이용자의 개인정보를 보호하고 아래와 같이 처리합니다.</p>

<h2>1. 처리하는 개인정보 항목과 목적</h2>
<table>
<tr><th>항목</th><td>소셜 로그인(구글 또는 카카오)이 알려 주는 <b>고유 식별번호</b>, <b>이름(닉네임)</b>, 가입 시각·최근 접속 시각, 동의 이력</td></tr>
<tr><th>목적</th><td>이용자 확인(본인 계정 식별), 서비스 이용 권한 관리(승인 여부 확인), 부정 이용 방지</td></tr>
<tr><th>자동 생성 정보</th><td>웹서버 <b>접속 기록</b>(접속 IP 주소, 접속 시각, 요청한 주소)이 서비스 이용 중 자동으로 남습니다. 목적은 안정적 운영과 부정 이용 방지입니다.</td></tr>
<tr><th>수집하지 않는 것</th><td>이메일, 전화번호, 주소, 생년월일, 성별, 프로필 사진, 비밀번호는 <b>수집하지 않습니다.</b></td></tr>
</table>

<h2>2. 보유 및 이용 기간</h2>
<p>탈퇴하거나 정보 삭제를 요청할 때까지 보유하며, 탈퇴 시 <b>지체 없이(즉시) 모두 삭제</b>합니다. 서비스를 종료하는 경우에도 지체 없이 파기합니다. 웹서버 접속 기록은 약 %(logdays)s일 보관한 뒤 자동으로 삭제됩니다(탈퇴해도 이 기간 동안은 서버 기록에 남을 수 있습니다).</p>

<h2>3. 제3자 제공 및 처리 위탁</h2>
<p>이용자의 개인정보를 제3자에게 제공하거나 처리를 위탁하지 않습니다. 로그인 과정에서 구글 또는 카카오가 각 사의 정책에 따라 로그인 정보를 처리하며, 이는 서비스가 아닌 각 사의 처리입니다. 정보는 운영자가 관리하는 클라우드 서버에 저장됩니다.</p>

<h2>4. 이용자의 권리와 행사 방법</h2>
<ul><li>언제든지 <a href="/gate/account">내 정보</a> 화면에서 저장된 정보를 확인하고 <b>탈퇴(정보 삭제)</b>할 수 있습니다.</li>
<li>열람·정정·삭제·처리정지는 아래 연락처로도 요청할 수 있습니다.</li>
<li><b>동의를 거부할 권리가 있으며</b>, 동의하지 않으면 서비스를 이용할 수 없습니다(로그인 확인 외의 불이익은 없습니다).</li></ul>

<h2>5. 쿠키(자동 수집 장치)</h2>
<p>로그인 상태를 유지하기 위한 서명된 세션 쿠키 1개(<code>gate_sess</code>, 마지막 이용 후 최대 1년 — 이용할 때마다 연장되며 로그아웃·탈퇴 시 즉시 삭제)만 사용하며, 광고·추적 목적의 쿠키는 쓰지 않습니다. 브라우저 설정에서 쿠키를 막을 수 있으나 그러면 로그인이 유지되지 않습니다.</p>

<h2>6. 안전성 확보 조치</h2>
<ul><li>암호화된 연결(HTTPS)로만 로그인하며, 세션 쿠키는 변조 방지 서명을 합니다.</li>
<li>저장 정보는 최소한으로 하고 접근은 운영자로 제한하며, 사용자 정보 파일은 외부에 공개되지 않는 경로에 저장합니다.</li></ul>

<h2>7. 개인정보 보호책임자</h2>
<table><tr><th>운영자(책임자)</th><td>%(op)s</td></tr><tr><th>연락처</th><td>%(ct)s</td></tr></table>
<p class="sub">개인정보 침해 신고·상담: 개인정보침해신고센터(privacy.kisa.or.kr, 국번없이 118), 개인정보분쟁조정위원회(www.kopico.go.kr, 1833-6972)</p>

<h2>8. 처리방침의 변경</h2>
<p>내용이 바뀌면 시행일과 버전을 갱신하고, 다시 로그인할 때 변경된 내용에 대한 동의를 새로 받습니다.</p>
</div>%(foot)s""" % {"ver": POLICY_VERSION, "eff": POLICY_EFFECTIVE, "op": op, "ct": ct, "foot": _foot(), "logdays": html.escape(_env("PRIVACY_LOG_DAYS", "14"))}


def consent_html(nickname, nxt, error=""):
    err = '<p class="warn">%s</p>' % html.escape(error) if error else ""
    return """
<div class="card"><h1>가입 동의</h1>
<p class="sub">%(name)s 님, 이용하기 전에 아래 내용을 확인하고 동의해 주세요.</p>%(err)s
<form method="post" action="/gate/consent">
<input type="hidden" name="next" value="%(next)s">
<h2>개인정보 수집·이용 동의 (필수)</h2>
<table>
<tr><th>수집 항목</th><td>소셜 로그인 고유 식별번호, 이름(닉네임)</td></tr>
<tr><th>이용 목적</th><td>이용자 확인, 서비스 이용 권한 관리, 부정 이용 방지</td></tr>
<tr><th>보유 기간</th><td>탈퇴 시까지 (탈퇴하면 즉시 삭제)</td></tr>
<tr><th>동의 거부 권리</th><td>동의하지 않을 수 있으며, 이 경우 서비스를 이용할 수 없습니다.</td></tr>
</table>
<label class="chk"><input type="checkbox" name="agree_privacy" value="1"><span><b>[필수]</b> 개인정보 수집·이용에 동의합니다. (<a href="/privacy" target="_blank">처리방침 보기</a>)</span></label>
<label class="chk"><input type="checkbox" name="agree_age" value="1"><span><b>[필수]</b> 만 14세 이상입니다.</span></label>
<label class="chk"><input type="checkbox" name="agree_notice" value="1"><span><b>[필수]</b> 이 서비스의 기사·뉴스레터 내용은 <b>개인 학습용</b>이며, 저작권이 원 저작자에게 있어 <b>복사·재배포하지 않겠습니다.</b></span></label>
<button class="btn primary" type="submit">동의하고 시작하기</button>
</form></div>
<div class="foot"><a href="/gate/logout">동의하지 않고 로그아웃</a></div>""" % {
        "name": html.escape(nickname or ""), "next": html.escape(nxt, quote=True), "err": err}


def login_html(nxt, c):
    q = "?next=" + urllib.parse.quote(nxt)
    btns = ""
    if c["google"]:
        btns += '<a class="btn google" href="/gate/google/start%s">🔵 구글로 계속하기</a>' % q
    if c["kakao"]:
        btns += '<a class="btn kakao" href="/gate/kakao/start%s">💬 카카오로 계속하기</a>' % q
    note = ("가입 후 관리자가 승인하면 이용할 수 있어요." if c["approval"] == "manual"
            else "로그인하고 개인정보 처리 동의를 하면 바로 이용할 수 있어요.")
    return """
<div class="card"><h1>📚 경제 공부 · 📰 신문 요약</h1>
<p class="sub">로그인한 분만 볼 수 있어요. %s</p>%s
<p class="sub">로그인하면 <a href="/privacy">개인정보 처리방침</a>을 확인한 것으로 보며, 다음 화면에서 동의를 받습니다. 이메일은 수집하지 않아요.</p>
</div>""" % (html.escape(note), btns)


def who_html(request=None):
    """화면 맨 위 탭 오른쪽에 '길동 님 · 구글' 처럼 지금 어느 계정으로 들어왔는지 보여 준다(누르면 내 정보).
    잠금이 꺼져 있거나 로그인 정보가 없으면(예: 서버 내부 PDF 만들기) 빈 글."""
    if request is None or not cfg()["enabled"]:
        return ""
    try:
        u = session_user(request)
    except Exception:
        u = None
    if not u:
        return ""
    prov = {"google": "구글", "kakao": "카카오"}.get(u["provider"], u["provider"])
    return '<a class="who" href="/gate/account" title="내 정보">%s 님 · %s</a>' % (html.escape(u["nickname"] or ""), html.escape(prov))


def footer_html(request=None):
    """/slack·/dig 맨 아래에 끼워 넣는 링크(처리방침은 항상 쉽게 찾을 수 있어야 한다). 잠금이 꺼져 있으면 빈 글."""
    if not cfg()["enabled"]:
        return ""
    return ('<footer class="sitefoot"><a href="/privacy">개인정보 처리방침</a> · <a href="/gate/account">내 정보·탈퇴</a>'
            ' · <a href="/gate/logout">로그아웃</a></footer>')


# ───────────────────────── 라우터·중간 문지기 ─────────────────────────
def _is_gated(path):
    return (path in ("/slack", "/dig") or path.startswith(("/slack/", "/dig/", "/api/dig/", "/api/news/")))


def _is_api(path):
    return path.startswith(("/api/", "/slack/"))


def _cookie_args(max_age):
    return dict(max_age=max_age, httponly=True, secure=cfg()["https"], samesite="lax", path="/")


def _session_token(uid):
    """로그인 쿠키 값: 사용자 번호 + 발급 시각(iat). 1년 유효."""
    return _sign({"uid": uid, "iat": int(time.time())}, SESSION_DAYS * 86400)


def session_user(request):
    p = _unsign(request.cookies.get(COOKIE_SESSION, ""))
    return get_user(p["uid"]) if p and "uid" in p else None


def _form(body_bytes):
    return {k: v[0] for k, v in urllib.parse.parse_qs(body_bytes.decode("utf-8", "replace")).items()}


def _check(request):
    """잠긴 주소에 들어올 때의 판정. 통과면 None, 아니면 돌려보낼 응답."""
    from fastapi.responses import JSONResponse, RedirectResponse
    path = request.url.path
    key = internal_key()
    sent = request.headers.get("x-gate-internal", "")
    if key and sent and hmac.compare_digest(sent, key):
        return None
    user = session_user(request)
    api = _is_api(path)
    nxt = urllib.parse.quote(safe_next(path + (("?" + request.url.query) if request.url.query else ""), "/slack"))
    if not user:
        return JSONResponse({"ok": False, "reason": "login"}, status_code=401) if api else RedirectResponse("/gate/login?next=" + nxt, 302)
    if user["status"] == "blocked":
        return JSONResponse({"ok": False, "reason": "blocked"}, status_code=403) if api else _page(
            "이용 제한", '<div class="card"><h1>이용이 제한되었어요</h1><p>문의: 운영자에게 연락해 주세요.</p></div>' + _foot(), 403)
    if user["consent_version"] != POLICY_VERSION:
        return JSONResponse({"ok": False, "reason": "consent"}, status_code=403) if api else RedirectResponse("/gate/consent?next=" + nxt, 302)
    if user["status"] != "approved":
        return JSONResponse({"ok": False, "reason": "pending"}, status_code=403) if api else RedirectResponse("/gate/pending", 302)
    return None


def _renew_session(request, resp):
    """로그인 상태로 쓰는 중이면 쿠키 기간을 다시 1년으로 늘린다(7일에 한 번).
    승인된 사용자에게만 — 탈퇴·차단·승인 취소된 사람의 쿠키는 연장하지 않는다. 로그아웃·탈퇴 응답은 건너뛴다."""
    path = request.url.path
    if not cfg()["enabled"] or path in ("/gate/logout", "/gate/delete") or not (_is_gated(path) or path.startswith("/gate/")):
        return
    p = _unsign(request.cookies.get(COOKIE_SESSION, ""))
    if not p or "uid" not in p or time.time() - int(p.get("iat", 0)) < RENEW_AFTER_DAYS * 86400:
        return
    u = get_user(p["uid"])
    if u and u["status"] == "approved":
        resp.set_cookie(COOKIE_SESSION, _session_token(u["id"]), **_cookie_args(SESSION_DAYS * 86400))


def install(app):
    """app.py 에서 한 번 부른다: 문지기 + /gate/* /privacy 화면을 붙인다."""
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse, RedirectResponse

    r = APIRouter()
    c0 = cfg()
    if c0["enabled"]:
        print("[gate] 잠금 켜짐 · 승인 방식=%s · 제공자=%s" % (c0["approval"], ",".join(p for p in ("google", "kakao") if c0[p])))
        if not (c0["operator"] and c0["contact"]):
            print("[gate] ⚠️ PRIVACY_OPERATOR / PRIVACY_CONTACT 가 비어 처리방침에 빈칸이 보입니다. .env 에 채우세요.")
    else:
        print("[gate] 설정이 덜 되어 잠금이 꺼져 있습니다(열린 상태). GATE_BASE_URL + 구글/카카오 키가 필요 — `python3 gate.py check`")

    @app.middleware("http")
    async def _gate_mw(request: Request, call_next):
        # 다른 사이트에서 날아온 POST(CSRF)는 로그인 여부와 상관없이 거부
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("sec-fetch-site", "") == "cross-site" \
                and (request.url.path.startswith("/gate/") or _is_gated(request.url.path)):
            return JSONResponse({"ok": False, "reason": "cross-site"}, status_code=403)
        if cfg()["enabled"] and _is_gated(request.url.path):
            deny = _check(request)
            if deny is not None:
                return deny
        resp = await call_next(request)
        _renew_session(request, resp)
        if _is_gated(request.url.path) and cfg()["enabled"]:
            # 공용 캐시(프록시)에 로그인한 사람의 내용이 남지 않게. 브라우저 자체 캐시(사진 등)는 그대로 허용.
            resp.headers.setdefault("Cache-Control", "private")
            resp.headers["Vary"] = "Cookie"
        return resp

    def _off():
        return _page("로그인 설정 필요", '<div class="card"><h1>로그인 기능이 아직 설정되지 않았어요</h1>'
                     '<p class="sub">운영자: 서버에서 <code>python3 gate.py check</code> 로 빠진 설정을 확인하세요.</p></div>' + _foot())

    @r.get("/privacy")
    def privacy():
        return _page("개인정보 처리방침", privacy_html())

    @r.get("/gate/privacy")
    def privacy2():
        return RedirectResponse("/privacy", 302)

    @r.get("/gate/login")
    def login(request: Request, next: str = ""):
        c = cfg()
        if not c["enabled"]:
            return _off()
        nxt = safe_next(next)
        u = session_user(request)
        if u and u["consent_version"] == POLICY_VERSION and u["status"] == "approved":
            return RedirectResponse(nxt, 302)
        return _page("로그인", login_html(nxt, c) + _foot())

    @r.get("/gate/{provider}/start")
    def start(provider: str, next: str = ""):
        c = cfg()
        if not c["enabled"] or provider not in ("google", "kakao") or not c[provider]:
            return _off() if not c["enabled"] else _page("안내", '<div class="card"><p>사용할 수 없는 로그인 방식이에요.</p></div>', 404)
        state = secrets.token_urlsafe(24)
        resp = RedirectResponse(authorize_url(provider, state), 302)
        resp.set_cookie(COOKIE_STATE, _sign({"s": state, "n": safe_next(next), "p": provider}, STATE_MINUTES * 60), **_cookie_args(STATE_MINUTES * 60))
        return resp

    @r.get("/gate/{provider}/callback")
    def callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
        c = cfg()
        if not c["enabled"] or provider not in ("google", "kakao"):
            return _off()
        st = _unsign(request.cookies.get(COOKIE_STATE, ""))
        if error or not code or not st or st.get("p") != provider or not hmac.compare_digest(str(st.get("s", "")), state):
            return _page("로그인 실패", '<div class="card"><h1>로그인하지 못했어요</h1><p>보안 확인에 실패했거나 로그인을 취소하셨어요. 다시 시도해 주세요.</p>'
                         '<a class="btn primary" href="/gate/login">다시 로그인</a></div>' + _foot(), 400)
        try:
            uid, nick = identity_from_code(provider, code)
        except Exception as e:
            print("[gate] %s 로그인 실패: %r" % (provider, e))
            return _page("로그인 실패", '<div class="card"><h1>로그인 서버와 연결하지 못했어요</h1><p>잠시 후 다시 시도해 주세요.</p>'
                         '<a class="btn primary" href="/gate/login">다시 로그인</a></div>' + _foot(), 502)
        user = upsert_login(provider, uid, nick)
        nxt = safe_next(st.get("n"))
        dest = nxt if user["consent_version"] == POLICY_VERSION else "/gate/consent?next=" + urllib.parse.quote(nxt)
        resp = RedirectResponse(dest, 302)
        resp.set_cookie(COOKIE_SESSION, _session_token(user["id"]), **_cookie_args(SESSION_DAYS * 86400))
        resp.delete_cookie(COOKIE_STATE, path="/")
        return resp

    @r.get("/gate/consent")
    def consent_get(request: Request, next: str = ""):
        if not cfg()["enabled"]:
            return _off()
        u = session_user(request)
        if not u:
            return RedirectResponse("/gate/login?next=" + urllib.parse.quote(safe_next(next)), 302)
        return _page("가입 동의", consent_html(u["nickname"], safe_next(next)))

    @r.post("/gate/consent")
    async def consent_post(request: Request):
        if not cfg()["enabled"]:
            return _off()
        u = session_user(request)
        f = _form(await request.body())
        nxt = safe_next(f.get("next"))
        if not u:
            return RedirectResponse("/gate/login?next=" + urllib.parse.quote(nxt), 302)
        if not (f.get("agree_privacy") and f.get("agree_age") and f.get("agree_notice")):
            return _page("가입 동의", consent_html(u["nickname"], nxt, "필수 항목 3개에 모두 동의해야 이용할 수 있어요."), 400)
        record_consent(u["id"], ["privacy(필수)", "age14(필수)", "notice(필수)"])
        return RedirectResponse(nxt if u["status"] == "approved" else "/gate/pending", 303)

    @r.get("/gate/pending")
    def pending(request: Request):
        u = session_user(request)
        if not u:
            return RedirectResponse("/gate/login", 302)
        if u["status"] == "approved" and u["consent_version"] == POLICY_VERSION:
            return RedirectResponse("/slack", 302)
        return _page("승인 대기", '<div class="card"><h1>⏳ 승인을 기다리고 있어요</h1><p>%s 님, 가입은 끝났고 운영자가 승인하면 이용할 수 있어요.</p>'
                     '<p class="sub">승인되면 이 화면을 새로고침하세요.</p></div><div class="foot"><a href="/gate/logout">로그아웃</a> · <a href="/privacy">처리방침</a></div>'
                     % html.escape(u["nickname"] or ""))

    @r.get("/gate/account")
    def account(request: Request):
        if not cfg()["enabled"]:
            return _off()
        u = session_user(request)
        if not u:
            return RedirectResponse("/gate/login?next=/slack", 302)
        prov = {"google": "구글", "kakao": "카카오"}.get(u["provider"], u["provider"])
        body = """<div class="card"><h1>내 정보</h1>
<table><tr><th>이름(닉네임)</th><td>%s</td></tr><tr><th>로그인 방식</th><td>%s</td></tr>
<tr><th>가입 시각</th><td>%s</td></tr><tr><th>동의 시각</th><td>%s (처리방침 %s)</td></tr><tr><th>상태</th><td>%s</td></tr></table>
<p class="sub">저장된 정보는 위가 전부예요(이메일 등은 저장하지 않습니다).</p>
<p><a class="btn primary" href="/slack">📰 신문 요약</a><a class="btn primary" href="/dig">📚 경제 공부 (디그)</a></p>
<h2>탈퇴 (정보 삭제)</h2><p class="sub">누르면 저장된 모든 정보와 동의 기록이 즉시 삭제되며 되돌릴 수 없어요.</p>
<form method="post" action="/gate/delete"><label class="chk"><input type="checkbox" name="confirm" value="1"><span>내 정보를 삭제하고 탈퇴합니다.</span></label>
<button class="btn danger" type="submit">탈퇴하고 정보 삭제</button></form></div>
<div class="foot"><a href="/gate/logout">로그아웃</a> · <a href="/privacy">개인정보 처리방침</a></div>""" % (
            html.escape(u["nickname"] or ""), html.escape(prov), html.escape(u["created_at"] or ""),
            html.escape(u["consent_at"] or "-"), html.escape(u["consent_version"] or "-"),
            html.escape({"approved": "이용 가능", "pending": "승인 대기", "blocked": "이용 제한"}.get(u["status"], u["status"])))
        return _page("내 정보", body)

    @r.post("/gate/delete")
    async def delete(request: Request):
        u = session_user(request)
        f = _form(await request.body())
        if not u:
            return RedirectResponse("/gate/login", 302)
        if not f.get("confirm"):
            return RedirectResponse("/gate/account", 303)
        delete_user(u["id"])
        resp = _page("탈퇴 완료", '<div class="card"><h1>탈퇴가 완료되었어요</h1><p>저장된 정보와 동의 기록을 모두 삭제했어요. 이용해 주셔서 감사합니다.</p></div>')
        resp.delete_cookie(COOKIE_SESSION, path="/")
        return resp

    @r.get("/gate/logout")
    def logout():
        resp = RedirectResponse("/gate/login", 302)
        resp.delete_cookie(COOKIE_SESSION, path="/")
        return resp

    app.include_router(r)


# ───────────────────────── 운영 명령 ─────────────────────────
def _print_users(rows):
    print("%-4s %-7s %-9s %-22s %-20s %s" % ("번호", "방식", "상태", "닉네임", "가입", "동의버전"))
    for u in rows:
        print("%-4s %-7s %-9s %-22s %-20s %s" % (u["id"], u["provider"], u["status"], (u["nickname"] or "")[:20], u["created_at"], u["consent_version"] or "-"))
    if not rows:
        print("(없음)")


def cli(argv):
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        c = cfg()
        ok = lambda b: "OK " if b else "빠짐"  # noqa: E731
        print("== 로그인 잠금 설정 점검 ==")
        print("[%s] GATE_BASE_URL            = %s   (예: https://mystatus-btr.duckdns.org)" % (ok(c["base"]), c["base"] or "-"))
        print("[%s] 구글  GATE_GOOGLE_CLIENT_ID / GATE_GOOGLE_CLIENT_SECRET" % ok(c["google"]))
        print("[%s] 카카오 GATE_KAKAO_REST_KEY (선택: GATE_KAKAO_CLIENT_SECRET)" % ok(c["kakao"]))
        print("[%s] PRIVACY_OPERATOR / PRIVACY_CONTACT  (처리방침의 보호책임자 — 법적 필수)" % ok(c["operator"] and c["contact"]))
        print("     승인 방식 GATE_APPROVAL = %s  (auto=로그인+동의만 / manual=운영자 승인 필요)" % c["approval"])
        print("     https 여부 = %s %s" % (c["https"], "" if c["https"] else "  ⚠️ 구글 로그인은 https 도메인이 필수"))
        print("\n⇒ 잠금 상태: %s" % ("켜짐" if c["enabled"] else "꺼짐(열린 상태)"))
        if c["base"]:
            print("\n등록할 리디렉션 URI(정확히 이대로):")
            print("  구글  : %s" % redirect_uri("google"))
            print("  카카오: %s" % redirect_uri("kakao"))
            print("  처리방침 주소(구글 동의 화면에 입력): %s/privacy" % c["base"])
        return 0
    if cmd in ("list", "pending"):
        with _db() as con:
            rows = con.execute("SELECT * FROM users %s ORDER BY id" % ("WHERE status='pending'" if cmd == "pending" else "")).fetchall()
        _print_users(rows)
        return 0
    if cmd == "stats":
        with _db() as con:
            for s, n in con.execute("SELECT status, COUNT(*) FROM users GROUP BY status"):
                print("%-9s %d" % (s, n))
        return 0
    if cmd in ("approve", "block", "unblock", "delete") and len(argv) > 1 and argv[1].isdigit():
        uid = int(argv[1])
        if cmd == "delete":
            delete_user(uid)
            print("삭제했어요: %d" % uid)
            return 0
        n = set_status(uid, "blocked" if cmd == "block" else "approved")
        print(("처리했어요: %d → %s" % (uid, "blocked" if cmd == "block" else "approved")) if n else "그런 번호가 없어요: %d" % uid)
        return 0 if n else 1
    print(__doc__.split("운영 명령:")[-1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
