#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_briefing.py — GYM종국(김종국) 데일리/주간 브리핑 생성기

무엇을 하나:
  1) PT 대시보드 DB(~/pt_data/pt.db)에서 운동/식단/컨디션 기록을 읽는다.
  2) 김종국(GYM종국) 말투로 데일리 또는 주간 브리핑 텍스트를 만든다. (규칙 기반, AI 모델 불필요)
  3) briefings 테이블에 저장한다 → PT 웹 대시보드 "📢 김종국 브리핑" 섹션에 바로 표시.
  4) 슬랙 keepgoing 채널로 전송한다 → 종국이가 직접 말하는 것처럼.

사용:
  python3 pt_briefing.py daily      # 오늘 하루 데일리 브리핑
  python3 pt_briefing.py weekly     # 최근 7일 주간 브리핑
  옵션:
    --no-slack   슬랙 전송 생략(DB 저장만)
    --no-db      DB 저장 생략(슬랙 전송만)
    --print      만든 브리핑을 표준출력에 찍기(미리보기)
    --date YYYY-MM-DD   기준 날짜 지정(기본: 오늘, KST)

필요 (.env, openclaw 루트 또는 ~/stock/stock/.env):
  SLACK_BOT_TOKEN_KEEPGOING   종국이(keepgoing) 봇 토큰 (없으면 SLACK_BOT_TOKEN 로 폴백)
  SLACK_KEEPGOING_CHANNEL     종국이 채널 ID (없으면 기본값 C0BMN9FN073)
  PT_PROTEIN_GOAL             하루 단백질 목표 g (기본 100)
  PT_SLEEP_MIN                최소 수면 시간 (기본 6)
