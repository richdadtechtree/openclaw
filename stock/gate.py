"""로그인(구글·카카오) + 개인정보 동의 + 승인 게이트 (2026-10-23 사용자 요청).

잠그는 곳: /economy(신문 요약, 옛 /slack 은 넘겨 줌) · /dig(경제 공부) · /ai(AI 소식, 2026-10-28) 와 그 화면이 쓰는 /api/news/* · /api/dig/* · /api/ai/* · /slack/* 주소.
          (주가 대시보드 '/' 와 나머지는 그대로 둔다)

흐름
  처음 방문 → /gate/login (구글·카카오) → 소셜 로그인 → /gate/consent (개인정보 동의 3칸) → 입장
  승인 방식  GATE_APPROVAL=auto   : 로그인 + 동의만 하면 바로 입장 (지금)
             GATE_APPROVAL=manual : 가입하면 '승인 대기' → 운영자가 `python3 gate.py approve <번호>` 해야 입장 (나중에)

개인정보 최소 수집: 소셜 로그인 고유번호 + **가입할 때 이용자가 직접 정한 닉네임**만 저장한다.
구글·카카오에는 이름·이메일·프로필을 아예 요청하지 않는다(구글 scope=openid 만, 카카오 scope 없음) — 실명이 서버에 들어올 길이 없다.
이용 기한: 승인할 때 관리자가 기한(무기한·7일·30일·90일·1년·날짜 지정)을 정할 수 있다. 기한이 지나면(그 날 자정까지 사용 가능) 로그인해도 '이용 기간 종료' 화면이 나오고,
          관리자가 기한을 바꾸면 곧바로 다시 쓸 수 있다. 자동 승인(auto)일 때 신규 가입자에게 체험 기간을 주려면 .env 에 GATE_AUTO_DAYS=14 처럼 적는다(기본 0 = 무기한).
관리자: 이메일을 받지 않으므로 '이메일이 ○○이면 관리자'를 쓸 수 없다. 그 계정으로 로그인한 뒤 서버에서 `gate.py admin 회원번호` 로 한 번 지정한다
        (웹에서는 관리자 권한을 줄 수 없음). 관리자는 /gate/admin 에서 가입자 목록을 보고 승인·차단·차단 해제·삭제할 수 있다.
저장 위치: ~/.openclaw/secret/gate/  (secret/ 은 git 이 절대 올리지 않는 폴더 — 서명 열쇠·사용자 DB 보호)

안전장치
  * 설정이 덜 됐으면(주소·키 없음) 잠금이 꺼진 채 '열려' 있다 → git 자동 반영 직후 갑자기 못 들어가는 사고 방지(경고만 출력).
  * 표준 라이브러리만 사용(새 설치 없음). 쿠키는 직접 HMAC 서명(변조·만료 검사).
  * 쿠키 HttpOnly + SameSite=Lax + (https 일 때) Secure, 다른 사이트에서 온 POST 는 거부, 로그인 후 이동 주소는 안전한 것만.
  * 서버 내부 작업(PDF 만들기)은 내부 열쇠 헤더로만 통과 — nginx 뒤에선 모든 요청이 127.0.0.1 로 보이므로 '로컬이면 통과' 는 쓰지 않는다.

운영 명령: python3 gate.py check | list | pending | approve N | block N | unblock N | delete N | stats | admin N | unadmin N | approve N [일수|YYYY-MM-DD|none]
"""
import base64
import hashlib
import ipaddress
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 처리방침·동의 문구를 고치면 이 날짜를 바꾼다 → 모든 사용자가 새 문구에 다시 동의해야 입장한다.
POLICY_VERSION = "2026-10-30.2"      # 동의 기록에 남는 버전(문구를 고칠 때마다 올린다) — .1=찰스 챌린지(기수·작성 글·같은 기수 공개) 추가, .2=모르는 용어 AI 풀이(용어 글자만 전송)
POLICY_EFFECTIVE = "2026-10-30"        # 처리방침에 보이는 시행일

COOKIE_SESSION = "gate_sess"          # ⚠️ PT 대시보드(Flask)의 'session' 쿠키와 같은 도메인에서 겹치지 않게 이름을 다르게
COOKIE_STATE = "gate_state"
COOKIE_IPADM = "gate_ipadm"        # 서버 IP 로 들어온 관리자 전용 쿠키(도메인 접속에서는 쓰이지 않음)
IPADM_HOURS = 12                   # IP 관리자 모드 유효 시간(연장 없음)
IPADM_MIN_PW = 12                  # 이보다 짧은 비밀번호는 쓰지 않는다(추측 공격 방지)
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


_NEXT_OK = re.compile(r"^/(economy|slack|dig|ai|market|challenge)(/[A-Za-z0-9_\-./]*)?(\?[A-Za-z0-9_\-=&%.]*)?$")


def safe_next(target, default="/economy"):
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
-- 찰스 챌린지(2026-10-30, 상세: challenge.py · docs/challenge-plan.md)
CREATE TABLE IF NOT EXISTS cohorts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
  start_date TEXT NOT NULL, end_date TEXT NOT NULL, memo TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS challenge_posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, cohort_id INTEGER,
  day TEXT NOT NULL, page TEXT NOT NULL,
  what TEXT NOT NULL, why TEXT NOT NULL, how TEXT NOT NULL, think TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(user_id, day, page));
CREATE INDEX IF NOT EXISTS ix_cp_day ON challenge_posts(day, cohort_id);
CREATE TABLE IF NOT EXISTS challenge_excused(
  user_id INTEGER NOT NULL, day TEXT NOT NULL, by_admin INTEGER, at TEXT NOT NULL, PRIMARY KEY(user_id, day));
CREATE TABLE IF NOT EXISTS challenge_days(
  day TEXT PRIMARY KEY, pages INTEGER NOT NULL, seen_at TEXT NOT NULL);
-- 📖 모르는 용어 풀이(2026-10-30): 같은 용어는 한 번만 AI 에 묻고 모두가 같이 쓴다(사람 정보 없음)
CREATE TABLE IF NOT EXISTS glossary(
  key TEXT PRIMARY KEY, term TEXT NOT NULL, short TEXT, easy TEXT, invest TEXT,
  source TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def _now():
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S")


def _db():
    path = os.path.join(gate_dir(), "gate.sqlite")
    fresh = not os.path.exists(path)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    have = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
    for col, ddl in (("is_admin", "INTEGER NOT NULL DEFAULT 0"), ("expires_at", "TEXT"),
                     ("nick_set", "INTEGER NOT NULL DEFAULT 0"), ("nick_key", "TEXT"), ("theme", "TEXT"),
                     ("role", "TEXT"), ("cohort_id", "INTEGER"), ("celebrated_at", "TEXT"),
                     ("apply", "TEXT")):                     # apply='charles' = 챌린지 입구로 가입·신청(찰스 승인 대기)       # 예전에 만든 DB 도 가입자 정보를 그대로 둔 채 이어서 쓴다
        if col not in have:
            con.execute("ALTER TABLE users ADD COLUMN %s %s" % (col, ddl))
    _cp = {r["name"] for r in con.execute("PRAGMA table_info(challenge_posts)")}
    if "terms" not in _cp:
        con.execute("ALTER TABLE challenge_posts ADD COLUMN terms TEXT")              # 📖 모르는 용어(JSON 목록)
    if "title" not in _cp:
        con.execute("ALTER TABLE challenge_posts ADD COLUMN title TEXT")              # 📰 기사 제목(자동으로 따거나 직접 고침)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_nick ON users(nick_key)")          # 같은 닉네임 중복 방지(NULL 은 여러 개 가능)
    # 예전에 구글·카카오가 알려 줘서 저장된 이름(실명일 수 있음)은 지운다 — 이제는 이용자가 직접 정한 닉네임(nick_set=1)만 보관한다.
    con.execute("UPDATE users SET nickname=NULL, nick_key=NULL WHERE nick_set=0 AND nickname IS NOT NULL")
    con.commit()
    if fresh:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return con


_NICK_RE = re.compile(r"^[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ_.\- ]{2,20}$")
_RESERVED = {"관리자", "운영자", "운영진", "관리", "운영", "admin", "administrator", "root", "system", "시스템", "openclaw", "뚜떵또", "운영자님", "관리자님"}
NICK_MSG = {"len": "닉네임은 2~20자로 입력해 주세요.",
            "chars": "닉네임에는 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요.",
            "alnum": "글자나 숫자가 하나 이상 있어야 해요.",
            "digits": "전화번호처럼 긴 숫자(8자리 이상)는 닉네임으로 쓸 수 없어요.",
            "reserved": "사용할 수 없는 닉네임이에요.",
            "dup": "이미 사용 중인 닉네임이에요. 다른 닉네임을 입력해 주세요."}


def nick_key(n):
    """중복 검사용 키: 대소문자·공백 차이를 무시(예: 'Nuri'와 'nuri', '누 리'와 '누리'는 같은 닉네임)."""
    return unicodedata.normalize("NFC", n).casefold().replace(" ", "")


def validate_nickname(raw, admin=False, exclude_uid=None):
    """닉네임 검사. 맞으면 (True, 다듬은 닉네임), 아니면 (False, 이유 코드: NICK_MSG 의 키).
    실명·전화번호·이메일이 닉네임으로 들어오는 것을 막는다(허용 글자 제한 + 긴 숫자 거부 + '@' 불가)."""
    n = re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(raw or ""))).strip()
    if not 2 <= len(n) <= 20:
        return False, "len"
    if not _NICK_RE.match(n):
        return False, "chars"
    if not re.search(r"[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]", n):
        return False, "alnum"
    if re.search(r"\d{8,}", n.replace(" ", "").replace("-", "").replace(".", "").replace("_", "")):
        return False, "digits"
    if not admin and nick_key(n) in {nick_key(x) for x in _RESERVED}:
        return False, "reserved"          # 운영자·관리자를 사칭하는 이름 금지(관리자 본인은 가능)
    with _db() as con:
        if con.execute("SELECT 1 FROM users WHERE nick_key=? AND id<>?", (nick_key(n), exclude_uid or -1)).fetchone():
            return False, "dup"
    return True, n


def disp(u):
    """화면에 보여 줄 이름 = 이용자가 정한 닉네임(아직 없으면 안내 글)."""
    return u["nickname"] if u["nickname"] else "(닉네임 미설정)"


def _today():
    return datetime.now(KST).strftime("%Y-%m-%d")


def _add_days(n):
    return (datetime.now(KST) + timedelta(days=int(n))).strftime("%Y-%m-%d")


