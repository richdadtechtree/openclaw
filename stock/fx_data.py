"""
원/달러 환율 수집 모듈 (대시보드 '💱 원/달러 환율' 칸 + 비트코인 김치 프리미엄 계산)

- 지수(market_data)·비트코인(crypto_data)과 분리. 여기서 장애가 나도 다른 칸은 그대로.
- 전부 키 없이 쓰는 공개 데이터. 소스마다 '순서대로 시도 → 처음 성공한 값' 방식.

  현재 환율 : 네이버 금융(1순위, 장중 실시간) → 두나무(업비트 운영사) → 유럽중앙은행(ECB) 기준환율
  3년 추이  : 유럽중앙은행(ECB) 기준환율 — Frankfurter 공개 API(https://frankfurter.dev, ECB 자료를 그대로 제공)
              → 실패 시 네이버 금융 일별 시세
              ECB 기준환율은 중앙은행이 매 영업일 1회 고시하는 공식 값이라 3년 흐름을 보기에 믿을 만하다.

- 값 검사: 1달러 = 800~2500원 밖이면 응답 이상으로 보고 버린다(다음 소스로).

서버 점검(stock venv):
    cd ~/stock/stock && venv/bin/python fx_data.py           # 대시보드가 받을 결과
    cd ~/stock/stock && venv/bin/python fx_data.py --probe   # 소스마다 되는지 하나씩
"""
import re
import threading
import time
from datetime import date, datetime, timedelta

import requests

TIMEOUT = 6
NOW_TTL = 60            # 초. 현재 환율 캐시
HIST_TTL = 6 * 3600     # 초. 3년 추이는 하루 한 점이라 6시간 캐시
YEARS = 3
CHART_POINTS = 160      # 그래프 점 개수(3년 ≈ 주 1점). 너무 많으면 작은 카드에서 뭉개진다.
FX_MIN, FX_MAX = 800, 2500

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://m.stock.naver.com/",
}

_lock = threading.Lock()
_cache = {"now": (0, None), "hist": (0, None)}


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _num(v):
    """'1,385.50' / 1385.5 / '+0.42' → float. 숫자가 아니면 None."""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("+", "").strip())
    except ValueError:
        return None


def _sane(v):
    if v is None or not (FX_MIN < v < FX_MAX):
        raise ValueError(f"환율 값 이상: {v}")
    return v


