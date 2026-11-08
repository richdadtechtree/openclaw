"""🔁 신문이 늦게 올라온 날 — 관리자가 버튼 하나로 '다시 가져오기 → 웹에 연결 → 요약 요청' 을 시키는 모듈 (2026-11-09 사용자 요청).

배경: 수집기(~/newspaper/scripts/run_daily.sh)는 05:00부터 5분마다 카페를 확인하다가 07:00 이 지나면 포기한다.
      신문 글이 7시 넘어 올라온 날은 사진이 서버에 없고, ChatGPT 아침 요약(오전 7시)도 사진 없이 나간다.
      그동안은 서버에 들어가 명령을 손으로 쳐야 했다 → 웹의 관리자 버튼으로 같은 일을 한다.

버튼이 하는 일 (순서대로, 앞이 실패하면 뒤는 하지 않는다):
  ① 가져오기  수집기를 **딱 한 번** 돌린다(`app/main.py`, run_daily.sh 가 한 번 시도하는 것과 같음. 시각과 상관없이 시도).
  ② 연결      scripts/news_sync.py --force 로 웹이 읽는 캐시에 연결(이 안에서 지면 글자 읽기도 시작됨).
  ③ 요약 요청 Slack #gpt 에 ChatGPT 앱을 멘션한 부탁 글을 올린다.
              ⚠️ 요약은 서버가 아니라 사용자의 ChatGPT 가 만든다 → 서버는 '부탁 글'만 올릴 수 있다.
              .env 의 NEWS_REDO_GPT_MENTION (예: <@U0123ABCD>) 이 없으면 이 단계는 건너뛰고 화면에 알려 준다.
              (ChatGPT 앱이 봇이 올린 멘션에 반응하는지는 Slack 설정에 달려 있어 서버에선 확인할 수 없음.)

관리자만(로그인 관리자 또는 서버 IP 관리자). 오늘(KST) 신문만 — 수집기는 '오늘' 글만 찾는다.
표준 라이브러리 + fastapi 만 쓴다(news_marks.py 와 같은 설치 방식).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
import gate

KST = timezone(timedelta(hours=9))
HOME = os.path.expanduser("~")
MENTION_RE = re.compile(r"^<@[UW][A-Z0-9]{2,20}>$")           # 슬랙 멘션 모양만 허용(그 밖의 글은 그대로 올리지 않는다)
COOLDOWN = 20                                                   # 끝난 뒤 이 초 안에 다시 누르면 무시(연타 방지)

STEPS = [("collect", "카페에서 다시 가져오기"), ("sync", "웹에 연결"), ("summary", "요약 요청")]

_lock = threading.Lock()
_state = {"running": False, "ok": None, "step": "", "message": "", "date": "", "started": 0.0, "finished": 0.0,
          "steps": {}, "tail": ""}


# ── 설정(환경변수) ─────────────────────────────────────────────────────────────
def newspaper_dir():
    return os.path.expanduser(os.getenv("NEWSPAPER_DIR", "~/newspaper"))


def sync_script():
    return os.path.expanduser(os.getenv("NEWS_SYNC_SCRIPT", "~/.openclaw/scripts/news_sync.py"))


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def collector_cmd():
    """run_daily.sh 와 같은 방식: 수집기 venv 파이썬으로 app/main.py, 화면 없는 서버면 xvfb-run 으로 감싼다."""
    d = newspaper_dir()
    py = os.path.join(d, ".venv", "bin", "python")
    if not os.path.isfile(py):
        py = sys.executable
    cmd = [py, os.path.join("app", "main.py")]
    if shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    return cmd, d


def mention():
    m = (os.getenv("NEWS_REDO_GPT_MENTION") or "").strip()
    return m if MENTION_RE.match(m) else ""


# ── 단계 ─────────────────────────────────────────────────────────────────────
def _set(**kw):
    with _lock:
        _state.update(kw)


def _step(key, status, note=""):
    with _lock:
        _state["steps"][key] = {"status": status, "note": note}
        if status == "run":
            _state["step"] = key


def _tail(text, n=6):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return "\n".join(lines[-n:])[:600]


def run_collect(timeout=900):
    cmd, cwd = collector_cmd()
    if not os.path.isdir(cwd):
        return False, "수집기 폴더가 없어요: %s" % cwd
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "수집기가 %d분 안에 끝나지 않았어요." % (timeout // 60)
    except Exception as e:                                      # 실행 파일 없음 등
        return False, "수집기를 실행하지 못했어요: %r" % (e,)
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    _set(tail=_tail(out))
    return p.returncode == 0, ("" if p.returncode == 0 else "카페에서 오늘 신문 글을 아직 못 찾았거나 받기에 실패했어요.")


def run_sync(date, timeout=600):
    script = sync_script()
    if not os.path.isfile(script):
        return False, "동기화 스크립트가 없어요: %s" % script
    try:
        p = subprocess.run([sys.executable, script, date, "--force", "--quiet"], capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return False, "웹에 연결하지 못했어요: %r" % (e,)
    if p.returncode == 0:
        return True, ""
    if p.returncode == 2:
        return False, "수집은 됐는데 웹이 읽을 신문 파일을 아직 못 찾았어요."
    _set(tail=_tail((p.stdout or "") + "\n" + (p.stderr or "")))
    return False, "웹에 연결하지 못했어요(rc=%s)." % p.returncode


def post_summary_request(date):
    """Slack #gpt 에 ChatGPT 앱을 멘션해 요약을 부탁한다. (ok, note) — 설정이 없으면 (None, 안내)."""
    m = mention()
    token = os.getenv("SLACK_BOT_TOKEN")
    channel = os.getenv("SLACK_GPT_CHANNEL", "C0BTHMT2M7X")
    if not m:
        return None, "NEWS_REDO_GPT_MENTION 이 없어 요약 요청은 건너뛰었어요. ChatGPT 에서 직접 요약을 돌려 주세요."
    if not token or not channel:
        return None, "슬랙 설정(SLACK_BOT_TOKEN)이 없어 요약 요청은 건너뛰었어요."
    text = ("%s 오늘(%s) 신문이 늦게 올라와 사진·PDF 를 다시 준비했어요. "
            "프로젝트 지침(chatgpt-newspaper-instructions.md)대로 오늘 신문 요약을 다시 만들어 이 채널에 보내 주세요."
            % (m, date))
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return False, "슬랙에 올리지 못했어요: %r" % (e,)
    if not res.get("ok"):
        return False, "슬랙이 거절했어요: %s" % res.get("error", "알 수 없음")
    return True, "#gpt 채널에 요약 부탁 글을 올렸어요."


