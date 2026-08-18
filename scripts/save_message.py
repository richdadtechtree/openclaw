#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
save_message.py — 형준/종국 PT 기록 저장기 (웹 대시보드 pt_dashboard.py 와 같은 pt.db 사용)
DB: ~/pt_data/pt.db

사용법
  1) 자유 텍스트(정규식 파싱, 폴백용):
     python3 save_message.py "스쿼트 5x8 레그프레스 4x12 닭가슴살 200g 체중 78kg 수면 7시간"

  2) 구조화 JSON(권장 — 종국 에이전트가 대화에서 직접 뽑아 넣는 방식):
     python3 save_message.py --json '{
       "date": "2026-08-17",
       "workouts": [{"exercise":"스쿼트","sets":5,"reps":8,"weight_kg":100}],
       "diet":     [{"meal":"점심","items":"닭가슴살 200g","protein_g":46}],
       "vitals":   {"weight_kg":78,"sleep_hours":7,"condition":"good","alcohol":0}
     }'
     # --date 로 날짜 강제(payload 의 date 보다 우선). 세 종류 다 선택(있는 것만 넣으면 됨).

JSON 모드는 LLM 이 대화에서 정확히 추출한 값을 그대로 저장하므로 정규식 파서보다 안정적이다.
종국(keepgoing) 에이전트는 사용자가 운동/식단/컨디션을 말하면 반드시 이 스크립트로 저장해야
웹 대시보드(pt_dashboard.py)에 즉시 노출된다.
"""
import sys, re, json, sqlite3
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
        body_fat_pct REAL,
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
    # 기존 DB(마이그레이션 전)에 body_fat_pct 컬럼이 없으면 추가 — pt_dashboard.py 와 동일 마이그레이션.
    cols = [r[1] for r in con.execute("PRAGMA table_info(vitals)").fetchall()]
    if "body_fat_pct" not in cols:
        con.execute("ALTER TABLE vitals ADD COLUMN body_fat_pct REAL")
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


# 식사 카테고리 — 아침/점심/저녁/간식/물/단백질 로 통일. '단백질'은 정규 식사와 별도로
# 프로틴 쉐이크·바 등을 챙겼을 때를 위한 카테고리. '수분'처럼 같은 뜻의 다른 표현이
# 들어와도(구조화 JSON 에서 LLM 이 다르게 부를 수 있음) 전부 '물' 로 정규화해서 검색·집계가
# 갈라지지 않게 한다. 새 표현이 필요하면 여기 별칭만 추가하면 됨.
MEAL_ALIASES = {'수분': '물', '음수': '물', '워터': '물', 'water': '물', 'Water': '물'}
MEAL_WORDS = ['아침', '점심', '저녁', '간식', '물', '단백질'] + list(MEAL_ALIASES.keys())


def normalize_meal(meal):
    """'수분' 등 물의 다른 표현을 '물' 로 통일. 그 외 값은 그대로 둠."""
    if not meal:
        return meal
    m = str(meal).strip()
    return MEAL_ALIASES.get(m, m)


def parse_diet(text):
    # 한글 음절 범위 — 키워드 앞뒤가 한글이면(=더 긴 단어의 일부면) 매칭 안 함.
    # 예: '막국수' 안의 '국'이 독립된 음식으로 잘못 매칭되는 것을 방지.
    # '물'도 같은 이유로 경계 보호가 필요 — 아니면 '탄수화물' 안의 '물'까지 식사시간으로 오인식됨.
    HANGUL = r'가-힣'
    food_words = ['닭가슴살', '달걀', '계란', '두부', '소고기', '돼지고기', '삼겹살', '생선', '연어', '참치',
                  '고등어', '프로틴', '쉐이크', '단백질바', '오트밀', '고구마', '현미', '샐러드', '브로콜리',
                  '아보카도', '밥', '죽', '국', '찌개', '면', '라면', '피자', '치킨', '햄버거', '빵', '과일', '견과류']
    food_kw = (r'(?<![' + HANGUL + r'])(?:' + '|'.join(food_words) + r')(?![' + HANGUL + r'])')
    foods = re.findall(food_kw + r'(?:\s*\d+\s*[gG개인분])?', text)
    protein = None
    pm = re.search(r'단백질\s*(\d+(?:\.\d+)?)\s*[gG]', text)
    if pm:
        protein = float(pm.group(1))

    # 앞쪽만 경계 보호(뒤는 보호 안 함) — '탄수화물'의 '물'은 막되, '간식으로'·'점심때'처럼
    # 조사가 바로 붙는 흔한 표현은 여전히 인식되게 함.
    meal_kw = (r'(?<![' + HANGUL + r'])(?:' + '|'.join(MEAL_WORDS) + r')')
    mm = re.search(meal_kw, text)
    meal_raw = mm.group(0) if mm else None
    meal = normalize_meal(meal_raw)

    if foods:
        items = ', '.join(foods)
    elif meal:
        # 화이트리스트에 없는 음식(막국수·메밀만두·아메리카노 등)이어도 통째로 보존 — 유실 방지.
        items = re.sub(r'^\s*' + re.escape(meal_raw) + r'\s*', '', text).strip() or text[:100]
    elif protein is not None:
        items = text[:100]
    else:
        return []

    return [{'meal': meal, 'items': items, 'protein_g': protein}]


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
    # 체지방률
    bfm = re.search(r'체지방(?:률|율)?\s*(\d+(?:\.\d+)?)\s*%', text)
    if bfm:
        bf = float(bfm.group(1))
        if 3 <= bf <= 60:
            v['body_fat_pct'] = bf
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


def _num(x):
    """숫자 문자열/값을 float 로. 빈값·None 은 None."""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def save_vitals(cur, v, day, raw, now):
    """vitals 는 date UNIQUE → 없으면 INSERT, 있으면 준 필드만 UPDATE(덮어쓰기)."""
    fields = {}
    for k in ('weight_kg', 'sleep_hours', 'body_fat_pct'):
        if v.get(k) not in (None, ""):
            fields[k] = _num(v[k])
    if v.get('condition'):
        fields['condition'] = str(v['condition'])
    if 'alcohol' in v and v['alcohol'] not in (None, ""):
        fields['alcohol'] = 1 if v['alcohol'] in (1, '1', True, 'true', 'True') else 0
    if not fields:
        return False
    try:
        cols = list(fields.keys()) + ['date', 'raw', 'created_at']
        vals = list(fields.values()) + [day, raw, now]
        cur.execute(
            f"INSERT INTO vitals ({','.join(cols)}) VALUES({','.join(['?']*len(cols))})",
            vals,
        )
    except sqlite3.IntegrityError:
        sets_clause = ','.join(f"{k}=?" for k in fields)
        cur.execute(
            f"UPDATE vitals SET {sets_clause},raw=? WHERE date=?",
            list(fields.values()) + [raw, day],
        )
    return True


def save_structured(payload):
    """대화에서 뽑은 구조화 데이터를 pt.db 에 저장. payload 예시는 파일 상단 도움말 참고."""
    today = date.today().isoformat()
    now = datetime.now().isoformat()
    day = payload.get('date') or today
    raw = payload.get('raw') or json.dumps(payload, ensure_ascii=False)

    con = init_db()
    cur = con.cursor()
    wc = dc = 0

    for w in payload.get('workouts', []) or []:
        name = (w.get('exercise') or '').strip()
        if not name:
            continue
        sets = w.get('sets')
        reps = w.get('reps')
        cur.execute(
            "INSERT INTO workouts (date,exercise,sets,reps,weight_kg,raw,created_at) VALUES(?,?,?,?,?,?,?)",
            (day, name,
             int(sets) if sets not in (None, "") else None,
             int(reps) if reps not in (None, "") else None,
             _num(w.get('weight_kg')), raw, now),
        )
        wc += 1

    for d in payload.get('diet', []) or []:
        items = (d.get('items') or '').strip()
        if not items:
            continue
        cur.execute(
            "INSERT INTO diet (date,meal,items,protein_g,raw,created_at) VALUES(?,?,?,?,?,?)",
            (day, normalize_meal(d.get('meal')), items, _num(d.get('protein_g')), raw, now),
        )
        dc += 1

    vitals = payload.get('vitals') or {}
    vs = save_vitals(cur, vitals, day, raw, now) if vitals else False

    con.commit()
    con.close()
    print(f"[{day}] 운동 {wc}개 / 식단 {dc}개 / 바이탈 {'저장' if vs else '없음'}")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 save_message.py \"메시지\"  또는  --json '<payload>'")
        sys.exit(1)

    # 구조화 JSON 모드 (권장)
    if sys.argv[1] == "--json":
        args = sys.argv[2:]
        date_override = None
        if args and args[0] == "--date" and len(args) >= 2:
            date_override = args[1]
            args = args[2:]
        if not args:
            print("사용법: python3 save_message.py --json '<payload>'")
            sys.exit(1)
        try:
            payload = json.loads(args[0])
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 실패: {e}")
            sys.exit(1)
        if date_override:
            payload['date'] = date_override
        save_structured(payload)
        return

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