def _find(obj, keys):
    """JSON 안을 뒤져 keys 중 처음 나오는 키의 값을 돌려준다.
    네이버 응답은 감싸는 겉모양({result:{...}} 등)이 주소마다 달라서, 겉모양에 기대지 않으려고 찾아 들어간다."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] not in (None, ""):
                return obj[k]
        for v in obj.values():
            found = _find(v, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, keys)
            if found is not None:
                return found
    return None


def _find_rows(obj):
    """JSON 안에서 '종가(closePrice)를 가진 항목들의 목록'을 찾아 돌려준다(겉모양과 무관)."""
    if isinstance(obj, list):
        if any(isinstance(x, dict) and "closePrice" in x for x in obj):
            return obj
        for v in obj:
            r = _find_rows(v)
            if r:
                return r
    elif isinstance(obj, dict):
        for v in obj.values():
            r = _find_rows(v)
            if r:
                return r
    return []


# ── 현재 환율 ──────────────────────────────────────────────────────────────
# 각 함수는 {"price", "change_rate"(없으면 None), "source"} 를 돌려준다.

def _now_naver_front():
    d = _get("https://m.stock.naver.com/front-api/marketIndex/productDetail"
             "?category=exchange&reutersCode=FX_USDKRW")
    return {"price": _sane(_num(_find(d, ["closePrice", "currentPrice", "nowPrice"]))),
            "change_rate": _num(_find(d, ["fluctuationsRatio", "changeRate"])),
            "source": "Naver"}


def _now_naver_api():
    d = _get("https://api.stock.naver.com/marketindex/exchange/FX_USDKRW")
    return {"price": _sane(_num(_find(d, ["closePrice", "currentPrice", "nowPrice"]))),
            "change_rate": _num(_find(d, ["fluctuationsRatio", "changeRate"])),
            "source": "Naver"}


def _now_dunamu():
    d = _get("https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=FRX.KRWUSD")[0]
    price = _sane(_num(d["basePrice"]))
    rate = _num(d.get("signedChangeRate"))
    return {"price": price, "change_rate": rate * 100 if rate is not None else None, "source": "Dunamu"}


def _now_ecb():
    # ECB 기준환율 최신값(하루 1회 고시). 실시간은 아니지만 공식 값이라 마지막 예비로 쓴다.
    d = _first_json(["https://api.frankfurter.dev/v1/latest?base=USD&symbols=KRW",
                     "https://api.frankfurter.app/latest?from=USD&to=KRW"])
    return {"price": _sane(_num(d["rates"]["KRW"])), "change_rate": None,
            "source": "ECB", "asof": d.get("date")}


# ── 3년 추이 ───────────────────────────────────────────────────────────────
# 각 함수는 [(날짜문자열 'YYYY-MM-DD', 환율), ...] 를 오래된 것부터 돌려준다.

def _first_json(urls):
    last = None
    for u in urls:
        try:
            return _get(u)
        except Exception as e:  # 주소가 바뀌었거나 막혔으면 다음 주소로
            last = e
    raise last


def _hist_ecb():
    start = (date.today() - timedelta(days=365 * YEARS + 3)).isoformat()
    d = _first_json([f"https://api.frankfurter.dev/v1/{start}..?base=USD&symbols=KRW",
                     f"https://api.frankfurter.app/{start}..?from=USD&to=KRW"])
    rows = sorted((day, _num(v.get("KRW"))) for day, v in d["rates"].items())
    return [(day, v) for day, v in rows if v and FX_MIN < v < FX_MAX]


def _hist_naver():
    # 네이버 일별 시세: 한 장(page)에 60일 → 3년 ≈ 13장. 오래 걸리지 않게 8초 안에서만.
    rows, t0 = {}, time.time()
    for page in range(1, 16):
        if time.time() - t0 > 8:
            break
        d = _get("https://m.stock.naver.com/front-api/marketIndex/prices"
                 f"?category=exchange&reutersCode=FX_USDKRW&page={page}&pageSize=60")
        items = _find_rows(d)
        got = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            day = str(it.get("localTradedAt") or it.get("tradeDate") or it.get("date") or "")[:10]
            v = _num(it.get("closePrice"))
            if re.match(r"\d{4}-\d{2}-\d{2}$", day) and v and FX_MIN < v < FX_MAX:
                rows[day] = v
                got += 1
        if not got:
            break
        if min(rows) <= (date.today() - timedelta(days=365 * YEARS)).isoformat():
            break
    return sorted(rows.items())


def _first_ok(fetchers, label):
    for f in fetchers:
        try:
            v = f()
            if v:
                return v
        except Exception as e:
            print(f"[fx] {label} {f.__name__} 실패: {e}")
    return None


def _history():
    ts, val = _cache["hist"]
    if val and time.time() - ts < HIST_TTL:
        return val
    for f in (_hist_ecb, _hist_naver):
        try:
            rows = f()
        except Exception as e:
            print(f"[fx] 3년 추이 {f.__name__} 실패: {e}")
            continue
        if len(rows) >= 100:          # 3년치면 수백 개. 너무 적으면 뭔가 잘못 받은 것 → 다음 소스
            src = "ECB" if f is _hist_ecb else "Naver"
            _cache["hist"] = (time.time(), (rows, src))
            return rows, src
        print(f"[fx] 3년 추이 {f.__name__} 점이 너무 적음: {len(rows)}개")
    return val  # 다 실패하면 예전 캐시라도(없으면 None)


def _summarize(rows, current):
    """3년 일별 값 → 그래프 점(0~100) + 최고/최저 + 고점 대비(지금 환율이 3년 최고점에서 몇 % 아래인지)."""
    vals = [v for _, v in rows]
    hi_i = max(range(len(vals)), key=vals.__getitem__)
    lo_i = min(range(len(vals)), key=vals.__getitem__)
    high, high_date = vals[hi_i], rows[hi_i][0]
    low, low_date = vals[lo_i], rows[lo_i][0]
    # 추이(ECB)는 하루 늦게 들어오므로, 지금 환율이 기록보다 높거나 낮으면 오늘을 고점/저점으로 본다
    today = date.today().isoformat()
    if current and current > high:
        high, high_date = current, today
    if current and current < low:
        low, low_date = current, today
    step = max(1, len(rows) // CHART_POINTS)
    pts = vals[::step]
    if current:
        pts = pts + [current]      # 그래프 끝은 지금 환율에 맞춘다
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    return {
        "points": [round((p - lo) / span * 100, 1) for p in pts],
        "from": rows[0][0], "to": rows[-1][0],
        "high": round(high, 2), "high_date": high_date,
        "low": round(low, 2), "low_date": low_date,
        "start": round(vals[0], 2),
        # 고점 대비(2026-10-08 사용자 요청: '3년 전 대비' 대신) — 0 이면 지금이 고점, -5 면 고점보다 5% 낮음
        "from_high_pct": round(((current or vals[-1]) / high - 1) * 100, 2),
    }


def get_usdkrw_now():
    """현재 환율만 (김치 프리미엄 계산용). 실패하면 None."""
    ts, val = _cache["now"]
    if val and time.time() - ts < NOW_TTL:
        return val
    val = _first_ok([_now_naver_front, _now_naver_api, _now_dunamu, _now_ecb], "현재 환율")
    if val:
        _cache["now"] = (time.time(), val)
    return val


def get_usdkrw():
    """대시보드용 묶음: 현재 환율·전일 대비·3년 추이. 현재값·추이 둘 다 없으면 None."""
    with _lock:
        now = get_usdkrw_now()
        hist = _history()
        if not now and not hist:
            return None
        rows, hist_src = hist if hist else ([], None)

        out = dict(now) if now else {"price": rows[-1][1], "change_rate": None,
                                     "source": hist_src, "asof": rows[-1][0]}
        # 등락률을 안 주는 소스(ECB 등)면 추이의 '오늘 이전 마지막 값'과 비교해 직접 계산
        if out.get("change_rate") is None and rows:
            today = datetime.now().date().isoformat()
            prev = [v for d, v in rows if d < today]
            if prev:
                out["change_rate"] = (out["price"] / prev[-1] - 1) * 100
        if out.get("change_rate") is not None:
            out["change_rate"] = round(out["change_rate"], 2)
        out["price"] = round(out["price"], 2)
        out["basis"] = "전일 대비"
        out["history"] = _summarize(rows, now["price"] if now else None) if rows else None
        out["history_source"] = hist_src
        return out


def _probe():
    """서버에서 소스마다 되는지 하나씩 확인(어디가 막혔는지 알려고)."""
    for f in (_now_naver_front, _now_naver_api, _now_dunamu, _now_ecb):
        try:
            print(f"✅ 현재 {f.__name__:<18} {f()}")
        except Exception as e:
            print(f"❌ 현재 {f.__name__:<18} {e}")
    for f in (_hist_ecb, _hist_naver):
        try:
            rows = f()
            print(f"{'✅' if len(rows) >= 100 else '⚠️'} 3년 {f.__name__:<18} {len(rows)}개 "
                  f"{rows[0] if rows else ''} ~ {rows[-1] if rows else ''}")
        except Exception as e:
            print(f"❌ 3년 {f.__name__:<18} {e}")


if __name__ == "__main__":
    import json
    import sys
    if "--probe" in sys.argv:
        _probe()
    else:
        print(json.dumps(get_usdkrw(), ensure_ascii=False, indent=2))
