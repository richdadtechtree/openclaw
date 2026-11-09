"""Administrator-only newspaper download and real gateway summary jobs."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Request
from fastapi.responses import JSONResponse
import gate
import news_files
import news_summary
import fcntl

KST = timezone(timedelta(hours=9))
HOME = os.path.expanduser("~")
COOLDOWN = 20                                                   # 끝난 뒤 이 초 안에 다시 누르면 무시(연타 방지)

STEPS = [("collect", "신문 다운로드"), ("sync", "웹에 연결"), ("summary", "기사 요약")]

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


# ── 단계 ─────────────────────────────────────────────────────────────────────
def _set(**kw):
    with _lock:
        _state.update(kw)
    persist()


def _step(key, status, note=""):
    with _lock:
        _state["steps"][key] = {"status": status, "note": note}
        if status == "run":
            _state["step"] = key
    persist()


def persist():
    with _lock:
        state = dict(_state, steps={k: dict(v) for k, v in _state["steps"].items()})
    news_summary.atomic_json(os.path.join(news_files.cache_root(), ".manual-job.json"), state)


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


def run_all(date, want_summary, download=True, lease=None):
    try:
        if download:
            _step("collect", "run")
            ok, note = run_collect()
            _step("collect", "ok" if ok else "fail", note)
            if not ok:
                return _set(ok=False, message=note)
        else:
            _step("collect", "skip", "이미 받은 파일로 요약해요.")
        if download or not news_files.load_index(date):
            _step("sync", "run")
            ok, note = run_sync(date)
            _step("sync", "ok" if ok else "fail", note)
            if not ok:
                return _set(ok=False, message=note)
        else:
            _step("sync", "ok", "준비된 지면을 사용해요.")
        if not want_summary:
            _step("summary", "skip", "다운로드만 완료했어요.")
            return _set(ok=True, message="신문을 다시 받아 웹에 연결했어요.")
        _step("summary", "run")
        note = news_summary.run(date, lambda note: _step("summary", "run", note))
        _step("summary", "ok", note)
        _set(ok=True, message=note)
    except Exception as e:                                       # 어떤 오류가 나도 '실행 중' 표시가 남지 않게
        current = snapshot().get("step")
        note = str(e) if isinstance(e, RuntimeError) else "처리 중 오류가 발생했어요. 다시 시도해 주세요."
        if current:
            _step(current, "fail", note)
        _set(ok=False, message=note)
    finally:
        # Release the process lease before advertising completion.
        if lease is not None:
            lease.close()
        _set(running=False, finished=time.time())


def start(date, want_summary, download=True):
    """시작하면 True, 이미 도는 중이거나 방금 끝났으면 False."""
    with _lock:
        if _state["running"] or (time.time() - _state["finished"] < COOLDOWN):
            return False
        os.makedirs(news_files.cache_root(), exist_ok=True)
        lease = open(os.path.join(news_files.cache_root(), ".manual-summary.lock"), "a")
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lease.close()
            return False
        _state.update(running=True, ok=None, step="", message="", date=date, started=time.time(), finished=0.0,
                      steps={k: {"status": "wait", "note": ""} for k, _ in STEPS}, tail="")
    try:
        persist()
        threading.Thread(target=run_all, args=(date, want_summary, download, lease), daemon=True).start()
    except Exception:
        lease.close()
        _set(running=False, ok=False, finished=time.time(), message="작업을 시작하지 못했어요.")
        raise
    return True


def snapshot():
    with _lock:
        s = dict(_state)
        s["steps"] = {k: dict(v) for k, v in _state["steps"].items()}
    s["labels"] = dict(STEPS)
    s["can_summary"] = news_summary.configured()
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
    @app.on_event("startup")
    def resume_status_and_recover_today():
        try:
            with open(os.path.join(news_files.cache_root(), ".manual-job.json"), encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("running"):
                saved.update(running=False, ok=False, finished=time.time(),
                             message="서버가 재시작되어 요약이 중단됐어요. '요약만 실행'을 누르면 완료한 지면부터 이어갑니다.")
            _set(**saved)
        except (OSError, ValueError, TypeError):
            pass
        # One explicitly requested recovery, not a new recurring schedule.
        # Expires at KST midnight; a durable claim prevents deploy/restart loops.
        date = "2026-11-09"
        if today_kst() != date or news_summary.messages(date):
            return
        if not news_summary.configured():
            _set(date=date, running=False, ok=False, finished=time.time(),
                 message="오늘 요약을 시작하지 못했어요. 서버의 요약 연결 설정(GATEWAY_TOKEN)을 확인해 주세요.")
            return
        marker = os.path.join(news_files.cache_root(), ".recovery-%s.started" % date)
        os.makedirs(news_files.cache_root(), exist_ok=True)
        try:
            with open(marker, "x", encoding="utf-8") as f:
                f.write("User requested today's summary once; see .manual-job.json for outcome.\n")
        except FileExistsError:
            return
        if not start(date, True, download=False):
            os.unlink(marker)

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
        if not isinstance(b, dict):
            return reply({"ok": False, "message": "요청 형식이 올바르지 않아요."}, 400)
        mode = b.get("mode", "all" if b.get("summary", True) else "download")
        if mode not in ("all", "download", "summary"):
            return reply({"ok": False, "message": "실행 종류가 올바르지 않아요."}, 400)
        want_summary = mode != "download"
        date = today_kst()                                        # 수집기는 '오늘' 신문만 찾는다
        if isinstance(b, dict) and b.get("date") and b.get("date") != date:
            return reply({"ok": False, "message": "오늘 신문만 다시 가져올 수 있어요."}, 400)
        started = start(date, want_summary, download=mode != "summary")
        return reply({"ok": True, "started": started, "state": snapshot()})
