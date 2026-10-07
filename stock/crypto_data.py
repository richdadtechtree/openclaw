"""
비트코인 시세 수집 모듈 (대시보드 '₿ 비트코인' 칸 전용)

- 주식 지수(market_data.get_snapshot)와 **완전히 분리**했다. 알람 스케줄러·투자 타이밍 계산은
  get_snapshot 을 쓰므로, 여기서 무슨 일이 생겨도 기존 지수/알람에는 영향이 없다.
- 전부 키 없이 쓰는 공개 API. 2026-10-06 서버 IP 에서 5곳 모두 정상 확인
  (scripts/test_btc_price.py — 응답 21~122ms, 같은 화폐끼리 차이 0.03% 이내).

  원화 가격 : 업비트(1순위) → 빗썸(예비)
  달러 가격 : 바이낸스 BTCUSDT(1순위) → 코인베이스 BTC-USD(예비)
  환율      : fx_data(네이버→두나무→ECB, 환율 칸과 같은 값) → 실패 시 업비트 USDT 원화가(대용)
  30일 추이 : 업비트 일봉 종가 (10년 그래프가 아직 준비 안 됐을 때만 대신 쓴다)
  10년 추이 : 빗썸 일봉 전체(2013~, 한 번에 받음) → 실패 시 업비트 일봉(2017-09~, 있는 만큼만).
              10년 동안 수백 배 올라 보통 눈금이면 앞쪽이 바닥에 붙는다 → 로그 눈금(같은 높이 = 같은 '배수').
              첫 받기는 뒤에서(화면 안 막음), 6시간 캐시.
  역대 최고가: 업비트 일봉 '고가'를 상장(2017-09)부터 한 번 전부 훑어 최고값을 찾고 파일(.btc_ath.json)에
              저장 → 이후엔 '오늘 고가·52주 최고가'와만 비교해 더 높으면 갱신(매번 수천 일을 다시 받지 않음).
              첫 훑기가 끝나기 전·실패 시엔 역대 최고가를 표시하지 않고 52주 최고가만 보인다(지어내지 않음).

- 등락률 기준이 거래소마다 다르다(업비트=매일 오전 9시 대비, 빗썸=최근 24시간 대비).
  그래서 응답에 basis(기준)를 함께 담아 화면에 그대로 적는다.

직접 점검(서버, stock venv):  ~/stock/stock/venv/bin/python crypto_data.py
"""
import json
import math
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

import requests

TIMEOUT = 5          # 초. 대시보드가 20초마다 부르므로 오래 기다리지 않는다.
QUOTE_TTL = 15       # 초. 시세 캐시(여러 사람이 동시에 열어도 거래소를 한 번만 부르게)
SPARK_TTL = 600      # 초. 30일 추이는 하루 한 점이라 10분 캐시면 충분
FX_TTL = 600         # 초. 환율도 자주 바뀌지 않는다

# 거래소들이 파이썬 기본 User-Agent 를 봇으로 막는 경우가 있어 브라우저처럼 보이게 한다.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}

_lock = threading.Lock()
_cache = {"quote": (0, None), "spark": (0, []), "fx": (0, None)}

# 역대 최고가(원화) 저장 파일 — 서버 실행 폴더(~/stock/stock)에 생긴다. 코드 동기화(rsync .py/.html)는 건드리지 않음.
ATH_FILE = os.getenv("BTC_ATH_FILE", ".btc_ath.json")
ATH_RESCAN_DAYS = 30      # 혹시 놓친 값이 있어도 한 달에 한 번은 처음부터 다시 훑어 바로잡는다
LONG_YEARS = 10
LONG_TTL = 6 * 3600       # 10년 추이 캐시(하루 한 점이라 자주 받을 필요 없음)
LONG_RETRY = 600          # 실패하면 10분 뒤에 다시 시도(매 요청마다 두드리지 않게)
LONG_POINTS = 200         # 그래프 점 개수(10년 ≈ 2~3주에 1점)
KST = timezone(timedelta(hours=9))
_long = {"ts": 0, "val": None, "loading": False, "failed": 0}
_ath_lock = threading.Lock()
_ath = {"loaded": False, "data": None, "scanning": False}


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ── 원화(KRW) ──────────────────────────────────────────────────────────────

def _krw_upbit():
    t = _get("https://api.upbit.com/v1/ticker?markets=KRW-BTC")[0]
    out = {
        "price": float(t["trade_price"]),
        "change_rate": float(t["signed_change_rate"]) * 100,   # 0.0123 → 1.23(%)
        "basis": "오전 9시 대비",
        "source": "Upbit",
        "high_today": float(t.get("high_price") or 0),        # 역대 최고가 갱신 비교용
        "today": str(t.get("trade_date_kst") or ""),          # 'YYYYMMDD'
    }
    # 업비트만 52주 최고가를 준다 → 지수 칸의 'ATH 대비 낙폭' 자리에 대신 쓴다.
    hi = t.get("highest_52_week_price")
    if hi:
        out["high_52w"] = float(hi)
        out["high_52w_date"] = t.get("highest_52_week_date")
    return out


