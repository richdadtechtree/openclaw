#!/usr/bin/env python3
"""비트코인 가격을 '서버에서' 잘 받아오는지 미리 시험하는 스크립트.

대시보드(stock, 포트 8000)에 비트코인 칸을 만들기 전에, 어떤 곳(거래소/집계 사이트)의
데이터가 **이 서버 IP 에서** 막히지 않고 빠르고 정확하게 오는지 확인한다.
(전례: yfinance 는 서버 IP 에서만 막혔다 → 서버에서 직접 돌려 봐야 안다.)

확인하는 곳 (전부 키 없이 쓰는 공개 API):
  원화(KRW)  : 업비트, 빗썸            ← 한국 시세(김치 프리미엄 포함)
  달러(USD)  : 바이낸스(USDT), 코인베이스, 코인게코

확인하는 것:
  ① 응답 여부/HTTP 코드/걸린 시간  ② 현재가·24시간 등락률  ③ 데이터 시각(너무 오래된 값인지)
  ④ 교차 검증 — 같은 화폐끼리 값이 1.5% 넘게 다르면 경고(한 곳이 이상한 값을 주는지)
  ⑤ 참고: 업비트 원화가 ÷ 바이낸스 달러가 = 비트코인으로 본 환율, 업비트 USDT 원화가와 비교해 김치 프리미엄

외부 라이브러리 없음(urllib 만) → 시스템 python3 로 그냥 실행:
    python3 scripts/test_btc_price.py          # 사람이 읽는 표
    python3 scripts/test_btc_price.py --json   # 기계용 JSON
종료코드: 0 = 원화·달러 각각 1곳 이상 성공 / 1 = 한쪽만 성공 / 2 = 전부 실패
"""

import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 8          # 초. 대시보드 갱신을 막지 않으려면 이 안에 와야 쓸 만하다.
STALE_SEC = 300      # 데이터 시각이 5분보다 오래됐으면 '오래된 값' 경고
DIFF_WARN = 1.5      # 같은 화폐 소스끼리 % 차이가 이보다 크면 경고

