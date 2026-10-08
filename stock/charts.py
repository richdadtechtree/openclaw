"""
대시보드 그래프 기간 선택(6개월·1년·3년·5년·10년) — /api/charts?period=5y   (2026-10-08 사용자 요청)

카드 8장(코스피·코스닥·S&P500·나스닥·QLD·TQQQ·비트코인·원/달러 환율)의 그래프를 한 번에 돌려준다.
일별 값은 각 모듈이 이미 모아 둔 것을 쓰고, 여기서는 '기간만큼 자르기 → 최고/최저 → 점 줄이기'만 한다.

  지수·ETF : index_history.history_rows()  (네이버 일별, QLD·TQQQ 분할 보정, 10년)
  비트코인 : crypto_data.history_rows()    (빗썸 일봉 → 업비트, 원화, 10년)
  환율     : fx_data.history_rows()        (ECB 기준환율 → 네이버, 10년)

- 값은 **실제 값**으로 보낸다(0~100 으로 바꾸지 않음) → 화면이 기준 가로선(고점 대비 -30% 등)을 같은 눈금에 그릴 수 있다.
- 최고/최저는 줄이기 **전** 모든 날로 계산(줄인 점으로 하면 꼭짓점을 놓친다) + 지금 값도 포함.
- 로그 눈금: 그 기간에 최고/최저가 5배를 넘을 때만(비트코인 10년 같은 경우). 6개월·1년 같은 짧은 기간은 거의 항상 보통 눈금.
- 데이터가 기간보다 짧으면(예: 업비트 예비 9년) 있는 만큼만 보내고 years 에 실제 길이를 적는다(10년인 척 안 함).
- 기간마다 5분 캐시(20초마다 새로 고치는 화면이 매번 계산하지 않게).
"""
import threading
import time
from datetime import date, timedelta

PERIODS = {"6m": 0.5, "1y": 1, "3y": 3, "5y": 5, "10y": 10}
DEFAULT_PERIOD = "5y"
MAX_POINTS = 180          # 카드 폭(≈260px)에 비해 충분히 촘촘
MIN_DAYS = 20             # 이보다 적으면 그래프로 보이지 않는다
LOG_RATIO = 5             # 최고/최저 > 5 이면 로그 눈금
CACHE_TTL = 300
INDEX_NAMES = ["KOSPI", "KOSDAQ", "S&P 500", "NASDAQ", "QLD", "TQQQ"]

_lock = threading.Lock()
_cache = {}


def series(rows, period, current=None, source=None, extra=None):
    """일별 [(날짜, 값), ...] → 기간만큼 자른 그래프 묶음. 너무 짧으면 None."""
    years = PERIODS[period]
    today = date.today()
    start = (today - timedelta(days=round(365.25 * years))).isoformat()
    cut = [(d, v) for d, v in rows if d >= start and v and v > 0]
    if current and current > 0:
        cut = [(d, v) for d, v in cut if d < today.isoformat()] + [(today.isoformat(), float(current))]
    if len(cut) < MIN_DAYS:
        return None
    hi_d, hi = max(cut, key=lambda r: r[1])
    lo_d, lo = min(cut, key=lambda r: r[1])
    step = max(1, -(-len(cut) // MAX_POINTS))        # 올림 나눗셈
    picked = cut[::step]
    if picked[-1] != cut[-1]:
        picked.append(cut[-1])                       # 마지막(지금) 값은 꼭 넣는다
    span_days = (date.fromisoformat(cut[-1][0]) - date.fromisoformat(cut[0][0])).days
    last = cut[-1][1]
    out = {
        "values": [round(v, 4) for _, v in picked],
        "from": cut[0][0], "to": cut[-1][0],
        "years": round(span_days / 365.25, 1),
        "high": round(hi, 4), "high_date": hi_d,
        "low": round(lo, 4), "low_date": lo_d,
        "from_high_pct": round((last / hi - 1) * 100, 2),
        "change_pct": round((last / cut[0][1] - 1) * 100, 2),    # 기간 처음 대비
        "log": hi / lo > LOG_RATIO,
        "source": source,
    }
    if extra:
        out.update(extra)
    return out


def _currents():
    """카드마다 '지금 값' — 그래프 끝을 화면 숫자와 맞춘다(모두 각 모듈의 캐시를 쓰므로 가볍다)."""
    cur = {}
    try:
        from market_data import get_snapshot
        for k, v in (get_snapshot(include_sparkline=False) or {}).items():
            cur[k] = v.get("current")
    except Exception as e:
        print(f"[charts] 지수 현재값 실패: {e}")
    try:
        from crypto_data import get_btc
        b = get_btc()
        if b and b.get("krw"):
            cur["BTC"] = b["krw"]["price"]
    except Exception as e:
        print(f"[charts] 비트코인 현재값 실패: {e}")
    try:
        from fx_data import get_usdkrw_now
        f = get_usdkrw_now()
        if f:
            cur["USDKRW"] = f["price"]
    except Exception as e:
        print(f"[charts] 환율 현재값 실패: {e}")
    return cur


def get_charts(period=DEFAULT_PERIOD):
    if period not in PERIODS:
        period = DEFAULT_PERIOD
    with _lock:
        hit = _cache.get(period)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    cur = _currents()
    out = {}
    import index_history
    for name in INDEX_NAMES:
        try:
            rows, splits = index_history.history_rows(name)
            out[name] = series(rows, period, cur.get(name), "Naver", {"splits": splits})
        except Exception as e:
            print(f"[charts] {name} 실패: {e}")
            out[name] = None
    try:
        import crypto_data
        rows, src = crypto_data.history_rows()
        out["BTC"] = series(rows, period, cur.get("BTC"), src)
    except Exception as e:
        print(f"[charts] 비트코인 실패: {e}")
        out["BTC"] = None
    try:
        import fx_data
        rows, src = fx_data.history_rows()
        out["USDKRW"] = series(rows, period, cur.get("USDKRW"), src)
    except Exception as e:
        print(f"[charts] 환율 실패: {e}")
        out["USDKRW"] = None
    # 아직 데이터를 받는 중인 칸(None)이 있으면 짧게만 캐시 → 받는 대로 금방 그래프가 생긴다
    ttl_hit = time.time() - (CACHE_TTL - 30 if any(v is None for v in out.values()) else 0)
    with _lock:
        _cache[period] = (ttl_hit, out)
    return out


def warm_up():
    """서버가 켜질 때 뒤에서 10년치 받기를 미리 시작(첫 화면부터 그래프가 나오게)."""
    def run():
        try:
            import index_history
            index_history.refresh()
        except Exception as e:
            print(f"[charts] 지수 미리 받기 실패: {e}")
        try:
            import crypto_data
            crypto_data.history_rows()
        except Exception as e:
            print(f"[charts] 비트코인 미리 받기 실패: {e}")
        try:
            import fx_data
            fx_data.history_rows()
        except Exception as e:
            print(f"[charts] 환율 미리 받기 실패: {e}")
    threading.Thread(target=run, daemon=True).start()
