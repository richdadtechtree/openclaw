"""
비트코인 시세 수집 모듈 (대시보드 '₿ 비트코인' 칸 전용)

- 주식 지수(market_data.get_snapshot)와 **완전히 분리**했다. 알람 스케줄러·투자 타이밍 계산은
  get_snapshot 을 쓰므로, 여기서 무슨 일이 생겨도 기존 지수/알람에는 영향이 없다.
- 전부 키 없이 쓰는 공개 API. 2026-10-06 서버 IP 에서 5곳 모두 정상 확인
  (scripts/test_btc_price.py — 응답 21~122ms, 같은 화폐끼리 차이 0.03% 이내).

  원화 가격 : 업비트(1순위) → 빗썸(예비)
  달러 가격 : 바이낸스 BTCUSDT(1순위) → 코인베이스 BTC-USD(예비)
  환율      : 두나무(업비트 운영사) 환율 → 실패 시 업비트 USDT 원화가(대용)
  30일 추이 : 업비트 일봉 종가

- 등락률 기준이 거래소마다 다르다(업비트=매일 오전 9시 대비, 빗썸=최근 24시간 대비).
  그래서 응답에 basis(기준)를 함께 담아 화면에 그대로 적는다.

직접 점검(서버, stock venv):  ~/stock/stock/venv/bin/python crypto_data.py
"""
import threading
import time

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

def _fx_dunamu():
    # 업비트 운영사(두나무)가 김치 프리미엄 계산에 쓰는 원/달러 환율(은행 고시 기준)
    d = _get("https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=FRX.KRWUSD")
    return _sane_fx(float(d[0]["basePrice"])), "환율"


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
    # 두 곳 다 실패하면 None → 김프 줄만 빠지고 나머지는 정상
    val = _first_ok([_fx_dunamu, _fx_usdt], "환율")
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

        out = {"krw": krw, "usd": usd, "kimchi": None, "sparkline": _sparkline()}

        if krw:
            krw["change_rate"] = round(krw["change_rate"], 2)
            if krw.get("high_52w"):
                krw["dd_52w"] = round((krw["price"] / krw["high_52w"] - 1) * 100, 2)
        if usd:
            usd["change_rate"] = round(usd["change_rate"], 2)

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
    import json
    print(json.dumps(get_btc(), ensure_ascii=False, indent=2))
