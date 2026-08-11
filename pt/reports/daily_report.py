from pathlib import Path
import sys
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))
from google import genai
from scripts.config import GEMINI_MODEL
from scripts.db import get_conn
from reports.fetch_data import fetch_range
def build_prompt(data):
    return f"""
당신은 개인 PT 트레이너입니다.
아래의 하루 기록을 보고 한국어로 일일 리포트를 작성하세요.
규칙:
- 의학적 진단 금지
- 잘한 점 2개
- 개선할 점 2개
-내일 할 행동3개
- 전체 길이 800자 이내
- 초보자가 이해하기 쉽게 작성
데이터: {data} """
def save_report(start, end, text):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reports (report_type, start_date, end_date, report_text)
        VALUES (?, ?, ?, ?)
        """,
        ("daily", start, end, text),
    )
    conn.commit()
    conn.close()
def main():
    data = fetch_range(days=1)
    client = genai.Client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=build_prompt(data),
    )
    report = response.text.strip()
    save_report(data["start"], data["end"], report)
    print(report)
if __name__ == "__main__":
    main()
