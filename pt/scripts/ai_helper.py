import os
from google import genai
from scripts.config import GEMINI_API_KEY, GEMINI_MODEL, BASE_DIR

# 새로운 클라이언트 초기화
client = genai.Client(api_key=GEMINI_API_KEY)

def load_markdown_file(filename):
    file_path = BASE_DIR / filename
    if file_path.exists():
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"{filename} 읽기 오류: {e}")
    return ""

def generate_response(prompt):
    # USER.md와 SOUL.md 파일 읽기 시도
    user_info = load_markdown_file("USER.md")
    soul_info = load_markdown_file("SOUL.md")
    
    # 기본 프로필 백업 (파일이 없을 경우 대비)
    default_user_info = """
    - 이름: 이형준
    - 운동 목적: 체지방 감량과 근력 향상
    - 운동 수준: 초보자 (주 3회 가능)
    - 장소/선호: 헬스장, 테니스, 야외 러닝
    """
    
    default_soul_info = """
    - 역할: 20년 차 베테랑 전문 PT 트레이너 (건강/운동 코칭만 답함. 투자/뉴스 질문은 신문 봇에게 패스)
    - 코칭: 2~3일 안 움직이면 경각심을 주며, 건강에 해롭거나 안 좋은 음식을 식단으로 먹었을 시 주의를 주고 구체적인 악영향을 경고.
    - 운동 추천: 균형 잡힌 체형을 위해 사용자가 평소 자주 하지 않는 운동 부위(상/하체 등 편향 방지)가 보이면 적극적으로 추천.
    - 성격: 차분하고 지속 가능한 루틴 우선, 실천 가능성 중시
    - 말투: 한국어로 짧고 명확하게, 5줄 이내 답변
    """
    
    user_profile = user_info if user_info.strip() else default_user_info
    bot_soul = soul_info if soul_info.strip() else default_soul_info

    try:
        full_prompt = f"""
당신은 다음 규칙과 프로필에 기반하여 작동하는 AI PT 코치입니다.

[사용자 프로필 정보]
{user_profile}

[코칭 스타일 및 규칙 (SOUL)]
{bot_soul}

위 규칙과 성격, 말투를 엄격하게 준수하여 사용자의 입력에 답변해 주세요.

사용자의 입력: {prompt}
"""
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
        )
        return response.text
    except Exception as e:
        return f"AI 답변 생성 중 오류가 발생했습니다: {e}"

def generate_image_response(image_bytes, mime_type="image/jpeg"):
    from google.genai import types
    
    # USER.md와 SOUL.md 파일 읽기 시도
    user_info = load_markdown_file("USER.md")
    soul_info = load_markdown_file("SOUL.md")
    
    # 기본 프로필 백업 (파일이 없을 경우 대비)
    default_user_info = """
    - 이름: 이형준
    - 운동 목적: 체지방 감량과 근력 향상
    - 운동 수준: 초보자 (주 3회 가능)
    - 장소/선호: 헬스장, 테니스, 야외 러닝
    """
    
    default_soul_info = """
    - 역할: 20년 차 베테랑 전문 PT 트레이너 (건강/운동 코칭만 답함. 투자/뉴스 질문은 신문 봇에게 패스)
    - 코칭: 2~3일 안 움직이면 경각심을 주며, 건강에 해롭거나 안 좋은 음식을 식단으로 먹었을 시 주의를 주고 구체적인 악영향을 경고.
    - 운동 추천: 균형 잡힌 체형을 위해 사용자가 평소 자주 하지 않는 운동 부위(상/하체 등 편향 방지)가 보이면 적극적으로 추천.
    - 성격: 차분하고 지속 가능한 루틴 우선, 실천 가능성 중시
    - 말투: 한국어로 짧고 명확하게, 5줄 이내 답변
    """
    
    user_profile = user_info if user_info.strip() else default_user_info
    bot_soul = soul_info if soul_info.strip() else default_soul_info

    prompt = f"""
당신은 사용자가 보낸 운동/식단 사진을 분석하고 기록을 돕는 AI PT 코치입니다.

[사용자 프로필 정보]
{user_profile}

[코칭 스타일 및 규칙 (SOUL)]
{bot_soul}

[미션]
제공된 이미지 파일(사진)을 세밀하게 분석하고 아래 두 가지 항목을 순서대로 생성해 주세요.

1. **[기록 데이터]**: 사진 속 내용에서 식사(식단) 정보나 운동 정보(종목명, 무게 kg, 횟수 reps, 세트 등)를 파악하여 텍스트 데이터 형식으로 정형화해 작성해 주세요. 
   - 예시 (식사): `저녁 식단: 닭가슴살 샐러드, 현미밥`
   - 예시 (운동): `운동: 벤치프레스 60kg 10회 3세트`
   - 식단과 운동 정보가 모두 없거나 분석할 수 없다면 이 영역은 비워두세요.
   
2. **[코칭 피드백]**: 분석된 결과를 바탕으로 사용자에게 보낼 5줄 이내의 짧고 명확한 피드백 메시지를 작성해 주세요. (SOUL에 명시된 어조와 말투 준수)

형식 예시:
[기록 데이터]
저녁 식단: 닭가슴살 샐러드, 현미밥

[코칭 피드백]
형준 님, 오늘 저녁은 단백질 위주로 아주 깔끔하게 드셨네요! 지속 가능한 루틴의 좋은 시작입니다. 오늘 운동도 잊지 말고 다녀오세요!
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type
                ),
                prompt
            ]
        )
        return response.text
    except Exception as e:
        return f"AI 이미지 분석 중 오류가 발생했습니다: {e}"