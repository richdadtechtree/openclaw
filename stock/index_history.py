"""
지수·ETF 5년 추이 (대시보드 코스피·코스닥·S&P500·나스닥·QLD·TQQQ 칸 아래 그래프)

- 예전 30일 그래프는 야후(yfinance)에서 받았는데 서버 IP 에서 막혀 점선만 보였다.
  → 서버에서 잘 되는 **네이버 금융 일별 시세**로 바꾼다(지수 시세도 이미 네이버를 쓴다).
- 네이버는 한 번에 50일까지만 준다(더 크게 달라면 이상한 응답) → 5년 ≈ 1250거래일 ≈ 25쪽.
  처음 한 번만 다 받고 파일(.index_hist.json)에 저장, 이후엔 최신 1~2쪽만 받아 이어 붙인다.
  받기는 뒤에서(화면 안 막음), 6시간마다 새로 고침.
- ⚠️ QLD·TQQQ 는 액면분할 이력이 있는데 네이버 미국 일별 시세는 **분할을 반영하지 않은 값**이다
  (market_data.py NAVER_HISTORY 주석 참고). 그대로 그리면 분할한 날 가격이 1/2·1/3 로 '폭락'한 것처럼 보인다.
  → 하루 사이 값이 1/2·1/3·1/4(또는 2·3·4배)에 가깝게(±8%) 변한 날을 분할로 보고, 그 이전 값을 나눠 맞춘다.
  (3배 레버리지도 하루에 -45% 이상 빠진 적은 없어서 진짜 폭락과 헷갈리지 않는다.)
- 지수 시세·알람(get_snapshot 의 다른 부분)과는 따로 돈다. 여기서 실패해도 그래프만 30일/점선으로 남는다.

서버 점검(stock venv):  cd ~/stock/stock && venv/bin/python index_history.py   # 받아서 저장하고 요약 출력
"""
import json
import os
import threading
import time
from datetime import date, timedelta

import requests

