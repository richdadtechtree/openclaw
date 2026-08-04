#!/usr/bin/env python3
"""
stock_alert_slack.py — 관심 종목 급등락 알림을 슬랙으로도 보내는 재사용 모듈.

목적(HANDOFF.md C):
  1) 텔레그램(briefing-bot)뿐 아니라 **슬랙에도** 급등락 알림 전송.
  2) 시간대 게이팅:
       - 국장(숫자 코드 종목)  → KRX 정규장(평일 09:00~15:30 KST)에만 알림
       - 미장(영문 티커 종목)  → 24시간 알림
  3) 기존 stock 코드는 최소 수정. 이 파일을 ~/stock/stock/ 에 두고 import 만 하면 됨.

────────────────────────────────────────────────────────────────────────
서버 적용 방법
  1) 이 파일을 stock 폴더로 복사:
       cp ~/.openclaw/scripts/stock_alert_slack.py ~/stock/stock/
  2) scheduler.py 의 alert_job 안, 종목 하나가 기준을 넘어 **텔레그램을 보내는
     바로 그 지점 옆**에 아래 한 줄을 추가:
       import stock_alert_slack as sas
       sas.notify_move(symbol, snap[symbol])   # 게이팅은 내부에서 처리(막히면 조용히 skip)
     (snap = market_data.get_custom_stocks_snapshot() 결과 dict)
  3) 혹은 한 번에 여러 종목을 모아 보내려면:
       import stock_alert_slack as sas
       sas.notify_moves(snap)                  # 기준·게이팅 통과분만 한 메시지로 전송
  4) 반영: systemctl --user restart stock-dashboard  (또는 scheduler 재실행)

.env (stock/.env 또는 ~/.openclaw/.env):
  SLACK_BOT_TOKEN        슬랙 봇 토큰 (xoxb-..., chat:write 스코프)
  SLACK_ALERT_CHANNEL    알림 전용 채널(C...) — 없으면 SLACK_BRIEFING_CHANNEL 로 폴백
  CUSTOM_ALERT_STEP      급등락 기준 %(기본 2.0)

단독 테스트(실제로 지금 알림이 나갈 종목만 미리보기 전송):
  cd ~/stock/stock && venv/bin/python stock_alert_slack.py
"""
import os
from datetime import datetime

import requests

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:  # pragma: no cover - zoneinfo 없으면 로컬 시간 사용
    KST = None