def _krw_bithumb():
    d = _get("https://api.bithumb.com/public/ticker/BTC_KRW")
    if d.get("status") != "0000":
        raise RuntimeError(f"bithumb status={d.get('status')}")
    t = d["data"]
    return {
        "price": float(t["closing_price"]),
        "change_rate": float(t["fluctate_rate_24H"]),
        "basis": "24시간 대비",
        "source": "Bithumb",
    }


# ── 달러(USD) ──────────────────────────────────────────────────────────────

def _usd_binance():
    t = _get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")
    return {"price": float(t["lastPrice"]), "change_rate": float(t["priceChangePercent"]),
            "basis": "24시간 대비", "source": "Binance"}


def _usd_coinbase():
    t = _get("https://api.exchange.coinbase.com/products/BTC-USD/stats")
    last, opn = float(t["last"]), float(t["open"])
    return {"price": last, "change_rate": (last - opn) / opn * 100,
            "basis": "24시간 대비", "source": "Coinbase"}


# ── 환율 (김치 프리미엄 계산용) ──────────────────────────────────────────────

def _fx_shared():
    from fx_data import get_usdkrw_now   # 환율 칸과 캐시를 같이 쓴다(같은 값을 두 번 받지 않게)
    now = get_usdkrw_now()
    return (_sane_fx(now["price"]), "환율") if now else None


def _fx_usdt():
    # 대용: 업비트 USDT(달러 코인) 원화가. USDT 자체에도 프리미엄이 붙어 실제보다 작게 나올 수 있다.
    t = _get("https://api.upbit.com/v1/ticker?markets=KRW-USDT")[0]
    return _sane_fx(float(t["trade_price"])), "USDT"


def _sane_fx(v):
    # 상식 범위(1달러 = 800~2500원) 밖이면 응답 이상 → 예외를 던져 다음 소스로 넘어가게 한다
    if not 800 < v < 2500:
        raise ValueError(f"환율 값 이상: {v}")
    return v


def _first_ok(fetchers, label):
    """순서대로 시도해 처음 성공한 값을 돌려준다. 전부 실패하면 None(칸이 통째로 깨지지 않게)."""
    for f in fetchers:
        try:
            v = f()
            if v:
                return v
        except Exception as e:  # 네트워크·응답 형식 변경 모두 여기서 흡수하고 다음 소스로
            print(f"[crypto] {label} {f.__name__} 실패: {e}")
    return None


def _fx():
    ts, val = _cache["fx"]
    if val and time.time() - ts < FX_TTL:
        return val
    # 환율 칸과 같은 값(fx_data: 네이버→두나무→ECB)을 먼저 쓰고, 다 안 되면 업비트 USDT 로 대신.
    # 둘 다 실패하면 None → 김프 줄만 빠지고 나머지는 정상
    val = _first_ok([_fx_shared, _fx_usdt], "환율")
    if val:
        _cache["fx"] = (time.time(), val)
    return val


def _sparkline():
    """업비트 일봉 30개 종가 → 0~100 으로 맞춘 목록(지수 칸 스파크라인과 같은 형식)."""
    ts, val = _cache["spark"]
    if val and time.time() - ts < SPARK_TTL:
        return val
    try:
        rows = _get("https://api.upbit.com/v1/candles/days?market=KRW-BTC&count=30")
        prices = [float(r["trade_price"]) for r in reversed(rows)]   # 업비트는 최신이 맨 앞 → 뒤집기
        lo, hi = min(prices), max(prices)
        span = (hi - lo) or 1
        val = [round((p - lo) / span * 100, 1) for p in prices]
        _cache["spark"] = (time.time(), val)
    except Exception as e:
        print(f"[crypto] 30일 추이 실패: {e}")
    return val or []


# ── 10년 추이 ──────────────────────────────────────────────────────────────

def _long_bithumb():
    """빗썸 일봉 전체(한 번 요청) → [(날짜, 종가), ...] 오래된 것부터. 칸: [시각ms, 시가, 종가, 고가, 저가, 거래량]"""
    d = _get("https://api.bithumb.com/public/candlestick/BTC_KRW/24h")
    if d.get("status") != "0000":
        raise RuntimeError(f"bithumb status={d.get('status')}")
    rows = {}
    for r in d["data"]:
        day = datetime.fromtimestamp(int(r[0]) / 1000, KST).date().isoformat()
        close = float(r[2])
        if close > 0:
            rows[day] = close
    return sorted(rows.items())