YEARS = 5
POINTS = 160              # 그래프 점 개수(5년 ≈ 주 1점보다 조금 촘촘)
PAGE_SIZE = 50            # 네이버 상한(100 이면 비정상 응답)
MAX_PAGES = 30            # 30쪽 × 50 = 1500거래일 ≈ 6년
REFRESH = 6 * 3600        # 6시간마다 최신 쪽만 다시 받기
RETRY = 600               # 실패하면 10분 뒤 재시도
PAUSE = 0.12              # 네이버를 너무 몰아서 두드리지 않게
HIST_FILE = os.getenv("INDEX_HIST_FILE", ".index_hist.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# 이름 → (네이버 일별 시세 주소 틀, 분할 보정 여부). 코드는 market_data._fetch_naver_quote 와 같다.
SOURCES = {
    "KOSPI":   ("https://m.stock.naver.com/api/index/KOSPI/price?pageSize={n}&page={p}", False),
    "KOSDAQ":  ("https://m.stock.naver.com/api/index/KOSDAQ/price?pageSize={n}&page={p}", False),
    "S&P 500": ("https://api.stock.naver.com/index/.INX/price?pageSize={n}&page={p}", False),
    "NASDAQ":  ("https://api.stock.naver.com/index/.IXIC/price?pageSize={n}&page={p}", False),
    "QLD":     ("https://api.stock.naver.com/stock/QLD/price?pageSize={n}&page={p}", True),
    "TQQQ":    ("https://api.stock.naver.com/stock/TQQQ.O/price?pageSize={n}&page={p}", True),
}

_lock = threading.Lock()
_state = {"loaded": False, "rows": {}, "fetched": {}, "loading": False, "failed": 0}


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _rows_of(payload):
    """네이버 응답에서 일별 행 목록을 꺼낸다(목록 그대로이거나 dict 로 감싼 경우 모두)."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("priceInfos", "prices", "priceList", "result", "datas", "list", "items"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def _page(name, page):
    """한 쪽(최대 50일) → {날짜: 종가}."""
    url = SOURCES[name][0].format(n=PAGE_SIZE, p=page)
    r = requests.get(url, headers=HEADERS, timeout=8)
    r.raise_for_status()
    out = {}
    for row in _rows_of(r.json()):
        day = str(row.get("localTradedAt") or row.get("localDate") or row.get("date") or "")[:10]
        if len(day) == 8 and day.isdigit():                       # 'YYYYMMDD' 형식도 받아 준다
            day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        close = _num(row.get("closePrice") or row.get("close"))
        if len(day) == 10 and day[4] == "-" and close and close > 0:
            out[day] = close
    return out


def _fetch(name, have):
    """have(이미 가진 {날짜: 종가}) 에 없는 최신 날들만 받아 합친다. 처음이면 5년치 전부."""
    start = (date.today() - timedelta(days=365 * YEARS + 7)).isoformat()
    rows = dict(have)
    for p in range(1, MAX_PAGES + 1):
        got = _page(name, p)
        if not got:
            break
        new = {d: v for d, v in got.items() if d not in rows}
        rows.update(got)                 # 최근 값은 덮어써서 고침(장중 값 → 확정 종가)
        if have and not new:
            break                        # 이미 가진 날까지 내려왔으면 그만(이어 붙이기)
        if min(got) <= start:
            break                        # 5년 전까지 다 받음
        time.sleep(PAUSE)
    return {d: v for d, v in rows.items() if d >= start}


def adjust_splits(rows):
    """[(날짜, 종가), ...] 오래된 것부터 → 액면분할을 반영한 값.
    하루 사이 비율이 1/2·1/3·1/4 (정분할) 또는 2·3·4 (병합)에 ±8% 안으로 가까우면 분할로 본다."""
    if len(rows) < 2:
        return list(rows), []
    vals = [v for _, v in rows]
    factor, splits = 1.0, []
    out = [vals[-1]]
    for i in range(len(vals) - 1, 0, -1):          # 최신 → 과거로 가며, 분할일을 지나면 이전 값에 배수를 곱한다
        ratio = vals[i] / vals[i - 1]
        for k in (2, 3, 4):
            if abs(ratio * k - 1) < 0.08:            # 1/k 로 떨어짐 = k:1 분할
                factor /= k
                splits.append((rows[i][0], f"{k}:1"))
                break
            if abs(ratio / k - 1) < 0.08:            # k 배로 뜀 = 1:k 병합
                factor *= k
                splits.append((rows[i][0], f"1:{k}"))
                break
        out.append(vals[i - 1] * factor)
    out.reverse()
    return [(d, v) for (d, _), v in zip(rows, out)], splits


def _load_file():
    if _state["loaded"]:
        return
    _state["loaded"] = True
    try:
        with open(HIST_FILE, encoding="utf-8") as f:
            d = json.load(f)
        _state["rows"] = {k: dict(v) for k, v in d.get("rows", {}).items()}
        _state["fetched"] = d.get("fetched", {})
    except (OSError, ValueError):
        pass


def _save_file():
    try:
        tmp = HIST_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"rows": _state["rows"], "fetched": _state["fetched"]}, f, ensure_ascii=False)
        os.replace(tmp, HIST_FILE)
    except OSError as e:
        print(f"[index-hist] 저장 실패: {e}")


def refresh(names=None, force=False):
    """오래된 심볼만 네이버에서 받아 갱신하고 파일에 저장(뒤에서 부르는 함수)."""
    _load_file()
    now = time.time()
    ok_any, fail_any = False, False
    for name in names or SOURCES:
        if not force and now - _state["fetched"].get(name, 0) < REFRESH and _state["rows"].get(name):
            continue
        try:
            rows = _fetch(name, _state["rows"].get(name, {}))
            if len(rows) >= 200:          # 1년도 안 되면 잘못 받은 것 → 저장 안 함
                _state["rows"][name] = rows
                _state["fetched"][name] = time.time()
                ok_any = True
            else:
                print(f"[index-hist] {name} 점이 너무 적음: {len(rows)}개")
                fail_any = True
        except Exception as e:
            print(f"[index-hist] {name} 받기 실패: {e}")
            fail_any = True
    if ok_any:
        _save_file()
    if fail_any:
        _state["failed"] = time.time()


def _kick():
    """오래됐으면 뒤에서 refresh 한 번(동시에 둘이 돌지 않게)."""
    now = time.time()
    stale = any(now - _state["fetched"].get(n, 0) >= REFRESH for n in SOURCES)
    if not stale or _state["loading"] or now - _state["failed"] < RETRY:
        return
    with _lock:
        if _state["loading"]:
            return
        _state["loading"] = True

    def run():
        try:
            refresh()
        finally:
            _state["loading"] = False
    threading.Thread(target=run, daemon=True).start()


def get_long(name, current=None):
    """그래프용 5년 추이 {points(0~100), from, to, years, source, splits}. 아직 없으면 None."""
    _load_file()
    _kick()
    raw = _state["rows"].get(name)
    if not raw or name not in SOURCES:
        return None
    rows = sorted(raw.items())
    splits = []
    if SOURCES[name][1]:
        rows, splits = adjust_splits(rows)
    step = max(1, len(rows) // POINTS)
    pts = [v for _, v in rows[::step]]
    if rows[::step][-1] != rows[-1]:
        pts.append(rows[-1][1])
    if current:
        pts.append(current)              # 그래프 끝은 지금 값
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    return {
        "points": [round((p - lo) / span * 100, 1) for p in pts],
        "from": rows[0][0], "to": date.today().isoformat() if current else rows[-1][0],
        # 실제 날짜 차이로(거래일 수로 나누면 한국·미국 휴일 수가 달라 어긋난다)
        "years": round((date.fromisoformat(rows[-1][0]) - date.fromisoformat(rows[0][0])).days / 365.25, 1),
        "source": "Naver", "min": round(lo, 2), "max": round(hi, 2),
        "splits": [f"{d} {r}" for d, r in splits],
    }


if __name__ == "__main__":
    refresh(force=True)
    for n in SOURCES:
        g = get_long(n)
        if g:
            print(f"✅ {n:<8} {g['from']} ~ {g['to']} ({g['years']}년, 점 {len(g['points'])}개) "
                  f"최저 {g['min']:,} 최고 {g['max']:,}" + (f" · 분할 보정 {g['splits']}" if g['splits'] else ""))
        else:
            print(f"❌ {n:<8} 데이터 없음")