"""
import os
import sys
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pt_challenges as chal

DB_PATH = Path.home() / "pt_data" / "pt.db"
DEFAULT_KEEPGOING_CHANNEL = "C0BMN9FN073"


# ── .env 로딩 (pt_dashboard.py 와 동일한 다중 경로 훑기) ──────────────────────
def load_env():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, ".env"),
        os.path.join(os.path.dirname(here), ".env"),   # openclaw 루트/.env
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
        try:
            with open(rp, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass


# ── DB 헬퍼 ──────────────────────────────────────────────────────────────────
def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def ensure_briefings_table(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS briefings ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, "
        "type TEXT NOT NULL DEFAULT 'daily', content TEXT NOT NULL, "
        "created_at TEXT NOT NULL)")


def q(con, sql, params=()):
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    except Exception:
        return []


def q_one(con, sql, params=()):
    rows = q(con, sql, params)
    return rows[0] if rows else {}


# ── 데이터 집계 ──────────────────────────────────────────────────────────────
def workout_streak(con, ref):
    """ref 날짜부터 거꾸로 연속 운동일 수."""
    rows = q(con, "SELECT DISTINCT date FROM workouts ORDER BY date DESC")
    streak, check = 0, ref
    for r in rows:
        try:
            rd = date.fromisoformat(r["date"])
        except Exception:
            continue
        if rd == check:
            streak += 1
            check -= timedelta(days=1)
        elif rd < check:
            break
    return streak


def fmt_workout(w):
    parts = [w.get("exercise", "운동")]
    detail = []
    if w.get("sets"):
        detail.append(f"{w['sets']}세트")
    if w.get("reps"):
        detail.append(f"{w['reps']}회")
    if w.get("weight_kg"):
        detail.append(f"{w['weight_kg']}kg")
    if detail:
        parts.append("(" + " · ".join(detail) + ")")
    return " ".join(parts)


# ── 데일리 브리핑 ────────────────────────────────────────────────────────────
def build_daily(con, ref):
    protein_goal = float(os.getenv("PT_PROTEIN_GOAL", "100"))
    sleep_min = float(os.getenv("PT_SLEEP_MIN", "6"))
    d = ref.isoformat()

    workouts = q(con, "SELECT exercise, sets, reps, weight_kg FROM workouts "
                      "WHERE date=? ORDER BY id", (d,))
    diet = q(con, "SELECT meal, items, protein_g FROM diet WHERE date=? ORDER BY id", (d,))
    vital = q_one(con, "SELECT weight_kg, sleep_hours, condition, alcohol "
                       "FROM vitals WHERE date=?", (d,))
    streak = workout_streak(con, ref)
    protein_total = sum((x.get("protein_g") or 0) for x in diet)

    L = []
    sleep_h = vital.get("sleep_hours") if vital else None
    has_vital = bool(vital)

    L.append(f"💪 *GYM종국 데일리 브리핑* — {ref.strftime('%m월 %d일 (%a)')}")
    L.append("")

    # ── 오늘 기록 요약 ───────────────────────────────────────────────
    L.append("📋 *오늘 기록*")
    if workouts:
        names = ", ".join(fmt_workout(w) for w in workouts)
        L.append(f"  • 운동: {len(workouts)}개 — {names}")
    else:
        L.append("  • 운동: 기록 없음")
    if diet:
        items = ", ".join((f"[{m['meal']}] " if m.get('meal') else "") + (m.get('items', '') or "")
                          for m in diet)
        prot = f" (단백질 {protein_total:.0f}g)" if protein_total > 0 else " (단백질 미기록)"
        L.append(f"  • 식단: {items}{prot}")
    else:
        L.append("  • 식단: 기록 없음")
    if has_vital:
        bits = []
        if vital.get("weight_kg"):
            bits.append(f"체중 {vital['weight_kg']}kg")
        if sleep_h is not None:
            bits.append(f"수면 {sleep_h}h")
        if vital.get("condition"):
            bits.append(f"컨디션 {vital['condition']}")
        if vital.get("alcohol"):
            bits.append("음주 O")
        if bits:
            L.append("  • 컨디션: " + " · ".join(bits))
    L.append("")

    # ── 분석: 잘한 점 / 아쉬운 점 / 개선할 점 ─────────────────────────
    goods, bads, fixes = [], [], []

    # 운동
    if workouts:
        goods.append(f"운동 {len(workouts)}개 해냈어. 이거 자체가 제일 잘한 거야 ㅎ")
        if streak >= 2:
            goods.append(f"{streak}일 연속 유지 중 🔥 습관 잡히는 소리 들린다 ㅎ")
    else:
        bads.append("오늘 운동 기록이 없어. 안 한 거면 그게 제일 아쉬운 거야 ㅎ")
        fixes.append("내일은 딱 40분. 후면(등/어깨 뒤) 먼저 → 전면 → 마무리. 집이면 스쿼트+푸시업이라도.")

    # 단백질
    if protein_total >= protein_goal:
        goods.append(f"단백질 {protein_total:.0f}g 챙겼다 👍 운동은 먹는 것까지가 운동이야.")
    elif protein_total > 0:
        need = protein_goal - protein_total
        bads.append(f"단백질이 목표({protein_goal:.0f}g)보다 {need:.0f}g 모자라.")
        fixes.append(f"내일은 단백질 {need:.0f}g 더 — 계란/닭가슴살/두부/그릭요거트로 채워 ㅎ")
    elif diet:
        fixes.append("먹은 건 적었는데 단백질 g수가 없네. g수까지 적어줘야 내가 계산해주지 ㅎ")
    else:
        bads.append("식단 기록이 아예 없어. 굶었으면 그게 제일 나빠. 굶지 마 ㅎ")
        fixes.append("끼니마다 뭘 먹었는지 한 줄이라도 남겨. 종류만 바꿔도 몸 바뀐다.")

    # 수면
    if sleep_h is not None:
        if sleep_h >= sleep_min:
            goods.append(f"수면 {sleep_h}h. 잘 잤어 — 잠이 곧 회복이고 근육이야 ㅎ")
        else:
            bads.append(f"수면 {sleep_h}h밖에 안 됐어. {sleep_min:.0f}시간은 자야 근육이 큰다.")
            fixes.append("오늘은 폰 내려놓고 30분 일찍 눕자. 회복도 훈련이야.")

    # 술
    if has_vital and vital.get("alcohol"):
        bads.append("술 마셨네 ㅎ... 몸이 회복을 못 해.")
        fixes.append("벌칙: 내일 유산소 30분 추가다. 빠르게 걷기든 자전거든. 각오해 ㅎ")

    # 컨디션
    if has_vital and vital.get("condition") in ("나쁨", "안좋음", "피곤"):
        fixes.append("컨디션 별로면 무리하지 마. 쉬는 것도 운동이야. 회복 우선.")

    if not goods:
        goods.append("음... 오늘은 콕 집어 칭찬할 게 잘 안 보여 ㅎ 내일은 하나라도 만들자.")
    if not bads:
        bads.append("딱히 잘못한 거 없어. 아주 깔끔했어 ㅎ 이대로만 가.")
    if not fixes:
        fixes.append("지금 페이스 그대로 유지. 꾸준함이 최고의 무기야 ㅎ")

    L.append("✅ *잘한 점*")
    for g in goods:
        L.append(f"  • {g}")
    L.append("")
    L.append("❌ *아쉬운 점 / 잘못한 점*")
    for b in bads:
        L.append(f"  • {b}")
    L.append("")
    L.append("🎯 *앞으로 개선할 점 (내일 미션)*")
    for f in fixes:
        L.append(f"  • {f}")
    L.append("")

    # ── 한마디 ───────────────────────────────────────────────────────
    if workouts and protein_total >= protein_goal and (sleep_h is None or sleep_h >= sleep_min):
        L.append("🗣️ 오~ 오늘 맛있었지? ㅎ 운동·식단·수면 다 잡았어. 이게 완성이야. 이대로 가자 ㅎ")
    elif workouts:
        L.append("🗣️ 운동은 해냈어 ㅎ 나머지 하나씩만 더 챙기면 된다. 잘하고 있어, 믿는다.")
    else:
        L.append("🗣️ 힘든 건 몸이 아니라 마음이야. 오늘부터 운동이 아니라 새로운 삶을 산다고 생각해. "
                 "내일 딱 40분만. 약속 ㅎ")

    return "\n".join(L)


# ── 주간 브리핑 ──────────────────────────────────────────────────────────────
def build_weekly(con, ref):
    protein_goal = float(os.getenv("PT_PROTEIN_GOAL", "100"))
    sleep_min = float(os.getenv("PT_SLEEP_MIN", "6"))
    start = ref - timedelta(days=6)
    s, e = start.isoformat(), ref.isoformat()

    wdays = [r["date"] for r in q(
        con, "SELECT DISTINCT date FROM workouts WHERE date BETWEEN ? AND ?", (s, e))]
    workout_cnt = q_one(
        con, "SELECT COUNT(*) n FROM workouts WHERE date BETWEEN ? AND ?", (s, e)).get("n", 0)
    diet_rows = q(con, "SELECT date, protein_g FROM diet WHERE date BETWEEN ? AND ?", (s, e))
    vit_rows = q(con, "SELECT date, weight_kg, sleep_hours, alcohol FROM vitals "
                      "WHERE date BETWEEN ? AND ? ORDER BY date", (s, e))
    streak = workout_streak(con, ref)

    # 단백질: 날짜별 합계 평균 (단백질 g수가 실제로 기록된 날만 집계)
    prot_by_day = {}
    for r in diet_rows:
        g = r.get("protein_g")
        if g:
            prot_by_day[r["date"]] = prot_by_day.get(r["date"], 0) + g
    avg_protein = (sum(prot_by_day.values()) / len(prot_by_day)) if prot_by_day else 0
    diet_logged_days = len({r["date"] for r in diet_rows})

    sleeps = [r["sleep_hours"] for r in vit_rows if r.get("sleep_hours") is not None]
    avg_sleep = (sum(sleeps) / len(sleeps)) if sleeps else None
    alcohol_days = sum(1 for r in vit_rows if r.get("alcohol"))
    weights = [(r["date"], r["weight_kg"]) for r in vit_rows if r.get("weight_kg") is not None]

    L = []
    L.append(f"📅 *GYM종국 주간 브리핑* — {start.strftime('%m/%d')} ~ {ref.strftime('%m/%d')}")
    L.append("")

    # 운동
    n = len(set(wdays))
    L.append(f"🏋️ *운동* — 이번 주 {n}일 / 총 {workout_cnt}세션")
    if n >= 3:
        L.append("  오~ 주 3회 넘었어 ㅎ 습관 잡히고 있다. 이게 제일 중요해.")
    elif n > 0:
        L.append("  아직 부족해 ㅎ 목표는 주 3회다. 다음 주는 하루 더 해보자.")
    else:
        L.append("  야... 이번 주 운동 기록이 하나도 없어 ㅎ 우리 진지하게 얘기 좀 하자 ㅎ")
    if streak >= 2:
        L.append(f"  🔥 현재 {streak}일 연속 유지 중!")
    L.append("")

    # 식단
    if prot_by_day:
        L.append(f"🍚 *식단* — 하루 평균 단백질 약 {avg_protein:.0f}g "
                 f"(단백질 기록 {len(prot_by_day)}일)")
        if avg_protein < protein_goal:
            L.append(f"  목표 {protein_goal:.0f}g 대비 부족한 날이 많았어. 단백질에 더 신경 써 ㅎ")
        else:
            L.append("  단백질 잘 챙겼다 👍 근육은 배신 안 해.")
    elif diet_logged_days:
        L.append(f"🍚 *식단* — 이번 주 식사 {diet_logged_days}일 기록. 근데 단백질 g수가 안 적혀 있어.")
        L.append("  뭘 얼마나 먹었는지 g수까지 적어줘야 제대로 코칭하지 ㅎ")
    else:
        L.append("🍚 *식단* — 기록이 거의 없네. 뭘 먹었는지 알아야 코칭을 하지 ㅎ")
    L.append("")

    # 수면
    if avg_sleep is not None:
        L.append(f"😴 *수면* — 하루 평균 {avg_sleep:.1f}시간")
        if avg_sleep < sleep_min:
            L.append(f"  {sleep_min:.0f}시간 밑이야. 잠이 곧 회복이고 근육이야. 일찍 자 ㅎ")
    L.append("")

    # 술
    if alcohol_days:
        L.append(f"🍺 *음주* — 이번 주 {alcohol_days}일")
        if alcohol_days >= 2:
            L.append("  ㅎ... 형준아 ㅎ 우리 진지하게 얘기 좀 하자 ㅎ 다음 주는 줄이자.")
        else:
            L.append("  한 번은 그럴 수 있어 ㅎ 대신 유산소로 갚았지? ㅎ")
        L.append("")

    # 체중 변화
    if len(weights) >= 2:
        d0 = weights[0][1]
        d1 = weights[-1][1]
        diff = d1 - d0
        arrow = "▼" if diff < 0 else ("▲" if diff > 0 else "―")
        L.append(f"⚖️ *체중* — {d0}kg → {d1}kg ({arrow} {abs(diff):.1f}kg)")
        L.append("")

    # 다음 주 미션
    L.append("🎯 *다음 주 미션*")
    L.append("  1. 운동 주 3회 이상 (40분 루틴이면 충분)")
    L.append(f"  2. 하루 단백질 {protein_goal:.0f}g 챙기기")
    L.append(f"  3. 매일 {sleep_min:.0f}시간 이상 자기")
    L.append("")
    L.append("🗣️ 운동은 꾸준히 하면 배신 안 해. 아이들이랑 뛰어놀려면 체력이 있어야지 ㅎ "
             "다음 주도 가보자 ㅎ")

    return "\n".join(L)


# ── 저장 / 전송 ──────────────────────────────────────────────────────────────
def save_to_db(con, ref, btype, content):
    ensure_briefings_table(con)
    con.execute(
        "INSERT INTO briefings (date, type, content, created_at) VALUES (?,?,?,?)",
        (ref.isoformat(), btype, content, datetime.now().isoformat()))
    con.commit()


def post_slack(content):
    token = os.getenv("SLACK_BOT_TOKEN_KEEPGOING") or os.getenv("SLACK_BOT_TOKEN")
    channel = os.getenv("SLACK_KEEPGOING_CHANNEL") or DEFAULT_KEEPGOING_CHANNEL
    if not token:
        print("[Warn] 슬랙 토큰 없음(SLACK_BOT_TOKEN_KEEPGOING/SLACK_BOT_TOKEN) → 슬랙 전송 생략")
        return False
    try:
        import requests
    except Exception:
        print("[Warn] requests 미설치 → 슬랙 전송 생략")
        return False
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        json={"channel": channel, "text": content,
              "unfurl_links": False, "unfurl_media": False},
        timeout=30,
    ).json()
    if not r.get("ok"):
        print(f"[Error] 슬랙 전송 실패: {r}")
        return False
    return True


def main():
    args = sys.argv[1:]
    btype = "daily"
    for a in args:
        if a in ("daily", "weekly"):
            btype = a
    no_slack = "--no-slack" in args
    no_db = "--no-db" in args
    do_print = "--print" in args

    ref = date.today()
    if "--date" in args:
        try:
            ref = date.fromisoformat(args[args.index("--date") + 1])
        except Exception:
            print("[Warn] --date 형식 오류, 오늘 날짜 사용")

    load_env()

    if not DB_PATH.is_file():
        print(f"[Warn] DB 파일 없음: {DB_PATH} → 빈 기록 기준으로 브리핑 생성")

    con = get_db()
    content = build_weekly(con, ref) if btype == "weekly" else build_daily(con, ref)
    # 슬랙은 *볼드* mrkdwn 사용, 웹 대시보드는 별표 없는 평문이 깔끔하다.
    content_web = content.replace("*", "")

    if do_print:
        print(content_web)
        print("─" * 40)

    if not no_db:
        try:
            save_to_db(con, ref, btype, content_web)
            print(f"✅ DB 저장 완료 (briefings, type={btype}, date={ref})")
        except Exception as ex:
            print(f"[Error] DB 저장 실패: {ex}")

    # 챌린지 마일스톤 새로 달성했는지 확인 → DB 기록(웹 팝업용) + 슬랙 축하(종국이가 직접 말하듯).
    # 데일리 잡에서만 확인(매일 21시 cron이 이미 있어 별도 스케줄 불필요).
    new_achievements = []
    if btype == "daily" and not no_db:
        try:
            new_achievements = chal.check_and_record_achievements(con, ref)
        except Exception as ex:
            print(f"[Error] 챌린지 달성 확인 실패: {ex}")
    con.close()

    if not no_slack:
        if post_slack(content):
            print("✅ 슬랙 전송 완료 (keepgoing)")
        for ach in new_achievements:
            congrats = f"🎉 *{ach['kind_label']} 달성! ({ach['milestone']})*\n{ach['message']}"
            if post_slack(congrats):
                print(f"✅ 챌린지 축하 슬랙 전송: {ach['kind']} {ach['milestone']}")
    elif new_achievements:
        for ach in new_achievements:
            print(f"[Info] 챌린지 달성(슬랙 생략): {ach['kind']} {ach['milestone']}")

    print(f"완료: {btype} 브리핑 ({ref})")


if __name__ == "__main__":
    main()
