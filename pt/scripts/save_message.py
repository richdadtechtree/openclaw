import os
import re
import sys
from datetime import date
from pathlib import Path

# 이 벤더링된 openclaw 복사본(dotenv 선택적)을 우선 임포트하도록 자기 패키지를 맨 앞에 둔다.
# (DB 경로는 config.py 가 /home/ubuntu/pt_system 존재 시 그쪽 pt_data.db 를 가리켜 대시보드와 공유)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path("/home/ubuntu/pt_system")))
from scripts.db import get_conn

# 기록 출처(raw_messages.source). 슬랙 전환 이후 기본값은 "slack".
# 환경변수 PT_SOURCE 또는 실행 시 `--source <이름>` 로 덮어쓸 수 있음(텔레그램 호환).
DEFAULT_SOURCE = os.getenv("PT_SOURCE", "slack")

def find_weight(text):
    match = re.search(r"체중\s*([0-9]+(?:\.[0-9]+)?)\s*kg", text, re.IGNORECASE) 
    return float(match.group(1)) if match else None

def find_sleep(text):
    match = re.search(r"수면\s*([0-9]+(?:\.[0-9]+)?)\s*시간", text) 
    return float(match.group(1)) if match else None

def save_raw_message(text, source=DEFAULT_SOURCE):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO raw_messages (source, message_text, processed) VALUES (?, ?, ?)",
        (source, text, 1),
    )
    conn.commit()
    conn.close()

def save_vitals_if_present(text):
    body_weight = find_weight(text)
    sleep_hours = find_sleep(text)
    
    if body_weight is None and sleep_hours is None and "컨디션" not in text: 
        return False
        
    condition = None
    if "컨디션" in text:
        condition = text.split("컨디션", 1)[-1].strip().splitlines()[0][:100]
        
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO vitals (record_date, body_weight_kg, sleep_hours, condition_text, memo)
        VALUES (?, ?, ?, ?, ?)
        """,
        (date.today().isoformat(), body_weight, sleep_hours, condition, text),
    )
    conn.commit()
    conn.close()
    return True

def save_workout_if_present(text):
    keywords = ["운동", "스쿼트", "벤치", "데드", "런닝", "걷기", "레그", "랫풀", "로우", "프레스", "풀업", "턱걸이"] 
    if not any(k in text for k in keywords):
        return 0
        
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    count = 0
    conn = get_conn()
    cur = conn.cursor()
    for line in lines:
        if any(k in line for k in keywords):
            # 횟수(Reps) 및 세트(Sets) 파싱
            reps = None
            sets = None
            
            reps_match = re.search(r"(\d+)\s*(?:회|개|reps|rep)", line, re.IGNORECASE)
            if reps_match:
                reps = int(reps_match.group(1))
            else:
                fallback_match = re.search(r"(?:풀업|턱걸이|스쿼트|벤치|데드|랫풀|런닝)\s*(\d+)", line)
                if fallback_match:
                    reps = int(fallback_match.group(1))
                    
            sets_match = re.search(r"(\d+)\s*(?:세트|set)", line, re.IGNORECASE)
            if sets_match:
                sets = int(sets_match.group(1))
                
            cur.execute(
                """
                INSERT INTO workouts (record_date, exercise_name, memo, reps, sets)
                VALUES (?, ?, ?, ?, ?)
                """,
                (date.today().isoformat(), line[:80], line, reps, sets),
            )
            count += 1
    conn.commit()
    conn.close()
    return count

def save_meal_if_present(text):
    keywords = ["식단", "아침", "점심", "저녁", "간식", "닭가슴살", "밥", "고구마", "샐러드", "계란"] 
    if not any(k in text for k in keywords):
        return 0
        
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    count = 0
    conn = get_conn()
    cur = conn.cursor()
    for line in lines:
        if any(k in line for k in keywords):
            meal_type = None
            for candidate in ["아침", "점심", "저녁", "간식"]:
                if candidate in line:
                    meal_type = candidate
                    break
            cur.execute(
                """
                INSERT INTO meals (record_date, meal_type, food_text, memo)
                VALUES (?, ?, ?, ?)
                """,
                (date.today().isoformat(), meal_type, line, line),
            )
            count += 1
    conn.commit()
    conn.close()
    return count

def main():
    args = sys.argv[1:]
    source = DEFAULT_SOURCE
    # 선택적 `--source <이름>` 플래그(맨 앞) 파싱 — 나머지는 메시지 본문.
    if len(args) >= 2 and args[0] == "--source":
        source = args[1]
        args = args[2:]

    text = " ".join(args).strip()
    if not text:
        text = sys.stdin.read().strip()
    if not text:
        print("입력된 메시지가 없습니다.")
        return

    save_raw_message(text, source)
    workout_count = save_workout_if_present(text)
    meal_count = save_meal_if_present(text)
    vitals_saved = save_vitals_if_present(text)

    print("[기록 완료]")
    print(f"- 운동: {workout_count}개")
    print(f"- 식단: {meal_count}개")
    print(f"- 바이탈: {'저장됨' if vitals_saved else '없음'}")
    # 파싱된 기록이 하나도 없으면 호출자(에이전트)가 감지해 사용자에게 경고하도록 표시.
    if workout_count == 0 and meal_count == 0 and not vitals_saved:
        print("[미저장] 인식된 운동/식단/바이탈 키워드가 없어 raw_messages 에만 남았습니다.")
    print("- 오늘의 한마디: 기록을 남긴 것 자체가 가장 중요한 시작입니다.")

if __name__ == "__main__":
    main()