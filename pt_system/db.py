#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_system/db.py — PT 트레이너 기록 저장소 (sqlite, stdlib 전용)

슬랙에 입력한 운동/식단/바이탈(체중·수면·컨디션) 데이터를 저장하는 단일 진실 소스.
표준 라이브러리(sqlite3)만 사용하므로 서버에 별도 pip 설치가 필요 없다.

DB 경로: 환경변수 PT_DB_PATH, 없으면 ~/.openclaw/pt_system/pt.sqlite
         (*.sqlite 는 .gitignore 대상 → 런타임 데이터는 서버에만 존재)

다른 모듈(record.py / briefing.py / app.py)이 여기서 connect()/조회 헬퍼를 가져다 쓴다.
"""
import os
import sqlite3
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:  # pragma: no cover
    KST = None


def db_path():
    p = os.getenv("PT_DB_PATH")
    if p:
        return os.path.expanduser(p)
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "pt.sqlite")


def now_kst():
    return datetime.now(KST) if KST else datetime.now()


def today_str():
    return now_kst().strftime("%Y-%m-%d")


SCHEMA = """
CREATE TABLE IF NOT EXISTS workouts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,           -- YYYY-MM-DD (KST)
    ts           TEXT NOT NULL,           -- ISO8601 입력시각
    type         TEXT,                    -- 웨이트/러닝/테니스/...
    detail       TEXT,                    -- 종목·세트·거리 등 자유 서술
    duration_min INTEGER,                 -- 운동 시간(분)
    intensity    TEXT,                    -- 낮음/보통/높음
    note         TEXT,
    source       TEXT DEFAULT 'slack',
    raw          TEXT                     -- 원문 메시지
);
CREATE TABLE IF NOT EXISTS meals (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT NOT NULL,
    ts        TEXT NOT NULL,
    meal      TEXT,                        -- 아침/점심/저녁/간식
    items     TEXT,                        -- 먹은 것
    kcal      INTEGER,
    protein_g REAL,
    note      TEXT,
    source    TEXT DEFAULT 'slack',
    raw       TEXT
);
CREATE TABLE IF NOT EXISTS vitals (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT NOT NULL,
    ts        TEXT NOT NULL,
    weight_kg REAL,
    sleep_h   REAL,
    condition TEXT,                        -- 컨디션 서술/점수
    mood      TEXT,
    note      TEXT,
    source    TEXT DEFAULT 'slack',
    raw       TEXT
);
CREATE TABLE IF NOT EXISTS ingest_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    source      TEXT,                      -- slack/telegram-relay/manual
    channel     TEXT,
    sender      TEXT,
    text        TEXT,
    parsed_kind TEXT                       -- workout/meal/vital/none
);
CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
CREATE INDEX IF NOT EXISTS idx_meals_date    ON meals(date);
CREATE INDEX IF NOT EXISTS idx_vitals_date   ON vitals(date);
"""


def connect(readonly=False):
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if readonly:
        if not os.path.exists(path):
            # 읽기 전용인데 파일이 없으면 빈 DB 를 초기화(대시보드 첫 기동 안전)
            init_db()
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    return con


def init_db():
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()
    return path


# ── 삽입 헬퍼 ────────────────────────────────────────────────
def _iso():
    return now_kst().isoformat(timespec="seconds")


def add_workout(con, *, date=None, type=None, detail=None, duration_min=None,
                intensity=None, note=None, source="slack", raw=None):
    con.execute(
        "INSERT INTO workouts(date,ts,type,detail,duration_min,intensity,note,source,raw)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (date or today_str(), _iso(), type, detail, duration_min, intensity, note, source, raw),
    )


def add_meal(con, *, date=None, meal=None, items=None, kcal=None, protein_g=None,
             note=None, source="slack", raw=None):
    con.execute(
        "INSERT INTO meals(date,ts,meal,items,kcal,protein_g,note,source,raw)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (date or today_str(), _iso(), meal, items, kcal, protein_g, note, source, raw),
    )


def add_vital(con, *, date=None, weight_kg=None, sleep_h=None, condition=None,
              mood=None, note=None, source="slack", raw=None):
    con.execute(
        "INSERT INTO vitals(date,ts,weight_kg,sleep_h,condition,mood,note,source,raw)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (date or today_str(), _iso(), weight_kg, sleep_h, condition, mood, note, source, raw),
    )


def log_ingest(con, *, source="slack", channel=None, sender=None, text=None, parsed_kind=None):
    con.execute(
        "INSERT INTO ingest_log(ts,source,channel,sender,text,parsed_kind) VALUES(?,?,?,?,?,?)",
        (_iso(), source, channel, sender, text, parsed_kind),
    )


# ── 조회 헬퍼 ────────────────────────────────────────────────
def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def counts_for_date(con, date):
    w = con.execute("SELECT COUNT(*) FROM workouts WHERE date=?", (date,)).fetchone()[0]
    m = con.execute("SELECT COUNT(*) FROM meals WHERE date=?", (date,)).fetchone()[0]
    v = con.execute("SELECT COUNT(*) FROM vitals WHERE date=?", (date,)).fetchone()[0]
    return {"workouts": w, "meals": m, "vitals": v}


def records_for_date(con, date):
    return {
        "workouts": _rows(con, "SELECT * FROM workouts WHERE date=? ORDER BY ts", (date,)),
        "meals": _rows(con, "SELECT * FROM meals WHERE date=? ORDER BY ts", (date,)),
        "vitals": _rows(con, "SELECT * FROM vitals WHERE date=? ORDER BY ts", (date,)),
    }


def range_str(days, end=None):
    end_d = end or today_str()
    end_dt = datetime.strptime(end_d, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=days - 1)
    return start_dt.strftime("%Y-%m-%d"), end_d


def weekly_stats(con, days=7, end=None):
    start, end_d = range_str(days, end)
    w = con.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(duration_min),0) dur "
        "FROM workouts WHERE date BETWEEN ? AND ?", (start, end_d)).fetchone()
    workout_days = con.execute(
        "SELECT COUNT(DISTINCT date) FROM workouts WHERE date BETWEEN ? AND ?",
        (start, end_d)).fetchone()[0]
    meals_c = con.execute(
        "SELECT COUNT(*) FROM meals WHERE date BETWEEN ? AND ?", (start, end_d)).fetchone()[0]
    vit = con.execute(
        "SELECT AVG(sleep_h) FROM vitals WHERE date BETWEEN ? AND ? AND sleep_h IS NOT NULL",
        (start, end_d)).fetchone()[0]
    weights = _rows(con,
        "SELECT date, weight_kg FROM vitals WHERE weight_kg IS NOT NULL "
        "AND date BETWEEN ? AND ? ORDER BY date, ts", (start, end_d))
    return {
        "start": start, "end": end_d, "days": days,
        "workout_count": w["c"], "workout_minutes": w["dur"],
        "workout_days": workout_days,
        "meal_count": meals_c,
        "avg_sleep_h": round(vit, 1) if vit is not None else None,
        "weight_first": weights[0]["weight_kg"] if weights else None,
        "weight_last": weights[-1]["weight_kg"] if weights else None,
    }


def last_workout_date(con):
    r = con.execute("SELECT MAX(date) FROM workouts").fetchone()[0]
    return r


def days_since_workout(con):
    d = last_workout_date(con)
    if not d:
        return None
    last = datetime.strptime(d, "%Y-%m-%d").date()
    return (now_kst().date() - last).days


def latest_weight(con):
    r = con.execute(
        "SELECT weight_kg, date FROM vitals WHERE weight_kg IS NOT NULL ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    return dict(r) if r else None


def weight_series(con, days=30, end=None):
    start, end_d = range_str(days, end)
    return _rows(con,
        "SELECT date, weight_kg FROM vitals WHERE weight_kg IS NOT NULL "
        "AND date BETWEEN ? AND ? ORDER BY date, ts", (start, end_d))


def recent(con, table, limit=50):
    assert table in ("workouts", "meals", "vitals", "ingest_log")
    return _rows(con, f"SELECT * FROM {table} ORDER BY ts DESC LIMIT ?", (limit,))


if __name__ == "__main__":
    path = init_db()
    print("초기화 완료:", path)
