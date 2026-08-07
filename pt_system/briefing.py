#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_system/briefing.py — DB 기반 일간/주간 PT 브리핑 (규칙 기반, AI 미사용)

DB(pt.sqlite)에 쌓인 운동/식단/바이탈을 집계해 한국어 브리핑 텍스트를 만든다.
규칙 기반이라 모델 상태와 무관하게 항상 동작한다. --slack 을 주면 슬랙 채널로도 전송.

사용:
  python3 pt_system/briefing.py daily  [YYYY-MM-DD]     # 하루 요약(기본: 오늘)
  python3 pt_system/briefing.py weekly [YYYY-MM-DD]     # 끝나는 날 기준 7일
  옵션: --slack  (슬랙 전송), --days N (weekly 기간)

슬랙 전송 env (.openclaw/.env):
  SLACK_BOT_TOKEN      xoxb-...
  SLACK_PT_CHANNEL     PT 브리핑 채널 (없으면 SLACK_BRIEFING_CHANNEL 폴백)
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


# ── 브리핑 텍스트 ────────────────────────────────────────────
def daily_text(con, date=None):
    date = date or db.today_str()
    rec = db.records_for_date(con, date)
    c = db.counts_for_date(con, date)
    since = db.days_since_workout(con)
    lines = [f"🏋️ *PT 일간 브리핑* — {date}", ""]

    # 운동
    if rec["workouts"]:
        lines.append("*운동*")
        for w in rec["workouts"]:
            parts = [w.get("type") or "운동", w.get("detail") or ""]
            meta = []
            if w.get("duration_min"):
                meta.append(f"{w['duration_min']}분")
            if w.get("intensity"):
                meta.append(w["intensity"])
            tail = f" ({', '.join(meta)})" if meta else ""
            lines.append(f"• {' - '.join(p for p in parts if p)}{tail}")
    else:
        lines.append("*운동* — 기록 없음 ❗")

    # 식단
    if rec["meals"]:
        lines.append("")
        lines.append("*식단*")
        total_kcal = sum(m["kcal"] for m in rec["meals"] if m.get("kcal"))
        total_pro = sum(m["protein_g"] for m in rec["meals"] if m.get("protein_g"))
        for m in rec["meals"]:
            extra = []
            if m.get("kcal"):
                extra.append(f"{m['kcal']}kcal")
            if m.get("protein_g"):
                extra.append(f"단백질 {m['protein_g']:g}g")
            tail = f" ({', '.join(extra)})" if extra else ""
            lines.append(f"• {m.get('meal') or '식사'}: {m.get('items') or ''}{tail}")
        agg = []
        if total_kcal:
            agg.append(f"총 {total_kcal}kcal")
        if total_pro:
            agg.append(f"단백질 {total_pro:g}g")
        if agg:
            lines.append(f"  → {' / '.join(agg)}")
    else:
        lines.append("")
        lines.append("*식단* — 기록 없음")

    # 바이탈
    if rec["vitals"]:
        lines.append("")
        lines.append("*컨디션/바이탈*")
        for v in rec["vitals"]:
            bits = []
            if v.get("weight_kg"):
                bits.append(f"체중 {v['weight_kg']:g}kg")
            if v.get("sleep_h"):
                bits.append(f"수면 {v['sleep_h']:g}h")
            if v.get("condition"):
                bits.append(f"컨디션 {v['condition']}")
            if bits:
                lines.append("• " + ", ".join(bits))

    # 한마디 (규칙 기반)
    lines.append("")
    if c["workouts"] == 0:
        if since is None:
            lines.append("💬 아직 운동 기록이 없어요. 오늘 가볍게라도 시작해봐요.")
        elif since >= 2:
            lines.append(f"💬 운동 안 한 지 {since}일째! 오늘은 꼭 몸을 움직입시다. 💪")
        else:
            lines.append("💬 오늘 운동 기록이 비어 있어요. 짧게라도 채워봐요.")
    else:
        lines.append("💬 오늘도 기록 완료. 이 페이스 유지해요. 👍")
    return "\n".join(lines)


def weekly_text(con, end=None, days=7):
    st = db.weekly_stats(con, days=days, end=end)
    lines = [f"📅 *PT 주간 리포트* — {st['start']} ~ {st['end']}", ""]
    lines.append(f"• 운동한 날: *{st['workout_days']}/{days}일*  "
                 f"(세션 {st['workout_count']}회, 총 {st['workout_minutes']}분)")
    lines.append(f"• 식단 기록: {st['meal_count']}건")
    if st["avg_sleep_h"] is not None:
        lines.append(f"• 평균 수면: {st['avg_sleep_h']}시간")
    if st["weight_first"] is not None and st["weight_last"] is not None:
        diff = round(st["weight_last"] - st["weight_first"], 1)
        arrow = "▼" if diff < 0 else ("▲" if diff > 0 else "―")
        lines.append(f"• 체중: {st['weight_first']:g} → {st['weight_last']:g}kg "
                     f"({arrow}{abs(diff):g}kg)")
    lines.append("")

    # 평가 (규칙 기반)
    lines.append("*코멘트*")
    if st["workout_days"] >= 3:
        lines.append("• ✅ 주 3회 목표 달성! 좋은 흐름이에요.")
    elif st["workout_days"] == 0:
        lines.append("• ❗ 이번 주 운동 기록이 없어요. 다음 주는 한 번이라도 시작합시다.")
    else:
        lines.append(f"• 운동 {st['workout_days']}회 — 목표(주3회)까지 "
                     f"{max(0, 3 - st['workout_days'])}회 남았어요.")
    if st["avg_sleep_h"] is not None and st["avg_sleep_h"] < 6:
        lines.append("• 😴 평균 수면이 6시간 미만이에요. 회복을 위해 수면을 늘려봐요.")
    if st["meal_count"] == 0:
        lines.append("• 🍽️ 식단 기록이 없어요. 한 끼라도 남기면 피드백이 정확해져요.")
    return "\n".join(lines)


# ── 슬랙 전송 ────────────────────────────────────────────────
def _load_env():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ~/.openclaw
    path = os.path.join(base, ".env")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def post_slack(text):
    _load_env()
    token = os.getenv("SLACK_BOT_TOKEN")
    channel = os.getenv("SLACK_PT_CHANNEL") or os.getenv("SLACK_BRIEFING_CHANNEL")
    if not token or not channel:
        print("[Warn] SLACK_BOT_TOKEN 또는 SLACK_PT_CHANNEL(/SLACK_BRIEFING_CHANNEL) 없음 — 슬랙 전송 생략")
        return False
    try:
        import requests
    except Exception:
        print("[Warn] requests 미설치 — 슬랙 전송 생략")
        return False
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        json={"channel": channel, "text": text,
              "unfurl_links": False, "unfurl_media": False},
        timeout=30,
    ).json()
    if not r.get("ok"):
        print(f"[Error] 슬랙 전송 실패: {r}")
        return False
    # 슬랙 발신 로그(뷰어용)와 호환 — 있으면 기록
    try:
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        from slack_log import log_slack
        log_slack(text, source="pt-briefing", channel=channel)
    except Exception:
        pass
    print("✅ 슬랙 전송 성공")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["daily", "weekly"])
    ap.add_argument("date", nargs="?", default=None, help="YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--slack", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    db.init_db()
    con = db.connect(readonly=True)
    try:
        if args.mode == "daily":
            text = daily_text(con, args.date)
        else:
            text = weekly_text(con, end=args.date, days=args.days)
    finally:
        con.close()

    print(text)
    if args.slack:
        post_slack(text)


if __name__ == "__main__":
    main()