def valid_date(t):
    try:
        datetime.strptime(t, "%Y-%m-%d")
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", t))
    except Exception:
        return False


def parse_term(term, until=""):
    """관리자 화면·서버 명령의 기한 입력 → (올바른가, 'YYYY-MM-DD' 또는 None=무기한).
    none=무기한 / 숫자=오늘부터 그 일수(최대 10년) / custom(+until) 또는 날짜 글자 = 그 날짜까지(오늘 이후, 10년 이내)."""
    t = (term or "").strip()
    if t in ("none", "무기한"):
        return True, None
    if t.isdigit() and 1 <= int(t) <= 3650:
        return True, _add_days(t)
    if t == "custom":
        t = (until or "").strip()
    if valid_date(t) and _today() <= t <= _add_days(3650):
        return True, t
    return False, None


def is_expired(u):
    """승인은 됐지만 이용 기한이 지났나(기한 날짜의 밤 12시까지 쓸 수 있다)."""
    e = (u["expires_at"] or "")[:10]
    return bool(u["status"] == "approved" and e and _today() > e)


def days_left(u):
    """남은 일수(오늘이면 0). 기한이 없으면 None."""
    e = (u["expires_at"] or "")[:10]
    if not e or not valid_date(e):
        return None
    return (datetime.strptime(e, "%Y-%m-%d").date() - datetime.now(KST).date()).days


def expiry_text(u):
    e = (u["expires_at"] or "")[:10]
    if not e:
        return "무기한"
    return ("만료됨 (%s)" % e) if is_expired(u) else "%s까지" % e


def upsert_login(provider, uid, apply=None):
    """소셜 로그인에 성공했을 때: 처음이면 가입(승인 방식에 따라 상태 결정, 닉네임은 동의 화면에서 직접 입력), 아니면 최근 로그인만 갱신.
    구글·카카오가 알려 주는 이름은 받지도 저장하지도 않는다.
    apply='charles' = 🔥 챌린지 입구(/gate/charles·/challenge)로 처음 가입 → 승인 방식과 상관없이 '승인 대기'.
    운영자가 관리 화면에서 ☑ 찰스로 지정해야만 쓸 수 있다(그 전엔 신문 요약 등 다른 화면도 못 씀)."""
    with _db() as con:
        row = con.execute("SELECT * FROM users WHERE provider=? AND provider_uid=?", (provider, str(uid))).fetchone()
        if row:
            con.execute("UPDATE users SET last_login_at=? WHERE id=?", (_now(), row["id"]))
        else:
            charles = apply == "charles"
            status = "approved" if (cfg()["approval"] == "auto" and not charles) else "pending"
            auto_days = _env("GATE_AUTO_DAYS", "0")
            exp = _add_days(auto_days) if status == "approved" and auto_days.isdigit() and 0 < int(auto_days) <= 3650 else None     # 체험 기간(기본 무기한)
            con.execute("INSERT INTO users(provider,provider_uid,status,expires_at,created_at,last_login_at,apply) VALUES(?,?,?,?,?,?,?)",
                        (provider, str(uid), status, exp, _now(), _now(), "charles" if charles else None))
        return con.execute("SELECT * FROM users WHERE provider=? AND provider_uid=?", (provider, str(uid))).fetchone()


def get_user(uid):
    try:
        with _db() as con:
            return con.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()
    except Exception:
        return None


def record_consent(uid, items, nickname=None):
    """동의 기록 + (처음 가입이면) 직접 정한 닉네임을 한꺼번에 저장. 동시에 같은 닉네임을 고른 경우 ValueError('dup')."""
    try:
        with _db() as con:
            con.execute("INSERT INTO consents(user_id,version,items,agreed_at) VALUES(?,?,?,?)",
                        (uid, POLICY_VERSION, json.dumps(items, ensure_ascii=False), _now()))
            con.execute("UPDATE users SET consent_version=?, consent_at=? WHERE id=?", (POLICY_VERSION, _now(), uid))
            if nickname is not None:
                con.execute("UPDATE users SET nickname=?, nick_key=?, nick_set=1 WHERE id=?", (nickname, nick_key(nickname), uid))
    except sqlite3.IntegrityError:
        raise ValueError("dup") from None


def set_nickname(uid, nickname):
    try:
        with _db() as con:
            return con.execute("UPDATE users SET nickname=?, nick_key=?, nick_set=1 WHERE id=?", (nickname, nick_key(nickname), uid)).rowcount
    except sqlite3.IntegrityError:
        raise ValueError("dup") from None


