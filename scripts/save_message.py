#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save_message.py — 형준 PT 기록 저장기
사용법: python3 save_message.py "스쿼트 5x8 레그프레스 4x12 닭가슴살 200g 체중 78kg 수면 7시간"
DB: ~/pt_data/pt.db
"""
import sys, re, sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path.home() / "pt_data" / "pt.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        exercise TEXT NOT NULL,
        sets INTEGER,
        reps INTEGER,
        weight_kg REAL,
        raw TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS diet (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        meal TEXT,
        items TEXT NOT NULL,
        protein_g REAL,
        raw TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS vitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        weight_kg REAL,
        sleep_hours REAL,
        condition TEXT,
        alcohol INTEGER DEFAULT 0,
        raw TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ai_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        report TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    con.commit()
    return con


def clean_name(name):
    name = re.sub(r'^[^\w가-힣]+', '', name)
    name = re.sub(r'^(오늘|어제|방금|아까|나|저|했어|했음|하고)\s*', '', name).strip()
    name = re.sub(r'\s*(했어|했음|함)$', '', name).strip()
    return name


def parse_workouts(text):
    results, seen = [], set()
    skip = {'수면', '체중', '단백질', '오늘', '어제', '아침', '점심', '저녁', '간식', '피자빵', '물', '시간'}

    chunks = re.split(r'[,.\n]|그리고|하고', text)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # 1. 세트x횟수 패턴 (e.g. 스쿼트 100kg 5x10, 스쿼트 5x10 100kg)
        m = re.search(r'([가-힣a-zA-Z\s\-]{2,15}?)\s+(?:(\d+(?:\.\d+)?)\s*kg\s+)?(\d+)\s*[xX×]\s*(\d+)(?:\s+(\d+(?:\.\d+)?)\s*kg)?', chunk)
        if m:
            name = clean_name(m.group(1))
            if len(name) >= 2 and name not in skip:
                weight = float(m.group(2) or m.group(5)) if (m.group(2) or m.group(5)) else None
                key = (name, m.group(3), m.group(4))
                if key not in seen:
                    seen.add(key)
                    results.append({'exercise': name, 'sets': int(m.group(3)), 'reps': int(m.group(4)), 'weight_kg': weight})
                continue

        # 2. 세트/회 패턴 (e.g. 스쿼트 100kg 5세트 10회)
        m = re.search(r'([가-힣a-zA-Z\s\-]{2,15}?)\s+(?:(\d+(?:\.\d+)?)\s*kg\s+)?(\d+)\s*세트\s*(\d+)\s*회(?:\s+(\d+(?:\.\d+)?)\s*kg)?', chunk)
        if m:
            name = clean_name(m.group(1))
            if len(name) >= 2 and name not in skip:
                weight = float(m.group(2) or m.group(5)) if (m.group(2) or m.group(5)) else None
                key = (name, m.group(3), m.group(4))
                if key not in seen:
                    seen.add(key)
                    results.append({'exercise': name, 'sets': int(m.group(3)), 'reps': int(m.group(4)), 'weight_kg': weight})
                continue

        # 3. 단일 개수/회 패턴 (e.g. 풀업 12개)
        m = re.search(r'([가-힣a-zA-Z\s\-]{2,15}?)\s+(?:(\d+(?:\.\d+)?)\s*kg\s+)?(\d+)\s*(?:개|회|번)', chunk)
        if m:
            name = clean_name(m.group(1))
            if len(name) >= 2 and name not in skip:
                weight = float(m.group(2)) if m.group(2) else None
                reps = int(m.group(3))
                key = (name, reps)
                if key not in seen:
                    seen.add(key)
                    results.append({'exercise': name, 'sets': 1, 'reps': reps, 'weight_kg': weight})
                continue

        # 4. 유산소/자유 형식 (테니스 30분 등)
        fm = re.search(r'(테니스|달리기|조깅|수영|자전거|등산|러닝|복싱|유산소|스텝밀|트레드밀)(?:\s+(\d+)\s*(?:게임|분|km))?', chunk)
        if fm:
            name, desc = fm.group(1), fm.group(2)
            if (name, desc) not in seen:
                seen.add((name, desc))
                results.append({
                    'exercise': f"{name} {desc}{'분' if desc else ''}".strip() if desc else name,
                    'sets': 1, 'reps': 1, 'weight_kg': None
                })
    return results


def parse_diet(text):
    food_kw = (r'(?:닭가슴살|달걀|계란|두부|소고기|돼지고기|삼겹살|생선|연어|참치|'
               r'고등어|프로틴|쉐이크|단백질바|오트밀|고구마|현미|샐러드|브로콜리|'
               r'아보카도|밥|죽|국|찌개|면|라면|피자|치킨|햄버거|빵|과일|견과류)')
    foods = re.findall(food_kw + r'(?:\s*\d+\s*[gG개인분])?', text)
    protein = None
    pm = re.search(r'단백질\s*(\d+(?:\.\d+)?)\s*[gG]', text)
    if pm:
        protein = float(pm.group(1))
    meal = next((k for k in ['아침', '점심', '저녁', '간식'] if k in text), None)
    if foods or protein:
        return [{'meal': meal, 'items': ', '.join(foods) if foods else text[:100], 'protein_g': protein}]
    return []


def parse_vitals(text):
    v = {}
    # 체중
    wm = re.search(r'체중\s*(\d+(?:\.\d+)?)\s*kg', text)
    if not wm:
        wm = re.search(r'(\d{2,3}(?:\.\d+)?)\s*kg(?!\s*(?:\d+\s*[xX×]|\d+\s*세트))', text)
    if wm:
        w = float(wm.group(1))
        if 40 <= w <= 200:
            v['weight_kg'] = w
    # 수면
    sm = re.search(r'수면\s*(\d+(?:\.\d+)?)\s*시간', text) or \
         re.search(r'(\d+(?:\.\d+)?)\s*시간\s*(?:잠|수면|취침)', text)
    if sm:
        v['sleep_hours'] = float(sm.group(1))
    # 컨디션
    for k, cv in [('최고', 'excellent'), ('좋', 'good'), ('보통', 'fair'),
                  ('피곤', 'tired'), ('나쁨', 'poor'), ('최악', 'terrible')]:
        if k in text:
            v['condition'] = cv
            break
    # 음주
    if any(w in text for w in ['술', '맥주', '소주', '와인', '음주', '마셨']):
        v['alcohol'] = 1
    return v or None


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 save_message.py \"메시지\"")
        sys.exit(1)

    msg = ' '.join(sys.argv[1:])
    today = date.today().isoformat()
    now = datetime.now().isoformat()

    con = init_db()
    cur = con.cursor()
    wc = dc = 0
    vs = False

    for w in parse_workouts(msg):
        cur.execute(
            "INSERT INTO workouts (date,exercise,sets,reps,weight_kg,raw,created_at) VALUES(?,?,?,?,?,?,?)",
            (today, w['exercise'], w['sets'], w['reps'], w['weight_kg'], msg, now)
        )
        wc += 1

    for d in parse_diet(msg):
        cur.execute(
            "INSERT INTO diet (date,meal,items,protein_g,raw,created_at) VALUES(?,?,?,?,?,?)",
            (today, d['meal'], d['items'], d['protein_g'], msg, now)
        )
        dc += 1

    vitals = parse_vitals(msg)
    if vitals:
        try:
            cols = list(vitals.keys()) + ['date', 'raw', 'created_at']
            vals = list(vitals.values()) + [today, msg, now]
            cur.execute(
                f"INSERT INTO vitals ({','.join(cols)}) VALUES({','.join(['?']*len(cols))})",
                vals
            )
        except sqlite3.IntegrityError:
            sets_clause = ','.join(f"{k}=?" for k in vitals)
            cur.execute(
                f"UPDATE vitals SET {sets_clause},raw=? WHERE date=?",
                list(vitals.values()) + [msg, today]
            )
        vs = True

    con.commit()
    con.close()
    print(f"운동 {wc}개 / 식단 {dc}개 / 바이탈 {'저장' if vs else '없음'}")


if __name__ == "__main__":
    main()
