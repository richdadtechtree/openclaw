import os
import threading
import time
from datetime import datetime

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from market_data import get_snapshot, load_ath_from_history, get_custom_stocks_snapshot
from trigger_engine import TriggerEngine
from summary import build_summary_text
from capture import capture_dashboard, capture_and_send

load_dotenv()

app = FastAPI(title="Stock Briefing Dashboard API")

# Ensure templates and static directories exist
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── 슬랙 데일리 다이제스트 (실시간 뷰어) ──────────────────────────────────────
# 슬랙 접속 불가 환경에서 '그날 시스템이 슬랙에 보낸 내용'을 웹으로 실시간 열람.
# 데이터 출처: slack_log.py 가 쌓는 ~/.openclaw/slack_logs/<날짜>.jsonl
import json as _json

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _KST = _ZoneInfo("Asia/Seoul")
except Exception:
    _KST = None

_SLACK_LOG_DIR = os.path.expanduser("~/.openclaw/slack_logs")


def _fetch_slack_history_api(date_str):
    import requests
    from datetime import datetime, timezone, timedelta
    try:
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            return []

        # 뷰어는 #gpt 채널 대화만 표시한다.
        gpt_ch = os.getenv("SLACK_GPT_CHANNEL", "C0BTHMT2M7X")
        if not gpt_ch:
            return []

        # Start and end of the day in KST (UTC+9)
        dt_start = datetime.strptime(date_str, "%Y-%m-%d")
        kst_tz = timezone(timedelta(hours=9))
        dt_start_kst = datetime(dt_start.year, dt_start.month, dt_start.day, tzinfo=kst_tz)
        ts_start = dt_start_kst.timestamp()
        ts_end = ts_start + 24 * 3600

        headers = {"Authorization": f"Bearer {token}"}

        all_messages = []
        params = {
            "channel": gpt_ch,
            "oldest": str(ts_start),
            "latest": str(ts_end),
            "limit": 200
        }
        res = requests.get("https://slack.com/api/conversations.history", headers=headers, params=params, timeout=15).json()
        if res.get("ok"):
            for msg in reversed(res.get("messages", [])):
                ts_val = float(msg.get("ts", 0))
                dt = datetime.fromtimestamp(ts_val, kst_tz)
                ts_iso = dt.isoformat(timespec="seconds")
                text = msg.get("text", "")

                bot_id = msg.get("bot_id")
                source = "bot" if bot_id else "user"

                all_messages.append({
                    "ts": ts_iso,
                    "source": source,
                    "kind": "text",
                    "text": text,
                    "room": "gpt"
                })
        return all_messages
    except Exception as e:
        print(f"[Slack API History] Fetch failed: {e}")
        return []


def _read_slack_log(date):
    path = os.path.join(_SLACK_LOG_DIR, "%s.jsonl" % date)
    local_msgs = []

    gpt_ch = os.getenv("SLACK_GPT_CHANNEL", "C0BTHMT2M7X")

    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = _json.loads(line)
                except Exception:
                    continue

                # #gpt 채널 메시지만 표시. 다른 시스템 발신(신문/알림/브리핑)은 제외.
                if not gpt_ch or r.get("channel", "") != gpt_ch:
                    continue

                local_msgs.append({"ts": r.get("ts", ""), "source": r.get("source", "unknown"),
                             "kind": r.get("kind", "text"), "text": r.get("text", ""), "room": "gpt"})

    api_msgs = _fetch_slack_history_api(date)
    seen = set()
    merged = []
    
    for m in api_msgs:
        key = (m["ts"][:16], m["text"][:50])
        seen.add(key)
        merged.append(m)
        
    for m in local_msgs:
        key = (m["ts"][:16], m["text"][:50])
        if key not in seen:
            seen.add(key)
            merged.append(m)
            
    merged.sort(key=lambda m: m["ts"])
    return merged