def delete_user(uid):
    """탈퇴: 사용자 정보와 동의 기록을 모두 지운다(보관하지 않음). 챌린지 글·인정 기록도 함께 지운다."""
    with _db() as con:
        con.execute("DELETE FROM consents WHERE user_id=?", (uid,))
        con.execute("DELETE FROM challenge_posts WHERE user_id=?", (uid,))
        con.execute("DELETE FROM challenge_excused WHERE user_id=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))


THEMES = ("auto", "light", "dark")


def set_theme(uid, theme):
    """계정별 화면 모드 저장(auto=기기 설정 따름 / light=화이트 / dark=다크). 허용 값 외에는 저장하지 않는다."""
    if theme not in THEMES:
        return False
    with _db() as con:
        con.execute("UPDATE users SET theme=? WHERE id=?", (theme, uid))
    return True


def theme_head(request):
    """<head> 에 끼워 넣는 짧은 스크립트: 이 계정이 고른 화면 모드를 그림이 그려지기 전에 적용(깜빡임 방지).
    고른 적 없으면 빈 글 → 화면이 예전처럼 이 브라우저의 기억/기기 설정을 따른다. 값은 허용 목록에서만 나오므로 그대로 넣어도 안전."""
    try:
        u = session_user(request) if (request is not None and cfg()["enabled"]) else None
    except Exception:
        u = None
    t = (u["theme"] if u and "theme" in u.keys() else None)
    if t not in THEMES:
        return ""
    return ('<script>window.__GATE_THEME="%s";(function(t){var d=document.documentElement;'
            'if(t==="auto")d.removeAttribute("data-theme");else d.setAttribute("data-theme",t);})("%s");</script>' % (t, t))


def is_admin(u):
    """승인된 관리자인가. 관리자 지정은 서버에서 `gate.py admin N` 으로만 한다(웹에서 권한을 주는 길은 없음)."""
    return bool(u and u["is_admin"] and u["status"] == "approved")


def set_admin(uid, flag):
    with _db() as con:
        if flag:        # 관리자는 항상 승인된 상태여야 한다(차단된 채 관리자로 남는 모순 방지)
            return con.execute("UPDATE users SET is_admin=1, status='approved', expires_at=NULL WHERE id=?", (uid,)).rowcount     # 관리자는 기한으로 잠기지 않음
        return con.execute("UPDATE users SET is_admin=0 WHERE id=?", (uid,)).rowcount


# ───────────────────── 찰스 챌린지 역할 ─────────────────────
# role: NULL=일반 · 'charles'=챌린지 참가 중(디그·챌린지 탭만) · 'graduate'=완수(모든 탭 + 챌린지 기록)
def role_of(u):
    try:
        return u["role"] if u is not None and "role" in u.keys() else None
    except Exception:
        return None


def applied_charles(u):
    try:
        return bool(u is not None and "apply" in u.keys() and u["apply"] == "charles")
    except Exception:
        return False


def set_apply(uid, value):
    with _db() as con:
        con.execute("UPDATE users SET apply=? WHERE id=?", (value, int(uid)))


def is_charles(u):
    return role_of(u) == "charles" and not (u and u["is_admin"])


def can_challenge(u):
    """챌린지 화면을 볼 수 있나: 찰스·완수자·관리자."""
    return bool(u) and (is_admin(u) or role_of(u) in ("charles", "graduate"))


def nav_links(u, ip_admin=False):
    """맨 위 탭에 보일 (주소, 글자) 목록. 찰스는 디그·챌린지만."""
    eco, dig, ai, ch = ("/economy", "📰 신문 요약"), ("/dig", "📚 경제 공부 (디그)"), ("/ai", "🤖 AI 소식"), ("/challenge", "🔥 챌린지")
    mkt = ("/market", "📈 주가 대시보드")
    if ip_admin or (u and is_admin(u)) or role_of(u) == "graduate":
        return [eco, dig, ai, mkt, ch]
    if is_charles(u):
        return [dig, ch]
    return [eco, dig, ai, mkt]


def nav_html(request, current):
    """탭 링크 HTML(지금 화면은 aria-current 로 강조). 잠금이 꺼져 있거나 로그인 정보가 없으면 기본 3개."""
    u, ip = None, False
    try:
        if request is not None and cfg()["enabled"]:
            if is_ip_host(request):
                ip = ip_admin_ok(request)
            else:
                u = session_user(request)
    except Exception:
        u = None
    return "".join('<a href="%s"%s>%s</a>' % (href, ' aria-current="page"' if href == "/" + current else "", label)
                   for href, label in nav_links(u, ip))


_NAV_RE = re.compile(r"<!--GATE_NAV:(\w+)-->.*?<!--/GATE_NAV-->", re.S)


def fill_page(html_text, request=None):
    """화면 HTML 의 자리표를 채운다: 탭(역할별)·맨 위 '이름 님'·맨 아래 링크·계정 화면 모드.
    자리표 사이의 기본 탭은 이 함수가 못 돌 때(파일을 그대로 열 때) 보이는 예비용."""
    try:
        foot, who, thm = footer_html(request), who_html(request), theme_head(request)
    except Exception:
        foot = who = thm = ""
    try:
        html_text = _NAV_RE.sub(lambda m: nav_html(request, m.group(1)), html_text)
    except Exception:
        pass
    return html_text.replace("<!--GATE_THEME-->", thm).replace("<!--GATE_FOOT-->", foot).replace("<!--GATE_WHO-->", who)


# ───────────────────── 서버 IP 접속 (관리자 비밀번호) ─────────────────────
# 도메인 없이 http://서버IP:8000 또는 https://서버IP 로 들어오면(Host 가 IP 주소) 구글·카카오 로그인은 쓸 수 없다
# (구글은 도메인 필수). 대신 .env 의 GATE_IP_ADMIN_PASSWORD 를 아는 사람만 '관리자 모드'로 입장시킨다.
#   · 도메인 접속은 지금처럼 구글/카카오 · IP 접속은 이 비밀번호만 (서로 섞이지 않음)
#   · 비밀번호가 없거나 12자 미만이면 IP 접속은 통째로 막힘
#   · 틀리면 5번째에 15분 잠금, 맞아도 12시간 뒤 자동 로그아웃(연장 없음), 비밀번호를 바꾸면 기존 로그인 모두 무효
_ip_fail = {}        # {접속자: [연속 실패 횟수, 잠금 해제 시각]}  (서버가 다시 켜지면 초기화)


def host_only(request):
    h = (request.headers.get("host", "") or "").strip()
    if h.startswith("["):
        return h[1:h.find("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def is_ip_host(request):
    """주소창의 호스트가 숫자 IP(예: 158.179.162.52, [::1])인가. 도메인이면 False."""
    try:
        ipaddress.ip_address(host_only(request))
        return True
    except ValueError:
        return False


def ip_password():
    return _env("GATE_IP_ADMIN_PASSWORD")


def ip_enabled():
    return len(ip_password()) >= IPADM_MIN_PW


def _ipadm_ver():
    """비밀번호가 바뀌면 값이 달라져 예전 로그인 쿠키가 모두 무효가 된다(비밀번호 자체는 쿠키에 들어가지 않는다)."""
    return hashlib.sha256(_secret() + b"|ipadm|" + ip_password().encode()).hexdigest()[:20]


def ip_admin_ok(request):
    if not (ip_enabled() and is_ip_host(request)):
        return False
    p = _unsign(request.cookies.get(COOKIE_IPADM, ""))
    return bool(p and p.get("k") == "ipadm" and hmac.compare_digest(str(p.get("v", "")), _ipadm_ver()))


def _client_key(request):
    ip = request.client.host if request.client else "?"
    if ip in ("127.0.0.1", "::1"):                      # nginx 뒤라면 실제 접속자는 X-Forwarded-For 에 있다
        ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or ip)
    return ip[:64]


def ip_lock_left(key):
    st = _ip_fail.get(key)
    return max(0, int(st[1] - time.time())) if st else 0


def ip_note(key, ok):
    if ok:
        _ip_fail.pop(key, None)
        return
    if len(_ip_fail) > 500:                             # 메모리가 커지지 않게 지난 기록 정리
        now = time.time()
        for k in [k for k, v in _ip_fail.items() if v[1] < now]:
            _ip_fail.pop(k, None)
    st = _ip_fail.setdefault(key, [0, 0])
    st[0] += 1
    if st[0] >= 5:
        st[0], st[1] = 0, time.time() + 15 * 60


def ip_pseudo_admin():
    """IP 관리자 모드로 /gate/admin 을 쓸 때 쓰는 가짜 관리자(회원 번호 0 = 실제 가입자와 겹치지 않음)."""
    return {"id": 0, "nickname": "IP 관리자", "is_admin": 1}


def _csrf(uid):
    """관리 화면의 버튼이 '이 관리자가 이 화면에서 누른 것'임을 확인하는 표(다른 사이트가 몰래 누르게 하는 공격 방지)."""
    return hmac.new(_secret(), ("csrf:%d" % int(uid)).encode(), hashlib.sha256).hexdigest()[:32]


def set_access(uid, status, expires):
    """승인 상태와 이용 기한을 함께 바꾼다(expires=None 이면 무기한)."""
    with _db() as con:
        return con.execute("UPDATE users SET status=?, expires_at=? WHERE id=?", (status, expires, uid)).rowcount


def set_status(uid, status):
    with _db() as con:
        return con.execute("UPDATE users SET status=? WHERE id=?", (status, uid)).rowcount


# ───────────────────────── 소셜 로그인(구글·카카오) ─────────────────────────
class LoginServerError(Exception):
    """구글·카카오 서버가 거절했을 때. 거절 이유(오류 번호)를 서버 기록에 남기려고 응답 본문을 함께 담는다."""


def _fail_text(url, e):
    """HTTP 오류 → '주소 → 상태번호 + 상대 서버가 알려 준 이유'. (예: KOE010 = 카카오 클라이언트 시크릿 불일치)
    ⚠️ 주소의 ? 뒤(인가 코드 등)와 보낸 값(키·시크릿)은 기록하지 않는다 — 응답 본문만 남긴다."""
    try:
        body = e.read().decode("utf-8", "replace")[:300]
    except Exception:
        body = ""
    return "%s → HTTP %s %s" % (url.split("?")[0], getattr(e, "code", "?"), body)


def _post_form(url, data, timeout=15):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LoginServerError(_fail_text(url, e)) from None


def _get_json(url, token, timeout=15):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LoginServerError(_fail_text(url, e)) from None


def redirect_uri(provider):
    return "%s/gate/%s/callback" % (cfg()["base"], provider)


def authorize_url(provider, state):
    c = cfg()
    if provider == "google":
        # openid 만: 고유번호(sub)뿐. ⚠️ 이름(profile)·이메일(email)은 요청하지 않는다 — 닉네임은 이용자가 직접 정한다(최소 수집).
        q = {"client_id": _env("GATE_GOOGLE_CLIENT_ID"), "redirect_uri": redirect_uri("google"), "response_type": "code",
             "scope": "openid", "state": state, "prompt": "select_account"}
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)
    if provider == "kakao":
        # scope 를 보내지 않는다 → 카카오 회원번호(id)만 받고 닉네임·이메일 등은 요청하지 않는다.
        q = {"client_id": _env("GATE_KAKAO_REST_KEY"), "redirect_uri": redirect_uri("kakao"), "response_type": "code", "state": state}
        return "https://kauth.kakao.com/oauth/authorize?" + urllib.parse.urlencode(q)
    raise ValueError(provider)


def identity_from_code(provider, code):
    """인가 코드 → 고유번호(문자열). 이름 등은 받지 않는다. 네트워크 호출이라 시험에서는 이 함수를 가짜로 바꾼다."""
    if provider == "google":
        tok = _post_form("https://oauth2.googleapis.com/token", {
            "code": code, "client_id": _env("GATE_GOOGLE_CLIENT_ID"), "client_secret": _env("GATE_GOOGLE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri("google"), "grant_type": "authorization_code"})
        info = _get_json("https://openidconnect.googleapis.com/v1/userinfo", tok["access_token"])
        return str(info["sub"])
    if provider == "kakao":
        data = {"grant_type": "authorization_code", "client_id": _env("GATE_KAKAO_REST_KEY"),
                "redirect_uri": redirect_uri("kakao"), "code": code}
        if _env("GATE_KAKAO_CLIENT_SECRET"):
            data["client_secret"] = _env("GATE_KAKAO_CLIENT_SECRET")
        tok = _post_form("https://kauth.kakao.com/oauth/token", data)
        info = _get_json("https://kapi.kakao.com/v2/user/me", tok["access_token"])
        return str(info["id"])
    raise ValueError(provider)


# ───────────────────────── 화면(HTML) ─────────────────────────
_CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2230;--sub:#5b6577;--line:#e3e7ee;--blue:#2f7be0;--red:#c0392b;color-scheme:light dark}
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
input.txt{width:100%;font:inherit;font-size:16px;padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);margin:4px 0 6px}
main.wide{max-width:1320px}   /* 2026-10-30 '🔥 찰스 · 기수' 칸이 늘어 넓힘 */
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch} .tablewrap table{min-width:640px;margin:0}
.tablewrap th,.tablewrap td{width:auto;white-space:nowrap}
.tablewrap td.act{white-space:normal;min-width:230px}.tablewrap td.act div{margin:1px 0}   /* 내 정보 화면용 첫 칸 30% 규칙을 관리 표에는 쓰지 않음 · 날짜가 여러 줄로 꺾이지 않게 */
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 14px}
.tabs a{padding:6px 14px;border:1px solid var(--line);border-radius:999px;text-decoration:none;font-size:14px;color:var(--sub)}
.tabs a.on{background:var(--blue);border-color:var(--blue);color:#fff}
.b-ok{color:#12a150;font-weight:700}.b-wait{color:#b8730f;font-weight:700}.b-block{color:var(--red);font-weight:700}
form.inl{display:inline;margin:0}
.mini{font:inherit;font-size:13px;padding:4px 8px;margin:2px 3px 2px 0;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.mini.go{border-color:var(--blue);color:var(--blue)}.mini.stop{border-color:var(--red);color:var(--red)}
.note{background:rgba(127,127,127,.1);border-radius:10px;padding:10px 14px;margin:10px 0;font-size:14px}
"""


def _page(title, body, status=200, wide=False):
    from fastapi.responses import HTMLResponse
    doc = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           '<title>%s</title><style>%s</style></head><body><main%s>%s</main></body></html>') % (html.escape(title), _CSS, ' class="wide"' if wide else "", body)
    return HTMLResponse(doc, status_code=status, headers={"Cache-Control": "no-store"})


def expired_html(u):
    c = cfg()
    contact = ("문의: " + html.escape(c["contact"])) if c["contact"] else "운영자에게 문의해 주세요."
    return """<div class="card"><h1>⏰ 이용 기간이 끝났어요</h1>
<p>%s 님의 이용 기한은 <b>%s</b>까지였어요. 계속 이용하려면 운영자에게 기한 연장을 요청해 주세요.</p>
<p class="sub">%s · 연장되면 이 화면을 새로고침하면 바로 이용할 수 있어요.</p>
<a class="btn primary" href="/gate/account">내 정보 보기</a><a class="btn danger" href="/gate/logout">로그아웃</a></div>%s""" % (
        html.escape(disp(u)), html.escape((u["expires_at"] or "")[:10]), contact, _foot())


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
<tr><th>항목</th><td>소셜 로그인(구글 또는 카카오)이 알려 주는 <b>고유 식별번호</b>, 가입할 때 이용자가 직접 정한 <b>닉네임</b>, 가입 시각·최근 접속 시각, 동의 이력, <b>화면 모드 설정</b>(화이트/다크/자동 — 선택한 경우에만),
<b>(챌린지 참가자만)</b> 이용자가 직접 작성한 <b>챌린지 글</b>(WHAT·WHY·HOW·생각 &amp; 투자에 적용할 점, 고른 신문 쪽)과 작성·수정 시각</td></tr>
<tr><th>목적</th><td>이용자 확인(본인 계정 식별), 서비스 이용 권한·기한 관리(승인 여부와 이용 기한 확인), 부정 이용 방지,
챌린지 운영(참여 기록·진행도 확인, 같은 기수 참가자 간 글 공유, 완수 시 이용 권한 부여)</td></tr>
<tr><th>운영자가 부여하는 정보</th><td><b>승인 상태</b>와 <b>이용 기한</b>(운영자가 정한 경우), 챌린지 참가 여부·<b>기수</b>·챌린지 기간·빠진 날 인정 기록은 이용자가 입력하는 것이 아니라 운영자가 계정에 기록하는 정보이며, 가입자 관리 화면에서 운영자만 볼 수 있습니다.</td></tr>
<tr><th>자동 생성 정보</th><td>웹서버 <b>접속 기록</b>(접속 IP 주소, 접속 시각, 요청한 주소)이 서비스 이용 중 자동으로 남습니다. 목적은 안정적 운영과 부정 이용 방지입니다.</td></tr>
<tr><th>닉네임·글 공개 범위</th><td>닉네임은 본인 화면과 가입자 관리 화면(운영자 전용)에 표시됩니다. 언제든 내 정보 화면에서 바꿀 수 있습니다.
<b>챌린지 참가자</b>의 닉네임과 작성한 챌린지 글은 <b>같은 기수 참가자와 운영자</b>에게 공개됩니다(그날은 자기 글을 저장한 참가자에게만 열리고, 지난 날의 글은 같은 기수 참가자가 읽을 수 있습니다). 그 밖의 이용자에게는 공개되지 않습니다.</td></tr>
<tr><th>수집하지 않는 것</th><td>실명, 이메일, 전화번호, 주소, 생년월일, 성별, 프로필 사진, 비밀번호는 <b>수집하지 않습니다.</b> 구글·카카오에는 이름·이메일·프로필 정보를 요청하지 않으며 저장하지도 않습니다. 닉네임에는 실명·전화번호·이메일을 쓰지 않도록 안내하고, 전화번호나 이메일처럼 보이는 값은 입력할 수 없게 막습니다.</td></tr>
</table>

<h2>2. 보유 및 이용 기간</h2>
<p>탈퇴하거나 정보 삭제를 요청할 때까지 보유하며, 탈퇴 시 <b>지체 없이(즉시) 모두 삭제</b>합니다. 서비스를 종료하는 경우에도 지체 없이 파기합니다. 웹서버 접속 기록은 약 %(logdays)s일 보관한 뒤 자동으로 삭제됩니다(탈퇴해도 이 기간 동안은 서버 기록에 남을 수 있습니다).</p>

<h2>3. 제3자 제공 및 처리 위탁</h2>
<p>이용자의 개인정보를 제3자에게 제공하거나 처리를 위탁하지 않습니다. 챌린지의 <b>모르는 용어 뜻 찾기</b>를 누르면 입력한 <b>용어 글자만</b>(닉네임·작성한 글·계정 정보는 빼고) 운영자의 AI 서비스(OpenAI ChatGPT)에 보내 설명을 받으며, 받은 설명은 다른 참가자도 같이 볼 수 있게 저장됩니다. 로그인 과정에서 구글 또는 카카오가 각 사의 정책에 따라 로그인 정보를 처리하며, 이는 서비스가 아닌 각 사의 처리입니다. 정보는 운영자가 관리하는 클라우드 서버에 저장됩니다.</p>

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


def consent_html(nick_value, nxt, error="", checks=()):
    ck = lambda name: " checked" if name in checks else ""        # 거부돼서 다시 보여 줄 때 이미 체크한 칸은 그대로 둔다
    err = '<p class="warn">%s</p>' % html.escape(error) if error else ""
    return """
<div class="card"><h1>가입</h1>
<p class="sub">닉네임을 정하고, 아래 내용을 확인한 뒤 동의해 주세요.</p>%(err)s
<form method="post" action="/gate/consent">
<input type="hidden" name="next" value="%(next)s">
<h2>닉네임 (필수)</h2>
<input class="txt" type="text" name="nickname" value="%(name)s" maxlength="20" required autocomplete="off" placeholder="예: 경제공부하는곰" aria-label="닉네임">
<p class="sub">2~20자, 한글·영문·숫자·공백과 _ - . 만 쓸 수 있어요. 이 이름이 화면에 표시되고 운영자에게 보여요. 챌린지 참가자라면 같은 기수 참가자에게도 보여요(그 밖의 이용자에게는 공개되지 않아요).
<b>실명·전화번호·이메일은 쓰지 마세요.</b> 나중에 내 정보 화면에서 바꿀 수 있어요.</p>
<h2>개인정보 수집·이용 동의 (필수)</h2>
<table>
<tr><th>수집 항목</th><td>소셜 로그인 고유 식별번호, 위에서 직접 입력한 닉네임, 화면 모드 설정(선택 시), (챌린지 참가자만) 직접 작성한 챌린지 글과 작성 시각 (구글·카카오의 이름·이메일은 받지 않아요)</td></tr>
<tr><th>이용 목적</th><td>이용자 확인, 서비스 이용 권한·기한 관리, 부정 이용 방지, 챌린지 운영(진행도·같은 기수 글 공유)</td></tr>
<tr><th>보유 기간</th><td>탈퇴 시까지 (탈퇴하면 즉시 삭제)</td></tr>
<tr><th>동의 거부 권리</th><td>동의하지 않을 수 있으며, 이 경우 서비스를 이용할 수 없습니다.</td></tr>
</table>
<label class="chk"><input type="checkbox" name="agree_privacy" value="1"%(c1)s><span><b>[필수]</b> 개인정보 수집·이용에 동의합니다. (<a href="/privacy" target="_blank">처리방침 보기</a>)</span></label>
<label class="chk"><input type="checkbox" name="agree_age" value="1"%(c2)s><span><b>[필수]</b> 만 14세 이상입니다.</span></label>
<label class="chk"><input type="checkbox" name="agree_notice" value="1"%(c3)s><span><b>[필수]</b> 이 서비스의 기사·뉴스레터 내용은 <b>개인 학습용</b>이며, 저작권이 원 저작자에게 있어 <b>복사·재배포하지 않겠습니다.</b></span></label>
<button class="btn primary" type="submit">동의하고 시작하기</button>
</form></div>
<div class="foot"><a href="/gate/logout">동의하지 않고 로그아웃</a></div>""" % {
        "name": html.escape((nick_value or "")[:40], quote=True), "next": html.escape(nxt, quote=True), "err": err,
        "c1": ck("agree_privacy"), "c2": ck("agree_age"), "c3": ck("agree_notice")}


def login_html(nxt, c):
    q = "?next=" + urllib.parse.quote(nxt)
    btns = ""
    if c["google"]:
        btns += '<a class="btn google" href="/gate/google/start%s">🔵 구글로 계속하기</a>' % q
    if c["kakao"]:
        btns += '<a class="btn kakao" href="/gate/kakao/start%s">💬 카카오로 계속하기</a>' % q
    if nxt.startswith("/challenge"):           # 🔥 찰스 챌린지 전용 입구
        return """
<div class="card"><h1>🔥 찰스 챌린지</h1>
<p>평일마다 종이신문 기사 하나를 골라 <b>WHAT · WHY · HOW · 생각</b>을 쓰는 챌린지예요.</p>
<p class="sub">로그인·가입을 하면 <b>운영자가 찰스로 승인한 뒤</b>에 이용할 수 있어요. 승인 전에는 다른 화면도 이용할 수 없어요.</p>%s
<p class="sub">로그인하면 <a href="/privacy">개인정보 처리방침</a>을 확인한 것으로 보며, 다음 화면에서 동의를 받습니다. 이메일은 수집하지 않아요.</p>
</div>""" % btns
    note = ("가입 후 관리자가 승인하면 이용할 수 있어요." if c["approval"] == "manual"
            else "로그인하고 개인정보 처리 동의를 하면 바로 이용할 수 있어요.")
    return """
<div class="card"><h1>📚 경제 공부 · 📰 신문 요약</h1>
<p class="sub">로그인한 분만 볼 수 있어요. %s</p>%s
<p class="sub">로그인하면 <a href="/privacy">개인정보 처리방침</a>을 확인한 것으로 보며, 다음 화면에서 동의를 받습니다. 이메일은 수집하지 않아요.</p>
</div>""" % (html.escape(note), btns)


_IP_MSG = {"bad": "비밀번호가 맞지 않아요.", "locked": "실패가 많아 잠시 잠겼어요. 15분 뒤에 다시 시도해 주세요.",
           "off": "IP 접속이 꺼져 있어요. 서버 .env 의 GATE_IP_ADMIN_PASSWORD(12자 이상)를 설정해야 해요."}


def ip_login_html(request, nxt, m=""):
    plain = not (request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https")
    warn = ('<p class="warn">⚠️ 이 연결은 암호화되지 않았어요(http). 비밀번호가 그대로 오갈 수 있으니 믿을 수 있는 네트워크에서만 쓰세요.</p>'
            if plain else "")
    msg = ('<p class="warn">%s</p>' % html.escape(_IP_MSG[m])) if m in _IP_MSG else ""
    return ('<div class="card"><h1>🔑 관리자 로그인 (IP 접속)</h1>'
            '<p class="sub">서버 IP 주소로 들어온 경우에는 관리자 비밀번호로만 입장할 수 있어요. 일반 이용자는 도메인 주소로 들어와 구글/카카오로 로그인해 주세요.</p>'
            '%s%s<form method="post" action="/gate/ip-login"><input type="hidden" name="next" value="%s">'
            '<input class="txt" type="password" name="password" autocomplete="current-password" required autofocus aria-label="관리자 비밀번호" placeholder="관리자 비밀번호">'
            '<button class="btn primary" type="submit">입장</button></form>'
            '<p class="sub">입장하면 12시간 동안 유지되고, 그 뒤엔 자동으로 로그아웃돼요.</p></div>') % (msg, warn, html.escape(nxt, quote=True)) + _foot()


def who_html(request=None):
    """화면 맨 위 탭 오른쪽에 '길동 님 · 구글' 처럼 지금 어느 계정으로 들어왔는지 보여 준다(누르면 내 정보).
    잠금이 꺼져 있거나 로그인 정보가 없으면(예: 서버 내부 PDF 만들기) 빈 글."""
    if request is None or not cfg()["enabled"]:
        return ""
    if is_ip_host(request):
        if not ip_admin_ok(request):
            return ""
        return ('<a class="who" href="/gate/admin" title="서버 IP 로 들어온 관리자 모드(12시간)">🔑 IP 관리자 모드</a>'
                '<a class="adminlink" href="/gate/admin" title="가입자 보기·승인·차단">🛠 관리</a>'
                '<a class="logout" href="/gate/ip-logout">로그아웃</a>')
    try:
        u = session_user(request)
    except Exception:
        u = None
    if not u:
        return ""
    prov = {"google": "구글", "kakao": "카카오"}.get(u["provider"], u["provider"])
    dl = days_left(u) if not is_admin(u) else None
    left = (" · 오늘까지" if dl == 0 else " · 기한 D-%d" % dl) if dl is not None and 0 <= dl <= 7 else ""     # 곧 끝나면 미리 알려 준다
    out = '<a class="who" href="/gate/account" title="내 정보">%s 님 · %s%s</a>' % (html.escape(disp(u)), html.escape(prov), left)
    if is_admin(u):
        out += '<a class="adminlink" href="/gate/admin" title="가입자 보기·승인·차단">🛠 관리</a>'
    return out + '<a class="logout" href="/gate/logout">로그아웃</a>'


def _challenge_row(u):
    """내 정보 표의 '챌린지' 줄(참가자·완수자만)."""
    r = role_of(u)
    if r not in ("charles", "graduate"):
        return ""
    name = ""
    try:
        with _db() as con:
            c = con.execute("SELECT name FROM cohorts WHERE id=?", (u["cohort_id"],)).fetchone() if u["cohort_id"] else None
            name = c["name"] if c else ""
            n = con.execute("SELECT COUNT(*) FROM challenge_posts WHERE user_id=?", (u["id"],)).fetchone()[0]
    except Exception:
        n = 0
    return "<tr><th>챌린지</th><td>%s%s · 작성한 글 %d개</td></tr>" % (
        html.escape(name + " ") if name else "", "🎓 완수" if r == "graduate" else "참가 중", n)


def charles_apply_html(u, done=False):
    """이미 쓰고 있는 일반 이용자가 🔥 챌린지 주소로 들어왔을 때: 참가 신청 화면."""
    if applied_charles(u):
        body = ('<p>✅ <b>찰스 참가 신청을 했어요.</b> 운영자가 승인하면 이 화면이 챌린지로 바뀌어요.</p>'
                '<p class="sub">승인되면 새로고침해 주세요. 그동안 다른 화면은 지금처럼 쓸 수 있어요.</p>')
    else:
        body = ('<p>챌린지는 운영자가 <b>찰스</b>로 승인한 분만 참여할 수 있어요.</p>'
                '<p class="sub">찰스가 되면 챌린지 기간에는 📚 디그·🔥 챌린지 화면만 보이고, 기간 평일을 모두 채우면 모든 화면을 기한 없이 다시 쓸 수 있어요.</p>'
                '<form method="post" action="/gate/charles/apply"><button class="btn primary" type="submit">🔥 찰스 참가 신청</button></form>')
    return ('<div class="card"><h1>🔥 찰스 챌린지</h1>%s<p><a href="/economy">📰 신문 요약으로 돌아가기</a></p></div>' % body) + _foot()


def footer_html(request=None):
    """/slack·/dig 맨 아래에 끼워 넣는 링크(처리방침은 항상 쉽게 찾을 수 있어야 한다). 잠금이 꺼져 있으면 빈 글."""
    if not cfg()["enabled"]:
        return ""
    if request is not None and is_ip_host(request):
        return '<footer class="sitefoot"><a href="/privacy">개인정보 처리방침</a> · <a href="/gate/ip-logout">로그아웃</a></footer>'
    return ('<footer class="sitefoot"><a href="/privacy">개인정보 처리방침</a> · <a href="/gate/account">내 정보·탈퇴</a>'
            ' · <a href="/gate/logout">로그아웃</a></footer>')


# ───────────────────────── 라우터·중간 문지기 ─────────────────────────
_ADMIN_MSG = {"approve": "승인했어요.", "block": "차단했어요.", "unblock": "차단을 풀고 승인했어요.", "term": "이용 기한을 바꿨어요.",
              "delete": "그 사람의 정보를 삭제했어요.", "admin": "관리자는 이 화면에서 바꿀 수 없어요.", "none": "그런 사용자가 없어요.",
              "baddate": "날짜를 확인해 주세요(오늘 이후, 10년 이내).", "badterm": "변경할 기한을 먼저 골라 주세요.", "badstate": "승인된 사람만 기한을 바꿀 수 있어요.",
              "cohort_add": "기수를 추가했어요.", "cohort_edit": "기수를 고쳤어요(그 기수 찰스들의 이용 기한도 종료일로 맞췄어요).",
              "cohort_del": "기수를 삭제했어요.", "cohort_busy": "소속된 사람이 있는 기수는 삭제할 수 없어요.",
              "cohort_bad": "기수 이름(1~20자)과 날짜(시작 ≤ 종료, 1년 이내)를 확인해 주세요.", "cohort_dup": "같은 이름의 기수가 이미 있어요.",
              "charles_on": "찰스로 지정했어요(디그·챌린지 탭만 보이고, 이용 기한은 기수 종료일).", "charles_off": "찰스에서 해제했어요(일반 사용자 화면).",
              "charles_nocohort": "찰스로 지정하려면 기수를 골라 주세요(기수가 없으면 위에서 먼저 추가).", "excuse": "그날을 인정했어요."}
_FILTERS = ("pending", "approved", "expired", "blocked", "apply", "charles", "graduate")
_TERM_OPTS = (("none", "무기한"), ("7", "7일"), ("30", "30일"), ("90", "90일"), ("365", "1년"), ("custom", "날짜 지정"))


def user_cat(u):
    """관리 화면 분류: blocked / pending / expired(승인됐지만 기한 지남) / approved."""
    if u["status"] == "blocked":
        return "blocked"
    if u["status"] != "approved":
        return "pending"
    return "expired" if is_expired(u) else "approved"


def _admin_btn(uid, action, label, cls, csrf, flt, confirm_text=""):
    oc = ' onsubmit="return confirm(\'%s\')"' % confirm_text if confirm_text else ""
    return ('<form method="post" action="/gate/admin/act" class="inl"%s><input type="hidden" name="uid" value="%d">'
            '<input type="hidden" name="action" value="%s"><input type="hidden" name="csrf" value="%s">'
            '<input type="hidden" name="f" value="%s"><button class="mini %s" type="submit">%s</button></form>'
            % (oc, uid, action, csrf, html.escape(flt, quote=True), cls, label))


def _term_form(uid, action, label, csrf, flt, placeholder=False):
    """기한을 고르고 누르는 버튼(승인 / 차단 해제 / 기한 변경). placeholder=True 면 '기한 선택…'이 먼저 보여
    실수로 무기한이 되는 것을 막는다(기한 변경에서 사용)."""
    opts = ('<option value="">기한 선택…</option>' if placeholder else "") + "".join(
        '<option value="%s"%s>%s</option>' % (v, " selected" if (v == "none" and not placeholder) else "", t) for v, t in _TERM_OPTS)
    return ('<form method="post" action="/gate/admin/act" class="inl"><input type="hidden" name="uid" value="%d">'
            '<input type="hidden" name="action" value="%s"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="f" value="%s">'
            '<select name="term" class="mini" onchange="this.form.until.style.display=this.value==\'custom\'?\'inline-block\':\'none\'">%s</select>'
            '<input type="date" name="until" class="mini" style="display:none"><button class="mini go" type="submit">%s</button></form>'
            % (uid, action, csrf, html.escape(flt, quote=True), opts, label))


def _hidden(csrf, flt, action, **kw):
    out = ('<input type="hidden" name="action" value="%s"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="f" value="%s">'
           % (action, csrf, html.escape(flt, quote=True)))
    return out + "".join('<input type="hidden" name="%s" value="%s">' % (k, html.escape(str(v), quote=True)) for k, v in kw.items())


def cohorts_html(csrf, flt):
    """관리 화면 '🔥 찰스 기수' 칸: 기수 추가·수정·삭제."""
    try:
        import challenge
        cs = challenge.list_cohorts()
        with _db() as con:
            members = {r[0]: (r[1], r[2]) for r in con.execute(
                "SELECT cohort_id, SUM(role='charles'), SUM(role='graduate') FROM users WHERE cohort_id IS NOT NULL GROUP BY cohort_id")}
    except Exception as e:
        return '<div class="note">챌린지 모듈을 불러오지 못했어요: %s</div>' % html.escape(repr(e))
    rows = ""
    for c in cs:
        n_ch, n_gr = members.get(c["id"], (0, 0))
        wd = len(challenge.weekdays(c["start_date"], c["end_date"]))
        rows += ('<tr><td><form method="post" action="/gate/admin/act" class="inl">%s'
                 '<input class="mini" name="name" value="%s" maxlength="20" style="width:70px">'
                 '<input class="mini" type="date" name="start" value="%s"> ~ <input class="mini" type="date" name="end" value="%s">'
                 '<button class="mini go" type="submit">수정</button></form></td><td>평일 %d일</td><td>참가 %d · 🎓 %d</td><td>%s</td></tr>'
                 % (_hidden(csrf, flt, "cohort_edit", cid=c["id"]), html.escape(c["name"], quote=True), c["start_date"], c["end_date"], wd,
                    n_ch or 0, n_gr or 0,
                    ('<form method="post" action="/gate/admin/act" class="inl" onsubmit="return confirm(\'이 기수를 삭제할까요?\')">%s'
                     '<button class="mini stop" type="submit">삭제</button></form>' % _hidden(csrf, flt, "cohort_del", cid=c["id"]))))
    if not rows:
        rows = '<tr><td colspan="4" class="sub">아직 기수가 없어요. 아래에서 추가하세요.</td></tr>'
    add = ('<form method="post" action="/gate/admin/act" class="inl">%s<input class="mini" name="name" placeholder="예: 1기" maxlength="20" style="width:80px" required>'
           '<input class="mini" type="date" name="start" required> ~ <input class="mini" type="date" name="end" required>'
           '<button class="mini go" type="submit">기수 추가</button></form>' % _hidden(csrf, flt, "cohort_add"))
    return ('<h2>🔥 찰스 기수 · 챌린지 기간</h2><div class="tablewrap"><table><tr><th>기수 · 기간</th><th>챌린지 날</th><th>사람</th><th></th></tr>%s</table></div>'
            '<p>%s</p><p class="sub">챌린지 날 = 기간 안의 평일(신문이 안 올라온 날은 자동으로 빠져요). 기간을 바꾸면 그 기수 찰스들의 이용 기한도 종료일로 같이 바뀌어요.</p>'
            % (rows, add))


def _charles_cell(u, csrf, flt, cohorts):
    """가입자 표의 '찰스' 칸: ☑ 찰스 + 기수 고르기 + 진행도(빠진 날 [인정])."""
    if u["is_admin"]:
        return '<span class="sub">관리자(🔥 챌린지 글쓰기 가능)</span>'
    r = role_of(u)
    opts = '<option value="">기수…</option>' + "".join('<option value="%d"%s>%s</option>' % (
        c["id"], " selected" if c["id"] == u["cohort_id"] else "", html.escape(c["name"])) for c in cohorts)
    form = ('<form method="post" action="/gate/admin/act" class="inl">%s<label class="mini"><input type="checkbox" name="on" value="1"%s> 찰스</label>'
            '<select name="cohort" class="mini">%s</select><button class="mini go" type="submit">저장</button></form>'
            % (_hidden(csrf, flt, "charles", uid=u["id"]), " checked" if r == "charles" else "", opts))
    info = ""
    if r in ("charles", "graduate"):
        try:
            import challenge
            p = challenge.progress(u)
        except Exception:
            p = None
        if r == "graduate":
            info = '<div>🎓 %s 완수</div>' % html.escape(p["cohort"]["name"] if p else "")
        elif p:
            info = '<div>%s · %d/%d일%s</div>' % (html.escape(p["cohort"]["name"]), p["done"], p["total"], (" · ✗%d" % len(p["missed"])) if p["missed"] else "")
            for day in p["missed"][:10]:
                info += ('<form method="post" action="/gate/admin/act" class="inl">%s<button class="mini" type="submit" title="이 날을 한 것으로 인정">%s 인정</button></form>'
                         % (_hidden(csrf, flt, "excuse", uid=u["id"], day=day), day[5:]))
    return form + info


def admin_html(me, rows, counts, flt, msg, d=""):
    c = cfg()
    csrf = _csrf(me["id"])
    try:
        import challenge
        cohorts = challenge.list_cohorts()
    except Exception:
        cohorts = []
    tabs = ""
    for key, label in (("", "전체"), ("pending", "승인 대기"), ("approved", "이용 가능"), ("expired", "기한 만료"), ("blocked", "차단"),
                       ("apply", "🙋 찰스 신청"), ("charles", "🔥 찰스"), ("graduate", "🎓 완수")):
        n = len(rows) if key == "" else counts.get(key, 0)
        tabs += '<a href="/gate/admin%s" class="%s">%s %d</a>' % (("?f=" + key) if key else "", "on" if key == flt else "", label, n)
    trs = ""
    for u in rows:
        cat = user_cat(u)
        label, cls = {"approved": ("이용 가능", "b-ok"), "pending": ("승인 대기", "b-wait"), "expired": ("기한 만료", "b-block"), "blocked": ("차단", "b-block")}[cat]
        prov = {"google": "구글", "kakao": "카카오"}.get(u["provider"], u["provider"])
        consent = "✔" if u["consent_version"] == POLICY_VERSION else ("재동의 필요" if u["consent_version"] else "동의 전")
        dl = days_left(u)
        if u["is_admin"]:
            term_cell = "무기한"
            acts = '<span class="sub">관리자</span>'
        else:
            term_cell = expiry_text(u) + ((" (D-%d)" % dl) if (dl is not None and 0 <= dl <= 7 and cat == "approved") else "")
            acts = ""
            if cat == "pending":
                acts += _term_form(u["id"], "approve", "승인", csrf, flt)
            elif cat == "blocked":
                acts += _term_form(u["id"], "unblock", "차단 해제(승인)", csrf, flt)
            else:
                acts += _term_form(u["id"], "term", "기한 변경", csrf, flt, placeholder=True)
            btns = ""
            if cat != "blocked":
                btns += _admin_btn(u["id"], "block", "차단", "stop", csrf, flt, "이 사람을 차단할까요? 바로 이용할 수 없게 됩니다.")
            btns += _admin_btn(u["id"], "delete", "삭제", "stop", csrf, flt, "이 사람의 정보를 완전히 삭제할까요? 되돌릴 수 없습니다.")
            acts = '<div>%s</div><div>%s</div>' % (acts, btns)
        def _short(t):          # 2026-10-23T21:47:12 → 10-23 21:47 (표가 옆으로 길어지지 않게)
            return html.escape((t or "")[5:16].replace("T", " "))
        trs += ("<tr><td>%d</td><td><b>%s</b>%s<div class='sub'>%s</div></td><td><span class='%s'>%s</span></td><td>%s</td>"
                "<td class='sub'>가입 %s<br>접속 %s</td><td>%s</td><td class='act'>%s</td><td class='act'>%s</td></tr>"
                % (u["id"], html.escape(disp(u)), (" 🛠" if u["is_admin"] else "") + (" <span class='b-wait'>🙋 찰스 신청</span>" if applied_charles(u) and not is_charles(u) else ""), html.escape(prov), cls, label, html.escape(term_cell),
                   _short(u["created_at"]), _short(u["last_login_at"]), consent, acts, _charles_cell(u, csrf, flt, cohorts)))
    if not trs:
        trs = '<tr><td colspan="8" class="sub">해당하는 가입자가 없어요.</td></tr>'
    auto_days = _env("GATE_AUTO_DAYS", "0")
    note = ('지금은 <b>가입하면 바로 이용 가능</b>(auto)입니다%s. 승인제로 바꾸려면 서버 .env 의 <code>GATE_APPROVAL=manual</code> 후 재시작하세요.'
            % ((" · 새 가입자 체험 기간 %s일" % html.escape(auto_days)) if auto_days.isdigit() and int(auto_days) > 0 else "")
            if c["approval"] == "auto" else
            '지금은 <b>관리자 승인 후 이용</b>(manual)입니다. 새 가입자는 "승인 대기"로 들어와요. 승인할 때 이용 기한을 함께 정할 수 있어요.')
    extra = ""
    if msg in ("approve", "unblock", "term"):
        extra = " 이용 기한: %s." % ("무기한" if d == "none" else (html.escape(d) + "까지" if d else "무기한"))
    flash = '<div class="note">%s%s</div>' % (html.escape(_ADMIN_MSG[msg]), extra) if msg in _ADMIN_MSG else ""
    return """<div class="card"><h1>🛠 가입자 관리</h1>
<p class="sub">%s 님(관리자) · 이름과 로그인 방식·가입일 외의 개인정보는 저장하지 않아요.</p>%s
<div class="note">%s</div>
<div class="tabs">%s</div>
<div class="tablewrap"><table><tr><th>번호</th><th>이름·방식</th><th>상태</th><th>이용 기한</th><th>가입·접속</th><th>동의</th><th>처리</th><th>🔥 찰스 · 기수</th></tr>%s</table></div>
<p class="sub">기한은 그 날짜의 밤 12시까지 쓸 수 있어요(기한이 지나면 로그인해도 '이용 기간 종료'가 보이고, 관리자가 기한을 늘리면 바로 다시 쓸 수 있어요).
차단하면 쿠키가 남아 있어도 바로 이용할 수 없고, 삭제하면 정보와 동의 기록이 모두 지워져요. 관리자 지정·해제는 서버에서 <code>gate.py admin/unadmin 번호</code> 로만 할 수 있어요.</p>
%s
<p><a class="btn primary" href="/economy">📰 신문 요약</a><a class="btn primary" href="/challenge">🔥 챌린지</a></p></div>
<div class="foot"><a href="/gate/account">내 정보</a> · <a href="/gate/logout">로그아웃</a> · <a href="/privacy">개인정보 처리방침</a></div>""" % (
        html.escape(disp(me)), flash, note, tabs, trs, cohorts_html(csrf, flt))


def _is_gated(path):
    return (path in ("/economy", "/slack", "/dig", "/ai", "/market", "/challenge")
            or path.startswith(("/economy/", "/slack/", "/dig/", "/api/dig/", "/api/news/", "/ai/", "/api/ai/", "/market/", "/challenge/", "/api/challenge/")))


def _is_challenge_path(path):
    return path == "/challenge" or path.startswith(("/challenge/", "/api/challenge/"))


def _charles_ok(path):
    """찰스가 쓸 수 있는 곳: 디그 + 챌린지."""
    return path == "/dig" or path.startswith(("/dig/", "/api/dig/")) or _is_challenge_path(path)


def _is_api(path):
    return path.startswith(("/api/", "/economy/", "/slack/"))


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
    api = _is_api(path)
    nxt = urllib.parse.quote(safe_next(path + (("?" + request.url.query) if request.url.query else ""), "/economy"))
    if is_ip_host(request):                              # 서버 IP 로 들어온 경우: 관리자 비밀번호로만 입장
        if ip_admin_ok(request):
            return None
        if not ip_enabled():
            return JSONResponse({"ok": False, "reason": "ip_off"}, status_code=403) if api else _page(
                "IP 접속 꺼짐", '<div class="card"><h1>IP 주소로는 접속할 수 없어요</h1><p class="sub">도메인 주소로 들어와 주세요.</p></div>' + _foot(), 403)
        return JSONResponse({"ok": False, "reason": "ip_login"}, status_code=401) if api else RedirectResponse("/gate/ip-login?next=" + nxt, 302)
    user = session_user(request)
    if not user:
        if not api and _is_challenge_path(path):
            return RedirectResponse("/gate/charles", 302)      # 챌린지 주소로 오면 챌린지 전용 입구(가입하면 찰스 승인 대기)
        return JSONResponse({"ok": False, "reason": "login"}, status_code=401) if api else RedirectResponse("/gate/login?next=" + nxt, 302)
    if user["status"] == "blocked":
        return JSONResponse({"ok": False, "reason": "blocked"}, status_code=403) if api else _page(
            "이용 제한", '<div class="card"><h1>이용이 제한되었어요</h1><p>문의: 운영자에게 연락해 주세요.</p></div>' + _foot(), 403)
    if user["consent_version"] != POLICY_VERSION or not user["nick_set"]:
        return JSONResponse({"ok": False, "reason": "consent"}, status_code=403) if api else RedirectResponse("/gate/consent?next=" + nxt, 302)
    if user["status"] != "approved":
        return JSONResponse({"ok": False, "reason": "pending"}, status_code=403) if api else RedirectResponse("/gate/pending", 302)
    if is_charles(user) and is_expired(user):
        # 마지막 날 신문이 없어서(휴간) 완수 판정이 다음 날로 미뤄진 경우: 기한 화면 전에 한 번 더 판정해 본다
        try:
            import challenge
            if challenge.maybe_graduate(user):
                user = get_user(user["id"])
        except Exception as e:
            print("[gate] 챌린지 완수 판정 실패: %r" % (e,))
    if is_expired(user):
        return JSONResponse({"ok": False, "reason": "expired"}, status_code=403) if api else _page("이용 기간 종료", expired_html(user), 403)
    if _is_challenge_path(path) and not can_challenge(user):
        return JSONResponse({"ok": False, "reason": "not_charles"}, status_code=403) if api else _page("찰스 챌린지", charles_apply_html(user))
    if is_charles(user) and not _charles_ok(path):          # 찰스는 디그·챌린지만(주소를 직접 쳐도)
        return JSONResponse({"ok": False, "reason": "charles"}, status_code=403) if api else RedirectResponse("/challenge", 302)
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
    if u and u["status"] == "approved" and not is_expired(u):
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
        if cfg()["enabled"] and is_ip_host(request) and request.url.path.startswith("/gate/") \
                and request.url.path not in ("/gate/ip-login", "/gate/ip-logout", "/gate/admin", "/gate/admin/act", "/gate/privacy"):
            # IP 접속에서는 구글/카카오 로그인·가입·내 정보가 의미 없다 → 관리자 비밀번호 화면으로
            if request.method in ("GET", "HEAD"):
                return RedirectResponse("/gate/ip-login", 302)
            return JSONResponse({"ok": False, "reason": "ip"}, status_code=403)
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

    @r.get("/gate/ip-login")
    def ip_login_page(request: Request, next: str = "", m: str = ""):
        if not cfg()["enabled"]:
            return _off()
        if not is_ip_host(request):
            return _nope()                                # 도메인에서는 이 화면이 없는 것처럼
        nxt = safe_next(next)
        if ip_admin_ok(request):
            return RedirectResponse(nxt, 302)
        return _page("관리자 로그인", ip_login_html(request, nxt, m))

    @r.post("/gate/ip-login")
    async def ip_login_post(request: Request):
        import asyncio
        if not cfg()["enabled"]:
            return _off()
        if not is_ip_host(request):
            return _nope()
        f = _form(await request.body())
        nxt = safe_next(f.get("next", ""))
        key = _client_key(request)
        if not ip_enabled():
            return RedirectResponse("/gate/ip-login?m=off", 303)
        if ip_lock_left(key):
            return RedirectResponse("/gate/ip-login?m=locked&next=" + urllib.parse.quote(nxt), 303)
        good = hmac.compare_digest(f.get("password", "").encode(), ip_password().encode())
        ip_note(key, good)
        if not good:
            print("[gate] ⚠️ IP 관리자 로그인 실패 (접속자 %s)" % key)
            await asyncio.sleep(1)                         # 연달아 시도하는 속도를 늦춘다
            return RedirectResponse("/gate/ip-login?m=bad&next=" + urllib.parse.quote(nxt), 303)
        print("[gate] IP 관리자 로그인 성공 (접속자 %s)" % key)
        resp = RedirectResponse(nxt, 303)
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"
        resp.set_cookie(COOKIE_IPADM, _sign({"k": "ipadm", "v": _ipadm_ver()}, IPADM_HOURS * 3600),
                        max_age=IPADM_HOURS * 3600, httponly=True, secure=https, samesite="strict", path="/")
        return resp

    @r.get("/gate/ip-logout")
    def ip_logout():
        resp = RedirectResponse("/gate/ip-login", 302)
        resp.delete_cookie(COOKIE_IPADM, path="/")
        return resp

    @r.get("/gate/login")
    def login(request: Request, next: str = ""):
        c = cfg()
        if not c["enabled"]:
            return _off()
        nxt = safe_next(next)
        u = session_user(request)
        if u and u["consent_version"] == POLICY_VERSION and u["nick_set"] and u["status"] == "approved":
            return _page("이용 기간 종료", expired_html(u), 403) if is_expired(u) else RedirectResponse(nxt, 302)
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
            # 이미 로그인된 사람이 '뒤로 가기'·앱 복원 등으로 옛 콜백 주소를 다시 연 경우 → 오류 대신 그대로 들여보낸다.
            # (이번 code 는 쓰지 않고 기존 로그인 쿠키만 확인하므로 보안 확인을 건너뛰는 것이 아니다. 승인·기한은 도착한 화면이 다시 검사)
            u = session_user(request)
            if u:
                nxt = safe_next((st or {}).get("n"))
                dest = nxt if (u["consent_version"] == POLICY_VERSION and u["nick_set"]) else "/gate/consent?next=" + urllib.parse.quote(nxt)
                resp = RedirectResponse(dest, 302)
                resp.delete_cookie(COOKIE_STATE, path="/")
                return resp
            # 로그인도 안 돼 있고 시작 기록(상태 쿠키)도 없는 옛 주소 → 겁주는 오류 대신 로그인 화면으로
            if not st and not error:
                return RedirectResponse("/gate/login", 302)
            return _page("로그인 실패", '<div class="card"><h1>로그인하지 못했어요</h1><p>보안 확인에 실패했거나 로그인을 취소하셨어요. 다시 시도해 주세요.</p>'
                         '<a class="btn primary" href="/gate/login">다시 로그인</a></div>' + _foot(), 400)
        try:
            uid = identity_from_code(provider, code)
        except Exception as e:
            print("[gate] %s 로그인 실패: %s: %s" % (provider, type(e).__name__, e))
            return _page("로그인 실패", '<div class="card"><h1>로그인 서버와 연결하지 못했어요</h1><p>잠시 후 다시 시도해 주세요.</p>'
                         '<a class="btn primary" href="/gate/login">다시 로그인</a></div>' + _foot(), 502)
        nxt = safe_next(st.get("n"))
        user = upsert_login(provider, uid, apply="charles" if nxt.startswith("/challenge") else None)
        dest = nxt if (user["consent_version"] == POLICY_VERSION and user["nick_set"]) else "/gate/consent?next=" + urllib.parse.quote(nxt)
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
        return _page("가입", consent_html(u["nickname"] if u["nick_set"] else "", safe_next(next)))

    @r.post("/gate/consent")
    async def consent_post(request: Request):
        if not cfg()["enabled"]:
            return _off()
        u = session_user(request)
        f = _form(await request.body())
        nxt = safe_next(f.get("next"))
        if not u:
            return RedirectResponse("/gate/login?next=" + urllib.parse.quote(nxt), 302)
        typed = f.get("nickname", "")
        done = {k for k in ("agree_privacy", "agree_age", "agree_notice") if f.get(k)}       # 이미 체크한 칸
        if len(done) < 3:
            return _page("가입", consent_html(typed, nxt, "필수 항목 3개에 모두 동의해야 이용할 수 있어요.", done), 400)
        ok, res = validate_nickname(typed, admin=bool(u["is_admin"]), exclude_uid=u["id"])
        if not ok:
            return _page("가입", consent_html(typed, nxt, NICK_MSG[res], done), 400)
        try:
            record_consent(u["id"], ["privacy(필수)", "age14(필수)", "notice(필수)", "nickname"], res)
        except ValueError:                         # 동시에 같은 닉네임을 고른 드문 경우
            return _page("가입", consent_html(typed, nxt, NICK_MSG["dup"], done), 400)
        return RedirectResponse(nxt if u["status"] == "approved" else "/gate/pending", 303)

    @r.get("/gate/pending")
    def pending(request: Request):
        u = session_user(request)
        if not u:
            return RedirectResponse("/gate/login", 302)
        if u["status"] == "approved" and u["consent_version"] == POLICY_VERSION and u["nick_set"]:
            return RedirectResponse("/challenge" if can_challenge(u) and is_charles(u) else "/economy", 302)
        if applied_charles(u):
            return _page("찰스 승인 대기", '<div class="card"><h1>🔥 찰스 승인을 기다리고 있어요</h1><p>%s 님, 가입은 끝났어요. 운영자가 <b>찰스</b>로 승인하면 챌린지를 시작할 수 있어요.</p>'
                         '<p class="sub">승인되면 이 화면을 새로고침하세요(챌린지 화면으로 바로 넘어가요).</p></div><div class="foot"><a href="/gate/logout">로그아웃</a> · <a href="/privacy">처리방침</a></div>'
                         % html.escape(disp(u)))
        return _page("승인 대기", '<div class="card"><h1>⏳ 승인을 기다리고 있어요</h1><p>%s 님, 가입은 끝났고 운영자가 승인하면 이용할 수 있어요.</p>'
                     '<p class="sub">승인되면 이 화면을 새로고침하세요.</p></div><div class="foot"><a href="/gate/logout">로그아웃</a> · <a href="/privacy">처리방침</a></div>'
                     % html.escape(disp(u)))

    @r.get("/gate/charles")
    def charles_entry(request: Request):
        """🔥 찰스 챌린지 전용 입구. 여기로 가입하면 찰스 승인 대기(일반 화면도 승인 전엔 못 씀)."""
        if not cfg()["enabled"]:
            return _off()
        u = session_user(request)
        if not u:
            return _page("찰스 챌린지", login_html("/challenge", cfg()) + _foot())
        return RedirectResponse("/challenge", 302)          # 로그인돼 있으면 문지기가 상태에 맞게(동의·대기·신청·챌린지) 보낸다

    @r.post("/gate/charles/apply")
    def charles_apply(request: Request):
        u = session_user(request)
        if not u:
            return RedirectResponse("/gate/charles", 303)
        if not is_charles(u) and not is_admin(u):
            set_apply(u["id"], "charles")
            print("[gate] 🔥 찰스 참가 신청: 회원 %d" % u["id"])
        return RedirectResponse("/challenge", 303)

    @r.get("/gate/account")
    def account(request: Request, m: str = ""):
        if not cfg()["enabled"]:
            return _off()
        u = session_user(request)
        if not u:
            return RedirectResponse("/gate/login?next=/economy", 302)
        note = ('<p class="note">닉네임을 바꿨어요.</p>' if m == "nick_ok" else
                ('<p class="warn">%s</p>' % html.escape(NICK_MSG[m])) if m in NICK_MSG else "")
        prov = {"google": "구글", "kakao": "카카오"}.get(u["provider"], u["provider"])
        body = """<div class="card"><h1>내 정보</h1>
%s<table><tr><th>회원 번호</th><td>%d</td></tr><tr><th>닉네임</th><td>%s</td></tr><tr><th>로그인 방식</th><td>%s</td></tr>
<tr><th>가입 시각</th><td>%s</td></tr><tr><th>동의 시각</th><td>%s (처리방침 %s)</td></tr><tr><th>상태</th><td>%s</td></tr><tr><th>이용 기한</th><td>%s</td></tr><tr><th>화면 모드</th><td>%s</td></tr>%s</table>
<p class="sub">저장된 정보는 위가 전부예요(실명·이메일 등은 저장하지 않습니다). 챌린지 글은 🔥 챌린지 화면에서 볼 수 있어요.</p>
<h2>닉네임 바꾸기</h2>
<form method="post" action="/gate/nickname"><input class="txt" type="text" name="nickname" value="%s" maxlength="20" required autocomplete="off" aria-label="새 닉네임">
<button class="btn primary" type="submit">닉네임 변경</button></form>
<p>%s</p>
<h2>탈퇴 (정보 삭제)</h2><p class="sub">누르면 저장된 모든 정보와 동의 기록이 즉시 삭제되며 되돌릴 수 없어요.</p>
<form method="post" action="/gate/delete"><label class="chk"><input type="checkbox" name="confirm" value="1"><span>내 정보를 삭제하고 탈퇴합니다.</span></label>
<button class="btn danger" type="submit">탈퇴하고 정보 삭제</button></form></div>
<div class="foot"><a href="/gate/logout">로그아웃</a> · <a href="/privacy">개인정보 처리방침</a></div>""" % (
            note, u["id"], html.escape(disp(u)), html.escape(prov), html.escape(u["created_at"] or ""),
            html.escape(u["consent_at"] or "-"), html.escape(u["consent_version"] or "-"),
            html.escape({"approved": "이용 가능", "pending": "승인 대기", "blocked": "이용 제한"}.get(u["status"], u["status"])),
            html.escape("무기한(관리자)" if is_admin(u) else expiry_text(u)),
            html.escape({"light": "화이트", "dark": "다크", "auto": "자동(기기 설정)"}.get(u["theme"], "고르지 않음")),
            _challenge_row(u),
            "".join('<a class="btn primary" href="%s">%s</a>' % (h, t) for h, t in nav_links(u)),
            html.escape(u["nickname"] or "", quote=True))
        return _page("내 정보", body)

    @r.post("/gate/theme")
    async def theme_save(request: Request):
        """화면이 부르는 저장 주소: 본문 {"theme":"auto|light|dark"}. 로그인·승인된 본인 계정에만 저장."""
        u = session_user(request)
        if not u or u["status"] != "approved":
            return JSONResponse({"ok": False}, status_code=401)
        try:
            data = json.loads((await request.body() or b"{}")[:200])
            t = data.get("theme") if isinstance(data, dict) else None
        except Exception:
            t = None
        if not set_theme(u["id"], t):
            return JSONResponse({"ok": False, "reason": "bad theme"}, status_code=400)
        return JSONResponse({"ok": True, "theme": t})

    @r.post("/gate/nickname")
    async def nickname_change(request: Request):
        u = session_user(request)
        if not u:
            return RedirectResponse("/gate/login", 302)
        f = _form(await request.body())
        ok, res = validate_nickname(f.get("nickname", ""), admin=bool(u["is_admin"]), exclude_uid=u["id"])
        if not ok:
            return RedirectResponse("/gate/account?m=" + res, 303)
        try:
            set_nickname(u["id"], res)
        except ValueError:
            return RedirectResponse("/gate/account?m=dup", 303)
        return RedirectResponse("/gate/account?m=nick_ok", 303)

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

    def _nope():
        return _page("없는 페이지", '<div class="card"><h1>페이지를 찾을 수 없어요</h1></div>', 404)

    def _admin_user(request):
        if is_ip_host(request):                          # IP 접속은 비밀번호로 들어온 관리자 모드만
            return ip_pseudo_admin() if ip_admin_ok(request) else None
        u = session_user(request)
        return u if is_admin(u) else None            # 관리자가 아니면 '없는 페이지'처럼 보이게(존재 자체를 알리지 않음)

    @r.get("/gate/admin")
    def admin_page(request: Request, f: str = "", m: str = "", d: str = ""):
        if not cfg()["enabled"]:
            return _off()
        me = _admin_user(request)
        if not me:
            return _nope()
        flt = f if f in _FILTERS else ""
        with _db() as con:
            allrows = con.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
        counts = {}
        for u in allrows:
            counts[user_cat(u)] = counts.get(user_cat(u), 0) + 1
            if role_of(u) in ("charles", "graduate"):
                counts[role_of(u)] = counts.get(role_of(u), 0) + 1
            if applied_charles(u) and not is_charles(u):
                counts["apply"] = counts.get("apply", 0) + 1

        def _keep(u):
            if not flt:
                return True
            if flt == "apply":
                return applied_charles(u) and not is_charles(u)
            return role_of(u) == flt if flt in ("charles", "graduate") else user_cat(u) == flt
        rows = [u for u in allrows if _keep(u)]
        dd = d if (d == "none" or valid_date(d)) else ""        # 화면에 되돌려 보여 주는 값은 날짜 모양일 때만(임의 글자 반사 방지)
        return _page("가입자 관리", admin_html(me, rows, counts, flt, m, dd), wide=True)

    @r.post("/gate/admin/act")
    async def admin_act(request: Request):
        me = _admin_user(request)
        if not me:
            return _nope()
        f = _form(await request.body())
        if not hmac.compare_digest(f.get("csrf", ""), _csrf(me["id"])):
            return _page("요청 오류", '<div class="card"><h1>확인에 실패했어요</h1><p>관리 화면을 새로고침한 뒤 다시 눌러 주세요.</p>'
                         '<a class="btn primary" href="/gate/admin">관리 화면으로</a></div>', 400)
        flt = f.get("f") if f.get("f") in _FILTERS else ""
        action = f.get("action", "")
        if action.startswith("cohort_"):                 # 기수 추가·수정·삭제(사람이 아니라 기수가 대상)
            import challenge
            cid = f.get("cid", "")
            if action == "cohort_add":
                res, _ = challenge.add_cohort(f.get("name", ""), f.get("start", ""), f.get("end", ""))
                code = {"ok": "cohort_add", "dup": "cohort_dup"}.get(res, "cohort_bad")
            elif action == "cohort_edit" and cid.isdigit():
                res = challenge.edit_cohort(cid, f.get("name", ""), f.get("start", ""), f.get("end", ""))
                code = {"ok": "cohort_edit", "dup": "cohort_dup"}.get(res, "cohort_bad")
            elif action == "cohort_del" and cid.isdigit():
                code = "cohort_del" if challenge.delete_cohort(cid) == "ok" else "cohort_busy"
            else:
                code = "none"
            return RedirectResponse("/gate/admin?" + ("f=" + flt + "&" if flt else "") + "m=" + code, 303)
        t = get_user(f["uid"]) if f.get("uid", "").isdigit() else None
        exp_note = ""
        if not t:
            code = "none"
        elif t["is_admin"]:
            code = "admin"                               # 관리자끼리·자기 자신은 이 화면에서 못 건드림(실수로 잠그는 사고 방지)
        elif action in ("approve", "unblock", "term"):
            term = f.get("term", "")
            if action == "term" and not term:
                code = "badterm"                         # '기한 선택…' 그대로 눌렀을 때 — 실수로 무기한이 되지 않게
            elif action == "term" and t["status"] != "approved":
                code = "badstate"
            else:
                ok, exp = parse_term(term or "none", f.get("until", ""))
                if not ok:
                    code = "baddate"
                else:
                    set_access(t["id"], "approved" if action != "term" else t["status"], exp)
                    if action != "term":
                        set_apply(t["id"], None)             # 찰스 신청자를 일반으로 승인하면 신청 표시는 지운다
                    code, exp_note = action, exp or "none"
        elif action == "charles":
            import challenge
            res = challenge.set_charles(t["id"], bool(f.get("on")), f.get("cohort") if f.get("cohort", "").isdigit() else None)
            code = {"on": "charles_on", "off": "charles_off"}.get(res, "charles_nocohort")
        elif action == "excuse":
            import challenge
            code = "excuse" if challenge.excuse(t["id"], f.get("day", ""), me["id"]) else "none"
        elif action == "block":
            set_status(t["id"], "blocked")
            code = "block"
        elif action == "delete":
            delete_user(t["id"])
            code = "delete"
        else:
            code = "none"
        qs = ("f=" + flt + "&" if flt else "") + "m=" + code + (("&d=" + exp_note) if exp_note else "")
        return RedirectResponse("/gate/admin?" + qs, 303)

    @r.get("/gate/logout")
    def logout():
        resp = RedirectResponse("/gate/login", 302)
        resp.delete_cookie(COOKIE_SESSION, path="/")
        return resp

    app.include_router(r)
    try:                                                     # 🔥 찰스 챌린지 화면·주소(/challenge, /api/challenge/*)
        import challenge
        challenge.install(app)
    except Exception as e:
        print("[gate] ⚠️ 챌린지 모듈 로드 실패: %r" % (e,))


# ───────────────────────── 운영 명령 ─────────────────────────
def _print_users(rows):
    print("%-4s %-7s %-9s %-22s %-20s %-14s %-12s %s" % ("번호", "방식", "상태", "닉네임", "가입", "이용기한", "동의버전", "관리자"))
    for u in rows:
        print("%-4s %-7s %-9s %-22s %-20s %-14s %-12s %s" % (u["id"], u["provider"], u["status"], (u["nickname"] or "-")[:20], u["created_at"],
                                                            ("만료 " + u["expires_at"][:10]) if is_expired(u) else ((u["expires_at"] or "")[:10] or "무기한"),
                                                            u["consent_version"] or "-", "★" if u["is_admin"] else ""))
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
        pw = ip_password()
        print("[%s] GATE_IP_ADMIN_PASSWORD   (서버 IP 로 접속할 때 쓰는 관리자 비밀번호, %d자 이상) — 지금 %s" % (
            ok(len(pw) >= IPADM_MIN_PW), IPADM_MIN_PW, ("설정됨(%d자)" % len(pw)) if pw else "없음 → IP 접속은 막혀 있음"))
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
        if cmd in ("approve", "unblock") and len(argv) > 2:          # 기한: 일수 | YYYY-MM-DD | none
            ok, exp = parse_term(argv[2])
            if not ok:
                print("기한을 확인해 주세요: 일수(예 30) / 날짜(예 2026-12-31, 오늘 이후·10년 이내) / none")
                return 2
            n = set_access(uid, "approved", exp)
            print(("처리했어요: %d → approved (기한 %s)" % (uid, exp or "무기한")) if n else "그런 번호가 없어요: %d" % uid)
            return 0 if n else 1
        n = set_status(uid, "blocked" if cmd == "block" else "approved")
        print(("처리했어요: %d → %s" % (uid, "blocked" if cmd == "block" else "approved")) if n else "그런 번호가 없어요: %d" % uid)
        return 0 if n else 1
    if cmd in ("admin", "unadmin") and len(argv) > 1 and argv[1].isdigit():
        n = set_admin(int(argv[1]), cmd == "admin")
        print(("%s: %s 번" % ("관리자로 지정했어요" if cmd == "admin" else "관리자에서 뺐어요", argv[1])) if n else "그런 번호가 없어요: %s" % argv[1])
        return 0 if n else 1
    print(__doc__.split("운영 명령:")[-1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
