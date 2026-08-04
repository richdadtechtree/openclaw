#!/usr/bin/env python3
"""
test_slack_alert.py — 오늘 관심 종목 변동(±2% 급등락 기준)을 슬랙으로 테스트 전송.

stock 폴더에서 실행:  cd ~/stock/stock && python test_slack_alert.py

- 국장(숫자 코드)/미장(영문 티커)을 나눠서 오늘 등락률 표시
- ±기준%(CUSTOM_ALERT_STEP, 기본 2%) 이상이면 급등/급락 강조
- KRX 장 열림/닫힘도 표시 (국장 시간대 제어 로직 미리보기)
- 채널: SLACK_ALERT_CHANNEL 있으면 그걸, 없으면 SLACK_BRIEFING_CHANNEL
"""
import os
from datetime import datetime

import requests
from market_data import get_custom_stocks_snapshot  # import 시 stock/.env 도 로드됨

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = None

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_ALERT_CHANNEL") or os.getenv("SLACK_BRIEFING_CHANNEL")
try:
    STEP = float(os.getenv("CUSTOM_ALERT_STEP", os.getenv("CUSTOM_ALERT_THRESHOLD", "2.0")))
except ValueError:
    STEP = 2.0


def now_kst():
    return datetime.now(KST) if KST else datetime.now()


def krx_open(now=None):
    """KRX 정규장(평일 09:00~15:30 KST) 여부."""
    now = now or now_kst()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 15 * 60 + 30


def send_slack(text):
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL:
        print("[Error] SLACK_BOT_TOKEN 또는 채널(.env)이 없습니다.")
        return False
    try:
        r = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                     "Content-Type": "application/json; charset=utf-8"},
            json={"channel": SLACK_CHANNEL, "text": text}, timeout=15,
        ).json()
        if not r.get("ok"):
            print("[Error] slack:", r)
        return r.get("ok")
    except Exception as e:
        print("[Error] slack 예외:", e)
        return False


def fmt(sym, d):
    cr = d["change_rate"]
    price = f"{d['current']:,.0f}원" if sym.isdigit() else f"${d['current']:,.2f}"
    if cr >= STEP:
        emoji, tag = "🚀", " *(급등)*"
    elif cr <= -STEP:
        emoji, tag = "📉", " *(급락)*"
    else:
        emoji, tag = "▪️", ""
    return f"{emoji} {d['name']} ({sym}): {cr:+.2f}% / {price}{tag}"


def main():
    snap = get_custom_stocks_snapshot(use_cache=False)
    kr = {s: d for s, d in snap.items() if s.isdigit()}
    us = {s: d for s, d in snap.items() if not s.isdigit()}
    now = now_kst()
    open_now = krx_open(now)

    parts = [f"🧪 *관심 종목 변동 테스트* ({now:%Y-%m-%d %H:%M} KST)"]
    parts.append(f"\n*🇰🇷 국장* — KRX 장 {'🟢 열림' if open_now else '🔴 닫힘 (닫히면 실제 알림 안 감)'}")
    parts += ([fmt(s, d) for s, d in kr.items()] or ["(데이터 없음)"])
    parts.append("\n*🇺🇸 미장* — 항상 알림")
    parts += ([fmt(s, d) for s, d in us.items()] or ["(데이터 없음)"])
    parts.append(f"\n기준: ±{STEP:.0f}% 이상 → 급등/급락 알림")

    ok = send_slack("\n".join(parts))
    print("✅ 슬랙 전송 성공!" if ok else "❌ 슬랙 전송 실패")


if __name__ == "__main__":
    main()