# ── .env 로딩 (scheduler 가 이미 로드했으면 setdefault 라 덮어쓰지 않음) ──────────
def _load_env():
    """stock/.env 와 openclaw/.env 를 모두 훑어 os.environ 에 채운다(기존값 우선)."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
        os.path.expanduser("~/stock/stock/.env"),
        os.path.expanduser("~/.openclaw/.env"),
    ]
    seen = set()
    for path in candidates:
        rp = os.path.realpath(path)
        if rp in seen or not os.path.isfile(rp):
            continue
        seen.add(rp)
        with open(rp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _token():
    return os.getenv("SLACK_BOT_TOKEN")


def _channel():
    return os.getenv("SLACK_ALERT_CHANNEL") or os.getenv("SLACK_BRIEFING_CHANNEL")


def _step():
    try:
        return float(os.getenv("CUSTOM_ALERT_STEP",
                               os.getenv("CUSTOM_ALERT_THRESHOLD", "2.0")))
    except (TypeError, ValueError):
        return 2.0


# ── 시간대 게이팅 ────────────────────────────────────────────────────────────
def now_kst():
    return datetime.now(KST) if KST else datetime.now()


def is_kr(symbol):
    """국장(숫자 코드) 종목이면 True, 미장(영문 티커)이면 False."""
    return str(symbol).isdigit()


def krx_open(now=None):
    """KRX 정규장(평일 09:00~15:30 KST) 여부."""
    now = now or now_kst()
    if now.weekday() >= 5:  # 토(5)/일(6)
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 15 * 60 + 30


def alert_allowed(symbol, now=None):
    """이 종목을 지금 알려도 되는지.
    국장 → KRX 정규장에만, 미장 → 항상.
    """
    if is_kr(symbol):
        return krx_open(now)
    return True


# ── 포맷 / 전송 ──────────────────────────────────────────────────────────────
def format_alert_line(symbol, data, step=None):
    """한 종목의 알림 한 줄. (test_slack_alert.fmt 과 동일 규칙)"""
    step = _step() if step is None else step
    cr = data.get("change_rate", 0.0)
    cur = data.get("current", 0)
    price = f"{cur:,.0f}원" if is_kr(symbol) else f"${cur:,.2f}"
    if cr >= step:
        emoji, tag = "🚀", " *(급등)*"
    elif cr <= -step:
        emoji, tag = "📉", " *(급락)*"
    else:
        emoji, tag = "▪️", ""
    name = data.get("name", symbol)
    return f"{emoji} {name} ({symbol}): {cr:+.2f}% / {price}{tag}"


def send_slack(text):
    """슬랙 채널에 텍스트 전송. 성공 시 True."""
    token, channel = _token(), _channel()
    if not token or not channel:
        print("[stock_alert_slack] SLACK_BOT_TOKEN 또는 채널(.env)이 없습니다.")
        return False
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=utf-8"},
            json={"channel": channel, "text": text,
                  "unfurl_links": False, "unfurl_media": False},
            timeout=15,
        ).json()
        if not r.get("ok"):
            print("[stock_alert_slack] slack 오류:", r)
        return bool(r.get("ok"))
    except Exception as e:  # pragma: no cover - 네트워크 예외
        print("[stock_alert_slack] slack 예외:", e)
        return False


# ── 고수준 API (scheduler.alert_job 에서 호출) ───────────────────────────────
def notify_move(symbol, data, now=None, step=None):
    """종목 하나의 급등락을 슬랙으로 알림.

    게이팅(국장 장시간)과 기준(±step%)을 내부에서 검사하므로,
    alert_job 에서 텔레그램 전송 옆에 그냥 호출하면 됨.
    실제로 전송했을 때만 True.
    """
    step = _step() if step is None else step
    if not alert_allowed(symbol, now):
        return False
    cr = data.get("change_rate", 0.0)
    if abs(cr) < step:
        return False
    return send_slack(format_alert_line(symbol, data, step))


def notify_moves(snapshot, now=None, step=None):
    """스냅샷 전체에서 게이팅·기준을 통과한 종목만 모아 한 메시지로 전송.

    반환: 전송한 종목 수(전송 실패/대상 없음이면 0).
    """
    step = _step() if step is None else step
    now = now or now_kst()
    lines = []
    for symbol, data in snapshot.items():
        if not alert_allowed(symbol, now):
            continue
        if abs(data.get("change_rate", 0.0)) < step:
            continue
        lines.append(format_alert_line(symbol, data, step))
    if not lines:
        return 0
    header = f"🔔 *관심 종목 급등락* ({now:%m-%d %H:%M} KST · ±{step:.0f}% 기준)"
    return len(lines) if send_slack("\n".join([header, *lines])) else 0


def main():
    """단독 실행: 지금 스냅샷 기준으로 '실제 알림이 나갈' 종목만 슬랙에 전송."""
    from market_data import get_custom_stocks_snapshot  # stock 폴더에서만 존재

    snap = get_custom_stocks_snapshot(use_cache=False)
    now = now_kst()
    sent = notify_moves(snap, now)
    if sent:
        print(f"✅ 슬랙 전송 성공 — {sent}개 종목")
    else:
        gated = [s for s in snap if not alert_allowed(s, now)]
        print("ℹ️ 전송할 알림 없음 "
              f"(기준 미달이거나 장시간 게이팅). 게이팅된 국장 종목: {gated or '없음'}")


if __name__ == "__main__":
    main()
