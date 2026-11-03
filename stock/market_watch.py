"""관리자 공용 관심종목. 웹 팝업 전용이며 기존 Slack/Telegram 감시목록은 변경하지 않는다."""
import hmac
import math
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

MAX_STOCKS = 20
TTL = 60
_cache = {}
_lock = threading.Lock()
_refreshing = False


@contextmanager
def _db():
    path = os.path.expanduser(os.getenv("MARKET_WATCH_DB", "~/.openclaw/secret/gate/market_watch.sqlite"))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS market_watch (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL, created_at TEXT NOT NULL)""")
    try:
        with con:
            yield con
    finally:
        con.close()


def items():
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM market_watch ORDER BY id")]


def validate(symbol, name):
    if not isinstance(symbol, str) or not isinstance(name, str):
        raise ValueError("종목코드와 이름을 입력해 주세요.")
    symbol, name = symbol.strip().upper(), name.strip()
    if not re.fullmatch(r"(?:[0-9]{6}|[A-Z]{1,6}(?:[.-][A-Z]{1,2})?)", symbol):
        raise ValueError("국내 6자리 종목코드 또는 미국 티커를 입력해 주세요.")
    if not 1 <= len(name) <= 40 or any(ord(c) < 32 for c in name):
        raise ValueError("종목 이름은 1~40자로 입력해 주세요.")
    return symbol, name


def quote(symbol):
    from market_data import _fetch_custom_quote
    q = _fetch_custom_quote(symbol)
    if not isinstance(q, dict):
        return None
    try:
        price, rate = float(q["current"]), float(q["change_rate"])
    except (ValueError, TypeError, KeyError):
        return None
    if not math.isfinite(price) or not math.isfinite(rate) or price <= 0 or rate <= -100:
        return None
    zone = ZoneInfo("Asia/Seoul" if symbol.isdigit() else "America/New_York")
    return {"current": price, "change_rate": rate, "source": str(q.get("source", "")),
            "currency": "KRW" if symbol.isdigit() else "USD",
            "market_date": datetime.now(zone).date().isoformat(),
            "observed_at": time.time()}


def add(symbol, name):
    symbol, name = validate(symbol, name)
    with _db() as con:
        if con.execute("SELECT 1 FROM market_watch WHERE symbol=?", (symbol,)).fetchone():
            raise ValueError("이미 추가된 종목입니다.")
        if con.execute("SELECT COUNT(*) FROM market_watch").fetchone()[0] >= MAX_STOCKS:
            raise ValueError("최대 20개 종목까지 추가할 수 있어요.")
    q = quote(symbol)
    if q is None:
        raise ValueError("시세를 확인하지 못했어요. 종목코드를 확인한 뒤 다시 시도해 주세요.")
    with _db() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT COUNT(*) FROM market_watch").fetchone()[0] >= MAX_STOCKS:
            raise ValueError("최대 20개 종목까지 추가할 수 있어요.")
        try:
            cur = con.execute("INSERT INTO market_watch(symbol,name,created_at) VALUES(?,?,?)",
                              (symbol, name, datetime.now(timezone.utc).isoformat()))
        except sqlite3.IntegrityError:
            raise ValueError("이미 추가된 종목입니다.") from None
        watch_id = cur.lastrowid
    with _lock:
        _cache[watch_id] = q
    return watch_id


def remove(watch_id):
    if type(watch_id) is not int or watch_id <= 0:
        raise ValueError("삭제할 종목을 다시 선택해 주세요.")
    with _db() as con:
        deleted = con.execute("DELETE FROM market_watch WHERE id=?", (watch_id,)).rowcount
    with _lock:
        _cache.pop(watch_id, None)
    return bool(deleted)


def _refresh(rows):
    global _refreshing
    def one(row):
        try:
            return row["id"], quote(row["symbol"])
        except Exception as exc:
            print("[market-watch] quote failed for %s: %s" % (row["symbol"], type(exc).__name__))
            return row["id"], None
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(one, rows))
        with _lock:
            for watch_id, q in results:
                # 실패 시 예전 값을 새 시세처럼 표시하지 않는다.
                _cache[watch_id] = q or {"unavailable": True, "observed_at": time.time()}
    finally:
        with _lock:
            _refreshing = False


def snapshot():
    global _refreshing
    rows = items()
    now = time.time()
    with _lock:
        due = [r for r in rows if now - _cache.get(r["id"], {}).get("observed_at", 0) >= TTL]
        if due and not _refreshing:
            _refreshing = True
            threading.Thread(target=_refresh, args=(due,), daemon=True).start()
        out = []
        for row in rows:
            q = _cache.get(row["id"])
            fresh = q and not q.get("unavailable") and now-q["observed_at"] < 180
            out.append(dict(row, quote=dict(q) if fresh else None))
    return out


def install(app, gate):
    def response(data, code=200):
        return JSONResponse(data, status_code=code, headers={"Cache-Control": "no-store"})

    def access(request, admin=False):
        if gate is None:
            return None, response({"ok": False, "message": "로그인 모듈을 사용할 수 없어요."}, 503)
        deny = gate._check(request)
        if deny is not None:
            return None, deny
        if gate.is_ip_host(request):
            user = gate.ip_pseudo_admin() if gate.ip_admin_ok(request) else None
        else:
            user = gate.session_user(request)
        if not user:
            return None, response({"ok": False, "message": "로그인이 필요해요."}, 401)
        if admin and not (gate.ip_admin_ok(request) or gate.is_admin(user)):
            return None, response({"ok": False, "message": "관리자만 종목을 변경할 수 있어요."}, 403)
        return user, None

    def admin_ok(user):
        return bool(user and (user["id"] == 0 or gate.is_admin(user)))

    @app.get("/market/api/watchlist")
    def watchlist(request: Request):
        user, deny = access(request)
        if deny is not None:
            return deny
        editable = admin_ok(user)
        return response({"ok": True, "items": items(), "can_manage": editable,
                         "csrf": gate._csrf(user["id"]) if editable else "",
                         "viewer_key": str(user["id"])})

    @app.post("/market/api/watchlist")
    async def change_watchlist(request: Request):
        user, deny = access(request, admin=True)
        if deny is not None:
            return deny
        if not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode("utf-8"), gate._csrf(user["id"]).encode("utf-8")):
            return response({"ok": False, "message": "화면을 새로고침한 뒤 다시 시도해 주세요."}, 403)
        if len(await request.body()) > 2048:
            return response({"ok": False, "message": "입력 내용이 너무 길어요."}, 413)
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError("입력 형식을 확인해 주세요.")
            if data.get("action") == "add":
                await run_in_threadpool(add, data.get("symbol"), data.get("name"))
            elif data.get("action") == "remove":
                await run_in_threadpool(remove, data.get("id"))
            else:
                raise ValueError("추가 또는 삭제를 선택해 주세요.")
        except ValueError as exc:
            return response({"ok": False, "message": str(exc)}, 400)
        return response({"ok": True, "items": items()})

    @app.get("/market/api/watchlist/quotes")
    def watch_quotes(request: Request):
        user, deny = access(request)
        if deny is not None:
            return deny
        return response({"ok": True, "items": snapshot(), "step": 2})