def run_all(date, want_summary):
    try:
        _step("collect", "run")
        ok, note = run_collect()
        _step("collect", "ok" if ok else "fail", note)
        if not ok:
            return _set(ok=False, message=note)
        _step("sync", "run")
        ok, note = run_sync(date)
        _step("sync", "ok" if ok else "fail", note)
        if not ok:
            return _set(ok=False, message=note)
        if not want_summary:
            _step("summary", "skip", "요약 요청은 하지 않았어요.")
            return _set(ok=True, message="신문을 다시 받아 웹에 연결했어요.")
        _step("summary", "run")
        ok, note = post_summary_request(date)
        _step("summary", "ok" if ok else ("skip" if ok is None else "fail"), note)
        if ok is False:
            return _set(ok=False, message="신문은 다시 받았지만 " + note)
        _set(ok=True, message="신문을 다시 받았어요. " + note)
    except Exception as e:                                       # 어떤 오류가 나도 '실행 중' 표시가 남지 않게
        _set(ok=False, message="예상 못 한 오류: %r" % (e,))
    finally:
        _set(running=False, finished=time.time())


def start(date, want_summary):
    """시작하면 True, 이미 도는 중이거나 방금 끝났으면 False."""
    with _lock:
        if _state["running"] or (time.time() - _state["finished"] < COOLDOWN):
            return False
        _state.update(running=True, ok=None, step="", message="", date=date, started=time.time(), finished=0.0,
                      steps={k: {"status": "wait", "note": ""} for k, _ in STEPS}, tail="")
    threading.Thread(target=run_all, args=(date, want_summary), daemon=True).start()
    return True


def snapshot():
    with _lock:
        s = dict(_state)
        s["steps"] = {k: dict(v) for k, v in _state["steps"].items()}
    s["labels"] = dict(STEPS)
    s["can_summary"] = bool(mention() and os.getenv("SLACK_BOT_TOKEN"))
    return s


# ── 관리자 확인 + 라우트 ────────────────────────────────────────────────────────
def is_admin(request):
    """news_marks.owner 와 같은 기준: 로그인 관리자 또는 서버 IP 관리자."""
    if gate.is_ip_host(request):
        return gate.ip_admin_ok(request)
    u = gate.session_user(request)
    return bool(u and gate.is_admin(u))


def reply(data, code=200):
    return JSONResponse(data, status_code=code, headers={"Cache-Control": "no-store"})


def install(app):
    @app.get("/api/news/redo")
    def get_redo(request: Request):
        """진행 상태. 관리자가 아니면 403 → 화면은 버튼 자체를 안 보인다."""
        if not is_admin(request):
            return reply({"ok": False, "reason": "forbidden"}, 403)
        return reply({"ok": True, "state": snapshot()})

    @app.post("/api/news/redo")
    async def post_redo(request: Request):
        if not is_admin(request):
            return reply({"ok": False, "reason": "forbidden"}, 403)
        if request.headers.get("content-type", "").split(";")[0] != "application/json" or request.headers.get("sec-fetch-site") == "cross-site":
            return reply({"ok": False, "message": "허용되지 않은 요청입니다."}, 403)
        try:
            b = await request.json()
        except Exception:
            b = {}
        want_summary = bool(b.get("summary", True)) if isinstance(b, dict) else True
        date = today_kst()                                        # 수집기는 '오늘' 신문만 찾는다
        if isinstance(b, dict) and b.get("date") and b.get("date") != date:
            return reply({"ok": False, "message": "오늘 신문만 다시 가져올 수 있어요."}, 400)
        started = start(date, want_summary)
        return reply({"ok": True, "started": started, "state": snapshot()})