# 일부 사이트는 파이썬 기본 User-Agent 를 봇으로 보고 막는다 → 브라우저처럼 보이게.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch_json(url):
    """URL 을 열어 (JSON, HTTP코드, 걸린ms) 를 돌려준다. 실패하면 예외에 이유를 담아 던진다."""
    req = urllib.request.Request(url, headers=HEADERS)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        # 403(차단)·451(지역 제한)·429(너무 자주 부름) 같은 코드를 그대로 보여 주는 게 진단에 중요
        raise RuntimeError(f"HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"연결 실패: {e.reason}")
    except TimeoutError:
        raise RuntimeError(f"시간 초과({TIMEOUT}초)")
    ms = int((time.time() - t0) * 1000)
    return json.loads(body.decode("utf-8")), code, ms


# ── 소스별 파서: (가격, 24h 등락률%, 데이터시각 epoch초 or None) 를 돌려준다 ──────────

def parse_upbit(d):
    # 업비트 등락률은 '전일 종가(한국시각 09:00 기준)' 대비. signed_change_rate 는 0.0123 = 1.23%
    t = d[0]
    return float(t["trade_price"]), float(t["signed_change_rate"]) * 100, t["trade_timestamp"] / 1000


def parse_bithumb(d):
    if d.get("status") != "0000":
        raise RuntimeError(f"빗썸 오류 status={d.get('status')}")
    t = d["data"]
    return float(t["closing_price"]), float(t["fluctate_rate_24H"]), int(t["date"]) / 1000


def parse_binance(d):
    return float(d["lastPrice"]), float(d["priceChangePercent"]), d["closeTime"] / 1000


def parse_coinbase(d):
    # stats 는 24시간 시가(open)·현재가(last)만 준다 → 등락률은 직접 계산
    last, opn = float(d["last"]), float(d["open"])
    return last, (last - opn) / opn * 100, None


def parse_coingecko_usd(d):
    b = d["bitcoin"]
    return float(b["usd"]), float(b["usd_24h_change"]), b.get("last_updated_at")


def parse_upbit_usdt(d):
    # 업비트의 테더(USDT) 원화 가격 ≈ 한국 시장이 매기는 1달러 값 (김치 프리미엄 계산용)
    t = d[0]
    return float(t["trade_price"]), float(t["signed_change_rate"]) * 100, t["trade_timestamp"] / 1000


SOURCES = [
    # (이름, 화폐, URL, 파서)
    ("업비트",   "KRW", "https://api.upbit.com/v1/ticker?markets=KRW-BTC", parse_upbit),
    ("빗썸",     "KRW", "https://api.bithumb.com/public/ticker/BTC_KRW", parse_bithumb),
    ("바이낸스", "USD", "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", parse_binance),
    ("코인베이스", "USD", "https://api.exchange.coinbase.com/products/BTC-USD/stats", parse_coinbase),
    ("코인게코", "USD",
     "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
     "&include_24hr_change=true&include_last_updated_at=true", parse_coingecko_usd),
]
USDT_SOURCE = ("업비트 USDT", "KRW", "https://api.upbit.com/v1/ticker?markets=KRW-USDT", parse_upbit_usdt)


def probe(name, cur, url, parser):
    """한 소스를 시험해 결과 dict 를 만든다(실패해도 예외 대신 ok=False 로 기록)."""
    r = {"name": name, "currency": cur, "url": url, "ok": False}
    try:
        data, code, ms = fetch_json(url)
        price, chg, ts = parser(data)
        if not price or price <= 0:
            raise RuntimeError(f"가격이 이상함: {price}")
        r.update(ok=True, http=code, ms=ms, price=price, change_pct=round(chg, 2))
        if ts:
            r["age_sec"] = int(time.time() - ts)
    except Exception as e:  # 파싱 실패(응답 형식 변경)도 여기서 잡혀 이유가 남는다
        r["error"] = str(e)
    return r


def cross_check(results):
    """같은 화폐 소스들의 가격 차이(중앙값 대비 %)를 보고 튀는 곳을 찾는다."""
    warns = []
    for cur in ("KRW", "USD"):
        ok = [r for r in results if r["ok"] and r["currency"] == cur]
        if len(ok) < 2:
            continue
        prices = sorted(r["price"] for r in ok)
        mid = prices[len(prices) // 2]
        for r in ok:
            r["diff_pct"] = round((r["price"] - mid) / mid * 100, 2)
        if len(ok) == 2:
            # 2곳뿐이면 누가 틀렸는지 알 수 없다 → 한쪽을 탓하지 말고 '둘이 다르다'고만 알린다
            a, b = ok
            gap = (a["price"] - b["price"]) / b["price"] * 100
            if abs(gap) > DIFF_WARN:
                warns.append(f"{a['name']}·{b['name']} 두 {cur} 소스가 {abs(gap):.2f}% 차이(어느 쪽이 맞는지 판단 불가)")
            continue
        for r in ok:
            if abs(r["diff_pct"]) > DIFF_WARN:
                warns.append(f"{r['name']} 가 다른 {cur} 소스와 {r['diff_pct']:+.2f}% 차이")
    for r in results:
        if r["ok"] and r.get("age_sec", 0) > STALE_SEC:
            warns.append(f"{r['name']} 데이터가 {r['age_sec']}초 전 값(오래됨)")
    return warns


def main():
    as_json = "--json" in sys.argv
    results = [probe(*s) for s in SOURCES]
    usdt = probe(*USDT_SOURCE)
    warns = cross_check(results)

    # 참고 지표: 비트코인으로 본 환율 vs 업비트 USDT → 김치 프리미엄
    by = {r["name"]: r for r in results}
    extra = {}
    if by["업비트"]["ok"] and by["바이낸스"]["ok"]:
        implied = by["업비트"]["price"] / by["바이낸스"]["price"]
        extra["btc_implied_usdkrw"] = round(implied, 1)
        if usdt["ok"]:
            extra["upbit_usdt_krw"] = usdt["price"]
            extra["kimchi_premium_pct"] = round((implied / usdt["price"] - 1) * 100, 2)

    krw_ok = any(r["ok"] for r in results if r["currency"] == "KRW")
    usd_ok = any(r["ok"] for r in results if r["currency"] == "USD")
    code = 0 if (krw_ok and usd_ok) else (1 if (krw_ok or usd_ok) else 2)

    if as_json:
        print(json.dumps({"results": results, "usdt": usdt, "extra": extra,
                          "warnings": warns, "exit": code}, ensure_ascii=False, indent=2))
        return code

    print(f"비트코인 가격 소스 점검  ({time.strftime('%Y-%m-%d %H:%M:%S')})\n")
    for r in results + [usdt]:
        if r["ok"]:
            fmt = f"{r['price']:,.0f}" if r["currency"] == "KRW" and r["price"] > 10000 else f"{r['price']:,.2f}"
            age = f" · {r['age_sec']}초 전" if "age_sec" in r else ""
            diff = f" · 중앙값 대비 {r['diff_pct']:+.2f}%" if "diff_pct" in r else ""
            print(f"  ✅ {r['name']:<8} {fmt:>16} {r['currency']}  {r['change_pct']:+6.2f}%  "
                  f"({r['ms']}ms{age}{diff})")
        else:
            print(f"  ❌ {r['name']:<8} {r['error']}")
    if extra:
        print()
        if "btc_implied_usdkrw" in extra:
            print(f"  참고) 비트코인으로 본 환율: 1달러 ≈ {extra['btc_implied_usdkrw']:,.1f}원")
        if "kimchi_premium_pct" in extra:
            print(f"  참고) 김치 프리미엄(업비트 USDT 기준): {extra['kimchi_premium_pct']:+.2f}%")
    print()
    for w in warns:
        print(f"  ⚠️ {w}")
    verdict = {0: "✅ 원화·달러 모두 받아옴 → 대시보드 칸 만들기 가능",
               1: "⚠️ 한쪽 화폐만 받아옴 → 되는 쪽만으로 칸 구성 가능",
               2: "❌ 전부 실패 → 서버 네트워크/차단 확인 필요"}[code]
    print(f"\n결론: {verdict}")
    return code


if __name__ == "__main__":
    sys.exit(main())
