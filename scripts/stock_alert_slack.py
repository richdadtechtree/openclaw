#!/usr/bin/env python3
"""
stock_alert_slack.py — 관심 종목 급등락 알림을 슬랙으로도 보내는 재사용 모듈.

목적(HANDOFF.md C):
  1) 텔레그램(briefing-bot)뿐 아니라 **슬랙에도** 급등락 알림 전송.
  2) 시간대 게이팅(슬랙에만 적용):
       - 국장(숫자 코드 종목)  → KRX 정규장(평일 09:00~15:30 KST)에만 알림
       - 미장(영문 티커 종목)  → 24시간 알림
  3) 기존 stock 코드는 최소 수정. 이 파일을 ~/stock/stock/ 에 두고 import 만 하면 됨.

핵심: scheduler.alert_job 은 스냅샷을 직접 스캔하지 않고, 상태를 기억하는
TriggerEngine.check_custom_stocks() 가 돌려주는 **custom_events**(새로 기준을
넘은 종목만)로 알림을 보낸다. 슬랙도 반드시 이 events 를 기반으로 해야 중복
전송이 없다(스냅샷 재스캔 금지). event 구조:
    {"symbol": "005930", "stage": "...", "message": "…Telegram/Slack 공용 mrkdwn…"}

────────────────────────────────────────────────────────────────────────
서버 적용 방법
  1) 이 파일을 stock 폴더로 복사:
       cp ~/.openclaw/scripts/stock_alert_slack.py ~/stock/stock/
  2) scheduler.py 의 alert_job, 관심 종목 텔레그램을 보내는 지점 **바로 뒤**에
     아래를 추가(텔레그램 로직은 그대로 두고 슬랙만 추가):
       try:
           import stock_alert_slack as sas
           sas.notify_events(custom_events)   # 게이팅 통과분만 슬랙 전송
       except Exception as _e:
           print(f"[Warn] Slack custom alert failed: {_e}")
     → 위치: `sent = send_telegram_message(custom_message)` 다음 줄.
  3) 반영: systemctl --user restart stock-dashboard  (또는 scheduler 재실행)

.env (stock/.env 또는 ~/.openclaw/.env):
  SLACK_BOT_TOKEN        슬랙 봇 토큰 (xoxb-..., chat:write 스코프)
  SLACK_ALERT_CHANNEL    알림 전용 채널(C...) — 없으면 SLACK_BRIEFING_CHANNEL 로 폴백
  CUSTOM_ALERT_STEP      급등락 기준 %(기본 2.0) — 미리보기(main)용

단독 미리보기(지금 스냅샷 기준으로 게이팅·기준 통과 종목만 슬랙 전송):
  cd ~/stock/stock && venv/bin/python stock_alert_slack.py
  ※ 미리보기는 엔진의 '한 번만 발동' 상태를 모르므로 alert_job 연결엔 쓰지 말 것.
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
    return os.getenv("SLACK_ALERT_CHANNEL") or os.getenv("SLACK_STOCK_CHANNEL") or os.getenv("SLACK_BRIEFING_CHANNEL")


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
    """이 종목을 지금 슬랙으로 알려도 되는지.
    국장 → KRX 정규장에만, 미장 → 항상.
    (symbol 이 비었거나 숫자가 아니면 미장으로 간주 → 허용)
    """
    if is_kr(symbol):
        return krx_open(now)
    return True


# ── 슬랙 전송 ────────────────────────────────────────────────────────────────
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


# ── 고수준 API: alert_job 연결용 (엔진 events 기반) ──────────────────────────
def filter_events_for_slack(events, now=None):
    """엔진 events 중 지금 슬랙으로 보내도 되는 것만 남긴다(시간대 게이팅)."""
    now = now or now_kst()
    return [e for e in (events or []) if alert_allowed(e.get("symbol", ""), now)]


def notify_events(events, now=None):
    """TriggerEngine.check_custom_stocks() 가 준 events 를 슬랙으로 전송.

    - 게이팅(국장 장시간/미장 24h) 통과분만 전송.
    - event["message"] 는 텔레그램/슬랙 공용 mrkdwn 이라 그대로 재사용.
    - alert_job 에서 텔레그램 전송 뒤에 그냥 호출하면 됨.
    반환: 슬랙으로 보낸 종목 수(대상 없음/전송 실패면 0).
    """
    kept = filter_events_for_slack(events, now)
    if not kept:
        return 0
    now = now or now_kst()
    header = f"📢 *관심 종목 변동 알림* ({now:%Y-%m-%d %H:%M})"
    body = "\n\n".join(e["message"] for e in kept)
    return len(kept) if send_slack(header + "\n\n" + body) else 0


# ── 미리보기 전용(스냅샷 기반) — alert_job 에는 쓰지 말 것 ────────────────────
def format_alert_line(symbol, data, step=None):
    """한 종목의 미리보기 한 줄."""
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


def preview_moves(snapshot, now=None, step=None):
    """[미리보기 전용] 스냅샷에서 게이팅·기준 통과 종목만 한 메시지로 전송.

    엔진의 '한 번만 발동' 상태를 모르므로 반복 호출 시 중복 전송됨.
    반드시 수동 단독 실행에서만 사용. 반환: 전송한 종목 수.
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
    header = f"🔔 *관심 종목 급등락(미리보기)* ({now:%m-%d %H:%M} KST · ±{step:.0f}% 기준)"
    return len(lines) if send_slack("\n".join([header, *lines])) else 0


def main():
    """단독 실행(미리보기): 지금 스냅샷 기준으로 게이팅·기준 통과 종목만 슬랙 전송."""
    from market_data import get_custom_stocks_snapshot  # stock 폴더에서만 존재

    snap = get_custom_stocks_snapshot(use_cache=False)
    now = now_kst()
    sent = preview_moves(snap, now)
    if sent:
        print(f"✅ 슬랙 전송 성공 — {sent}개 종목")
    else:
        gated = [s for s in snap if not alert_allowed(s, now)]
        print("ℹ️ 전송할 알림 없음 "
              f"(기준 미달이거나 장시간 게이팅). 게이팅된 국장 종목: {gated or '없음'}")


if __name__ == "__main__":
    main()
