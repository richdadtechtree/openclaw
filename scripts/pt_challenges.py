#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_challenges.py — 챌린지(연속 운동·금주) 계산 + 마일스톤 달성 기록 공용 모듈.

pt_dashboard.py(웹 대시보드 /api/challenges, /api/achievements/*)와
pt_briefing.py(데일리 cron)가 이 모듈을 같이 써서 기준을 하나로 유지한다.
DB: ~/pt_data/pt.db (workouts, vitals 테이블은 이미 존재한다고 가정)
"""
from datetime import date, timedelta, datetime

GOAL_PER_WEEK = 3
SOBER_MILESTONES = [7, 14, 30, 66, 100]
WEEK_MILESTONES = [2, 4, 8, 12, 16]

SOBER_REWARDS = {
    7:  "🎁 7일 달성! 오늘 치팅밀 하나 허락 ㅎ … 근데 딱 하나만, 내일부터 다시 간다 ㅎ",
    14: "🎁 2주! 오늘 딱 한 잔은 봐준다 ㅎ … 근데 여기서 무너지면 처음부터야. 그냥 이어가는 게 이득 ㅎ",
    30: "🎁 한 달! 먹고픈 거 하루 마음껏 먹어 ㅎ … 30일 한 사람이 여기서 멈춰? 계속 간다 ㅎ",
    66: "🏆 66일, 습관 완성! 이건 이제 네 삶이야. 아이들이랑 오래 뛰어놀 몸 만드는 중 ㅎ",
    100: "🏆 100일!! 건강한 아빠가 최고의 아빠야 ㅎ 멈출 이유가 없지, 계속 ㅎ",
}
WEEK_REWARDS = {
    2:  "🎁 2주 연속 주3회! 이번 주말은 아이들이랑 신나게 놀아 ㅎ … 다음 주도 간다 ㅎ",
    4:  "🎁 한 달 개근! 먹고픈 거 하나 허락 ㅎ … 근데 습관은 이제부터야, 이어가자 ㅎ",
    8:  "🎁 8주! 몸 바뀌는 게 보이지? ㅎ 하루 쉬어가도 좋아 … 대신 바로 복귀 ㅎ",
    12: "🏆 12주! 이제 운동이 네 일상이야. 계속 ㅎ",
    16: "🏆 16주 완주! 아이들이랑 30년 더 뛰어놀 체력, 네가 만든 거야 ㅎ 멈추지마 ㅎ",
}

KIND_WORKOUT = "workout_week"
KIND_SOBER = "sober"
KIND_LABELS = {KIND_WORKOUT: "🔥 연속 운동 챌린지", KIND_SOBER: "🚫🍺 금주 챌린지"}


def ensure_tables(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        milestone INTEGER NOT NULL,
        date TEXT NOT NULL,
        message TEXT NOT NULL,
        seen INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS achievement_state (
        kind TEXT PRIMARY KEY,
        last_milestone INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT
    );
    """)
    con.commit()


def _next_milestone(value, milestones):
    for m in milestones:
        if value < m:
            return m, m - value
    return None, 0


def compute_challenges(con, today=None):
    """오버뷰 카드·검사기가 공용으로 쓰는 챌린지 현황 계산. today 는 date 객체."""
    today = today or date.today()

    wdates = set()
    for r in con.execute("SELECT DISTINCT date FROM workouts"):
        try:
            wdates.add(date.fromisoformat(r["date"]))
        except (ValueError, TypeError, IndexError, KeyError):
            pass

    # 요즘 연속(일)
    day_streak = 0
    check = today if today in wdates else today - timedelta(days=1)
    while check in wdates:
        day_streak += 1
        check -= timedelta(days=1)

    # 주별 운동일수(월요일 시작 주)
    def week_start(d):
        return d - timedelta(days=d.weekday())

    week_counts = {}
    for wd in wdates:
        ws = week_start(wd)
        week_counts[ws] = week_counts.get(ws, 0) + 1

    this_week = week_start(today)
    this_week_count = week_counts.get(this_week, 0)
    this_week_success = this_week_count >= GOAL_PER_WEEK

    week_streak = 1 if this_week_success else 0
    wk = this_week - timedelta(days=7)
    while week_counts.get(wk, 0) >= GOAL_PER_WEEK:
        week_streak += 1
        wk -= timedelta(days=7)

    w_next, w_remain = _next_milestone(week_streak, WEEK_MILESTONES)

    # 금주 연속일 — 마지막 음주일(alcohol=1) 다음날부터 오늘까지
    last_drink_row = con.execute(
        "SELECT date FROM vitals WHERE alcohol=1 AND date <= ? ORDER BY date DESC LIMIT 1",
        (today.isoformat(),)).fetchone()
    last_drink = last_drink_row["date"] if last_drink_row else None
    if last_drink:
        try:
            sober_days = max((today - date.fromisoformat(last_drink)).days, 0)
        except (ValueError, TypeError):
            sober_days = 0
    else:
        base_row = con.execute(
            "SELECT MIN(d) AS d FROM (SELECT date d FROM workouts UNION SELECT date d FROM vitals)").fetchone()
        base = base_row["d"] if base_row else None
        try:
            sober_days = max((today - date.fromisoformat(base)).days, 0) if base else 0
        except (ValueError, TypeError):
            sober_days = 0

    s_next, s_remain = _next_milestone(sober_days, SOBER_MILESTONES)

    return {
        "workout": {
            "day_streak": day_streak,
            "week_streak": week_streak,
            "this_week_count": this_week_count,
            "this_week_success": this_week_success,
            "goal_per_week": GOAL_PER_WEEK,
            "next_goal": w_next,
            "remaining": w_remain,
            "reward_hint": WEEK_REWARDS.get(week_streak) if week_streak else None,
        },
        "sober": {
            "days": sober_days,
            "next_goal": s_next,
            "remaining": s_remain,
            "last_drink": last_drink,
            "reward_hint": SOBER_REWARDS.get(sober_days),
        },
    }


def check_and_record_achievements(con, today=None):
    """새로 넘어선 마일스톤(개인 최고 기록 경신)을 achievements 에 기록하고 리스트로 반환.
    같은 마일스톤은 한 번만 기록(연속이 끊겼다가 다시 그 값에 도달해도 재알림 없음 — 신기록만 축하).
    반환 항목: {kind, kind_label, milestone, message}
    """
    today = today or date.today()
    ensure_tables(con)
    data = compute_challenges(con, today)

    plan = [
        (KIND_WORKOUT, data["workout"]["week_streak"], WEEK_MILESTONES, WEEK_REWARDS),
        (KIND_SOBER, data["sober"]["days"], SOBER_MILESTONES, SOBER_REWARDS),
    ]

    new_achievements = []
    for kind, value, milestones, rewards in plan:
        reached = [m for m in milestones if value >= m]
        if not reached:
            continue
        top = max(reached)
        row = con.execute(
            "SELECT last_milestone FROM achievement_state WHERE kind=?", (kind,)).fetchone()
        last = row["last_milestone"] if row else 0
        if top <= last:
            continue
        message = rewards.get(top, f"{top} 달성! 계속 가자 ㅎ")
        now = datetime.now().isoformat()
        con.execute(
            "INSERT INTO achievements (kind,milestone,date,message,seen,created_at) VALUES (?,?,?,?,0,?)",
            (kind, top, today.isoformat(), message, now))
        con.execute(
            "INSERT INTO achievement_state (kind,last_milestone,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(kind) DO UPDATE SET last_milestone=excluded.last_milestone, updated_at=excluded.updated_at",
            (kind, top, now))
        new_achievements.append({
            "kind": kind, "kind_label": KIND_LABELS.get(kind, kind),
            "milestone": top, "message": message,
        })

    if new_achievements:
        con.commit()
    return new_achievements