@app.get("/slack", response_class=HTMLResponse)
def slack_view():
    """슬랙 데일리 다이제스트 실시간 뷰어 페이지."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slack_digest_live.html")
        with open(p, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except Exception as e:
        return HTMLResponse("<h1>slack 뷰어 로드 실패</h1><pre>%s</pre>" % e, status_code=500)


@app.get("/slack/data")
def slack_data(date: str = ""):
    """그날 슬랙 발신 로그 JSON. date 미지정 시 오늘(KST)."""
    if not date:
        now = _dt_now()
        date = now.strftime("%Y-%m-%d")
    return JSONResponse({"date": date, "messages": _read_slack_log(date)})


def _dt_now():
    return datetime.now(_KST) if _KST else datetime.now()


# ── 오늘 신문 원본(사진·PDF) 내려받기 ────────────────────────────────────────
# 파일 자체는 구글 드라이브에 있지만, 웹이 요청마다 드라이브를 부르면 느리고
# 인증이 끊기면 페이지가 멈춘다. 그래서 scripts/news_sync.py 가 하루 한 번
# 드라이브 → 로컬 캐시(~/.openclaw/news_cache/<날짜>/)로 받아두고,
# 여기서는 그 캐시만 읽어서 내려준다.
import subprocess as _subprocess
import sys as _sys
import threading as _threading

try:
    import news_files as _news
except Exception as _e:  # 이 모듈이 없어도 나머지 대시보드는 그대로 동작해야 한다
    _news = None
    print("[news] news_files 로드 실패: %s" % _e)

_news_refresh_lock = _threading.Lock()
_news_refresh_at = [0.0]        # 마지막 새로고침 시각(초). 연타 방지용.


def _news_sync_script():
    return os.path.expanduser(os.getenv("NEWS_SYNC_SCRIPT", "~/.openclaw/scripts/news_sync.py"))


def _run_news_sync(date):
    """드라이브에서 다시 받아오기(백그라운드 실행). 실패해도 웹은 멀쩡해야 한다."""
    script = _news_sync_script()
    if not os.path.isfile(script):
        print("[news] 동기화 스크립트 없음: %s" % script)
        return
    try:
        p = _subprocess.run([_sys.executable, script, date, "--quiet"],
                            capture_output=True, text=True, timeout=600)
        if p.returncode not in (0, 2):
            print("[news] 동기화 실패(rc=%s): %s" % (p.returncode, (p.stderr or "").strip()[:300]))
    except Exception as e:
        print("[news] 동기화 예외: %r" % e)


@app.get("/api/news/today")
def news_today(date: str = ""):
    """그날 신문 원본 목록(PDF 1개 + 사진 N장). date 미지정 시 오늘(KST)."""
    if _news is None:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "news_files 모듈 없음"})
    date = date or _news.today_kst()
    if not _news.valid_date(date):
        return JSONResponse(status_code=400, content={"ok": False, "reason": "날짜 형식은 YYYY-MM-DD"})
    return JSONResponse(_news.summary(date))


@app.get("/api/news/file")
def news_file(name: str, date: str = "", dl: int = 0):
    """신문 파일 1개. dl=1 이면 다운로드, 아니면 브라우저에서 바로 보기."""
    if _news is None:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "news_files 모듈 없음"})
    date = date or _news.today_kst()
    path = _news.resolve(date, name)
    if not path:
        return JSONResponse(status_code=404, content={"ok": False, "reason": "그런 파일이 없습니다"})
    mt = _news.media_type(name)
    if dl:
        # filename 을 주면 브라우저가 '저장'으로 처리한다(ASCII 이름이라 안전).
        base = os.path.basename(name)
        save_as = base if base.startswith(date) else "%s_%s" % (date, base)   # 2026-09-15.pdf 는 그대로
        return FileResponse(path, media_type=mt, filename=save_as)
    return FileResponse(path, media_type=mt)


@app.get("/api/news/thumb")
def news_thumb(name: str, date: str = ""):
    """사진 썸네일(작게 줄인 이미지). Pillow 가 없으면 원본을 그대로 준다."""
    if _news is None:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "news_files 모듈 없음"})
    date = date or _news.today_kst()
    path = _news.ensure_thumb(date, name)
    if not path:
        return JSONResponse(status_code=404, content={"ok": False, "reason": "그런 파일이 없습니다"})
    mt = "image/jpeg" if path.endswith(".jpg") else _news.media_type(name)
    return FileResponse(path, media_type=mt)


@app.get("/api/news/zip")
def news_zip(date: str = "", what: str = "photos"):
    """그날 사진을 한 번에 받는 ZIP. what=all 이면 PDF 도 함께."""
    if _news is None:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "news_files 모듈 없음"})
    date = date or _news.today_kst()
    what = "all" if what == "all" else "photos"
    path = _news.ensure_zip(date, what)
    if not path:
        return JSONResponse(status_code=404, content={"ok": False, "reason": "받을 파일이 없습니다"})
    name = "news-%s%s.zip" % (date, "" if what == "all" else "-photos")
    return FileResponse(path, media_type="application/zip", filename=name)


@app.post("/api/news/refresh")
def news_refresh(background_tasks: BackgroundTasks, date: str = ""):
    """지금 드라이브에서 다시 받아오기. 60초 안에 또 누르면 그냥 무시한다."""
    if _news is None:
        return JSONResponse(status_code=503, content={"ok": False, "reason": "news_files 모듈 없음"})
    date = date or _news.today_kst()
    if not _news.valid_date(date):
        return JSONResponse(status_code=400, content={"ok": False, "reason": "날짜 형식은 YYYY-MM-DD"})
    now = time.time()
    with _news_refresh_lock:
        if now - _news_refresh_at[0] < 60:
            return {"ok": True, "status": "skipped", "message": "방금 받아왔습니다. 잠시 후 다시 시도하세요."}
        _news_refresh_at[0] = now
    background_tasks.add_task(_run_news_sync, date)
    return {"ok": True, "status": "accepted", "date": date}



@app.on_event("startup")
def startup_event():
    # Load historical ATH values in a background thread
    threading.Thread(target=load_ath_from_history, daemon=True).start()


@app.get("/api/indices")
def get_indices():
    """
    코스피/코스닥/S&P500/TQQQ의 현재가, 등락률, 역대 최고가 대비 하락률 반환.
    국내지수·TQQQ는 한투 API 우선, 실패 시 yfinance 폴백.
    """
    data = get_snapshot(include_sparkline=True)
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
    }


@app.get("/api/alerts")
def get_alerts():
    """
    투자 타이밍 현황 반환 (하락 단계 진행률, 다음 트리거까지 남은 폭 등).
    읽기 전용 — 트리거 발동/알람 전송은 스케줄러(scheduler.py)가 담당.
    """
    snapshot = get_snapshot(include_sparkline=False)
    engine = TriggerEngine()
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": engine.status(snapshot),
    }


@app.get("/api/custom-stocks")
def get_custom_stocks():
    """
    관심 종목 및 ETF의 현재가, 전일대비 등락률, 오늘 알람 여부 반환.
    """
    custom_snapshot = get_custom_stocks_snapshot(use_cache=True)
    engine = TriggerEngine()
    data = engine.get_custom_stocks_status(custom_snapshot)
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
    }


@app.get("/api/summary")
def get_summary():
    """
    현재 시장·투자 타이밍 상황을 사람이 읽기 쉬운 글자로 요약해 반환.
    오픈클로(대화형 봇)가 불러서 그대로 전달하기 좋음.
    """
    text = build_summary_text()
    return {
        "status": "success",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text": text,
    }


@app.get("/api/screenshot")
def get_screenshot():
    """
    대시보드를 지금 즉시 캡처해 PNG 이미지로 반환 (전송하지 않음).
    오픈클로가 이 이미지를 받아 자기 봇으로 전달할 수 있음.
    """
    path = "static/briefing_screenshot.png"
    if capture_dashboard(path):
        return FileResponse(path, media_type="image/png", filename="market_briefing.png")
    return JSONResponse(status_code=503, content={"status": "error", "message": "capture failed"})


@app.post("/api/briefing/send")
def post_briefing_send(background_tasks: BackgroundTasks):
    """
    지금 즉시 캡처해서 브리핑 봇(봇 1)으로 텔레그램 전송을 예약.
    바로 응답을 돌려주고 전송은 백그라운드에서 진행.
    """
    background_tasks.add_task(capture_and_send)
    return {"status": "accepted", "message": "briefing capture & send started"}


# Version 2.6 - Stock Dashboard Modern UI with Country Flags & Slack Integration
@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """
    Serves the main HTML dashboard.
    """
    if os.path.exists("templates/index.html"):
        return FileResponse("templates/index.html")
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return HTMLResponse("<h1>Dashboard template loading...</h1>")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)

