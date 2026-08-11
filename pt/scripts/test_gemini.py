import sys
from pathlib import Path

# 파이썬이 pt_system 폴더를 최상위 경로로 인식하도록 추가합니다.
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))

from google import genai
from scripts.config import GEMINI_MODEL

client = genai.Client()

response = client.models.generate_content(
    model=GEMINI_MODEL,
    contents="한국어로 한 문장만 답하세요. AI PT 시스템 테스트입니다."
)

print(response.text)