def _long_upbit():
    rows = {day: close for day, _, close in _upbit_days() if close > 0}
    return sorted(rows.items())


def _load_long():
    """10년 추이를 받아 그래프용으로 줄인다(로그 눈금 0~100)."""
    for f, src in ((_long_bithumb, "Bithumb"), (_long_upbit, "Upbit")):
        try:
            rows = f()
        except Exception as e:
            print(f"[crypto] 10년 추이 {f.__name__} 실패: {e}")
            continue
        start = (date.today() - timedelta(days=365 * LONG_YEARS + 2)).isoformat()
        rows = [r for r in rows if r[0] >= start]
        if len(rows) < 365:                 # 1년도 안 되면 '긴 그래프'라 부를 수 없다 → 다음 소스
            print(f"[crypto] 10년 추이 {f.__name__} 점이 너무 적음: {len(rows)}개")
            continue
        step = max(1, len(rows) // LONG_POINTS)
        picked = rows[::step]
        if picked[-1] != rows[-1]:
            picked.append(rows[-1])         # 마지막 날은 꼭 넣는다
        return {"closes": [v for _, v in picked], "from": rows[0][0], "to": rows[-1][0],
                "source": src, "years": round(len(rows) / 365.25, 1)}
    return None


def _long_history():
    """캐시된 10년 추이. 없거나 오래됐으면 뒤에서 새로 받는다(그동안은 있는 것/없음을 돌려줌)."""
    now = time.time()
    fresh = _long["val"] and now - _long["ts"] < LONG_TTL
    retry_ok = now - _long["failed"] > LONG_RETRY
    if not fresh and not _long["loading"] and retry_ok:
        _long["loading"] = True

        def run():
            try:
                v = _load_long()
                if v:
                    _long.update(val=v, ts=time.time())
                else:
                    _long["failed"] = time.time()
            finally:
                _long["loading"] = False
        threading.Thread(target=run, daemon=True).start()
    return _long["val"]


def _long_chart(current):
    """10년 종가 + 지금 가격 → 로그 눈금 0~100 점. 그래프 끝은 지금 가격."""
    h = _long_history()
    if not h:
        return None
    vals = h["closes"] + ([current] if current else [])
    logs = [math.log10(v) for v in vals]
    lo, hi = min(logs), max(logs)
    span = (hi - lo) or 1
    return {"points": [round((v - lo) / span * 100, 1) for v in logs],
            "from": h["from"], "to": date.today().isoformat() if current else h["to"],
            "source": h["source"], "years": h["years"], "log": True,
            "min": round(min(vals)), "max": round(max(vals))}


# ── 역대 최고가(원화, 업비트) ────────────────────────────────────────────────

def _ath_load():
    if not _ath["loaded"]:
        _ath["loaded"] = True
        try:
            with open(ATH_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if float(d.get("price", 0)) > 0 and d.get("date"):
                _ath["data"] = d
        except (OSError, ValueError):
            pass
    return _ath["data"]


def _ath_save(d):
    _ath["data"] = d
    try:
        tmp = ATH_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, ATH_FILE)          # 쓰다 끊겨도 반쪽 파일이 남지 않게
    except OSError as e:
        print(f"[crypto] 역대 최고가 저장 실패: {e}")


def _upbit_days(max_pages=25, pause=0.15):
    """업비트 KRW-BTC 일봉을 오늘부터 거꾸로 200개씩 전부 받는다 → [(날짜, 고가, 종가), ...] 최신이 앞.
    25쪽 × 200일 = 5000일(약 13년) → 상장(2017-09) 전체를 덮는다. 업비트 요청 한도(초당 10회)를 지키려고 쉬어 가며."""
    out, to = [], None
    for _ in range(max_pages):
        url = "https://api.upbit.com/v1/candles/days?market=KRW-BTC&count=200"
        if to:
            url += f"&to={to}"
        rows = _get(url)
        if not rows:
            break
        for r in rows:
            out.append((str(r.get("candle_date_time_kst", ""))[:10],
                        float(r.get("high_price") or 0), float(r.get("trade_price") or 0)))
        if len(rows) < 200:
            break                                   # 맨 처음(상장일)까지 다 받음
        to = str(rows[-1]["candle_date_time_utc"])[:19]   # 가장 오래된 날 앞에서 다음 쪽
        time.sleep(pause)
    return out


def _scan_upbit_ath():
    """업비트 일봉 전체에서 '고가' 최댓값과 그날을 찾는다."""
    rows = _upbit_days()
    if len(rows) < 365:
        raise RuntimeError(f"일봉이 너무 적음: {len(rows)}일")
    day, best, _ = max(rows, key=lambda r: r[1])
    if best <= 0:
        raise RuntimeError("고가 값이 없음")
    return {"price": best, "date": day, "days": len(rows), "scanned": time.strftime("%Y-%m-%d")}


def _ath_scan_bg():
    """훑기는 수 초 걸리므로 화면을 붙잡지 않게 뒤에서 한 번만 돌린다."""
    with _ath_lock:
        if _ath["scanning"]:
            return
        _ath["scanning"] = True

    def run():
        try:
            d = _scan_upbit_ath()
            old = _ath["data"]
            if old and float(old["price"]) > d["price"]:      # 저장값이 더 높으면(오늘 고가로 갱신된 것) 유지
                d.update(price=float(old["price"]), date=old["date"])
            _ath_save(d)
            print(f"[crypto] 역대 최고가 확인: {d['price']:,.0f}원 ({d['date']}, 일봉 {d['days']}개)")
        except Exception as e:
            print(f"[crypto] 역대 최고가 훑기 실패: {e}")
        finally:
            _ath["scanning"] = False
    threading.Thread(target=run, daemon=True).start()


def _ath_for(krw):
    """원화 시세(krw)에 역대 최고가를 붙인다. 한 번도 다 훑은 적 없으면 붙이지 않는다."""
    d = _ath_load()
    stale = (not d) or d.get("scanned", "") < time.strftime(
        "%Y-%m-%d", time.localtime(time.time() - ATH_RESCAN_DAYS * 86400))
    if stale:
        _ath_scan_bg()
    if not d:
        return
    # 오늘 고가·52주 최고가·지금 가격 중 저장값보다 높은 게 있으면 그게 새 역대 최고가
    cands = [(float(d["price"]), d["date"])]
    if krw.get("high_today"):
        t = krw.get("today", "")
        cands.append((krw["high_today"], f"{t[:4]}-{t[4:6]}-{t[6:8]}" if len(t) == 8 else time.strftime("%Y-%m-%d")))
    if krw.get("high_52w") and krw.get("high_52w_date"):
        cands.append((krw["high_52w"], krw["high_52w_date"]))
    cands.append((krw["price"], time.strftime("%Y-%m-%d")))
    price, day = max(cands, key=lambda c: c[0])
    if price > float(d["price"]):
        _ath_save({**d, "price": price, "date": day})
    krw["ath"] = price
    krw["ath_date"] = day
    krw["dd_ath"] = round((krw["price"] / price - 1) * 100, 2)


def get_btc():
    """대시보드용 비트코인 묶음. 원화·달러 둘 다 실패하면 None."""
    with _lock:
        ts, val = _cache["quote"]
        if val and time.time() - ts < QUOTE_TTL:
            return val

        krw = _first_ok([_krw_upbit, _krw_bithumb], "원화")
        usd = _first_ok([_usd_binance, _usd_coinbase], "달러")
        if not krw and not usd:
            return None

        out = {"krw": krw, "usd": usd, "kimchi": None, "sparkline": _sparkline(), "long": None}

        if krw:
            krw["change_rate"] = round(krw["change_rate"], 2)
            if krw.get("high_52w"):
                krw["dd_52w"] = round((krw["price"] / krw["high_52w"] - 1) * 100, 2)
            if krw["source"] == "Upbit":      # 역대 최고가는 업비트 기준(빗썸 예비 시세와 섞지 않음)
                try:
                    _ath_for(krw)
                except Exception as e:
                    print(f"[crypto] 역대 최고가 처리 실패: {e}")
        if usd:
            usd["change_rate"] = round(usd["change_rate"], 2)

        # 10년 그래프(원화). 준비 전이면 None → 화면은 30일 그래프를 대신 보여 준다
        try:
            out["long"] = _long_chart(krw["price"] if krw else None)
        except Exception as e:
            print(f"[crypto] 10년 그래프 실패: {e}")

        # 김치 프리미엄 = 한국 원화가 ÷ (해외 달러가 × 환율) − 1
        if krw and usd:
            fx = _fx()
            if fx:
                rate, basis = fx
                out["kimchi"] = {
                    "pct": round((krw["price"] / (usd["price"] * rate) - 1) * 100, 2),
                    "fx": round(rate, 2),
                    "basis": basis,
                }

        _cache["quote"] = (time.time(), out)
        return out


if __name__ == "__main__":
    import sys
    if "--ath" in sys.argv:            # 역대 최고가를 지금 바로 처음부터 훑어 저장(서버 점검용)
        d = _scan_upbit_ath()
        _ath_save(d)
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(get_btc(), ensure_ascii=False, indent=2))
