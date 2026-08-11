import time
import subprocess
from pathlib import Path
import sys
import requests

# 1. 프로젝트 루트를 경로에 추가 (매뉴얼 12장 기준)
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))

# 2. 매뉴얼에서 정의한 모듈 임포트
from scripts.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BASE_DIR
from scripts.send_telegram import send_message
from scripts.ai_helper import generate_response, generate_image_response

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def get_updates(offset=None):
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        res = requests.get(f"{API_URL}/getUpdates", params=params, timeout=40)
        res.raise_for_status()
        return res.json().get("result", [])
    except Exception as e:
        print(f"Update 조회 오류: {e}")
        return []

def handle_text(text):
    # /daily 리포트 요청 처리
    if text == "/daily":
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "reports/daily_report.py")],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            send_message(f"[오류 발생]\n일일 리포트 생성 중 에러가 발생했습니다:\n{result.stderr.strip()}")
            return
        stdout_val = result.stdout.strip()
        send_message("[일일 PT 리포트]\n\n" + (stdout_val if stdout_val else "리포트 생성 내용이 없습니다."))
        return

    # /weekly 리포트 요청 처리
    if text == "/weekly":
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "reports/weekly_report.py")],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            send_message(f"[오류 발생]\n주간 리포트 생성 중 에러가 발생했습니다:\n{result.stderr.strip()}")
            return
        stdout_val = result.stdout.strip()
        send_message("[주간 PT 리포트]\n\n" + (stdout_val if stdout_val else "주간 데이터가 없습니다."))
        return

    # /help 도움말
    if text == "/help":
        send_message("사용법\n- 운동/식단/체중을 자연스럽게 입력하세요.\n- /daily: 일일 리포트\n- /weekly: 주간 리포트\n- /help: 도움말")
        return

    # 일반 기록 저장 스크립트 실행
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "scripts/save_message.py"), text],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        send_message(f"[오류 발생]\n기록 저장 중 에러가 발생했습니다:\n{result.stderr.strip()}")
        return
    stdout_val = result.stdout.strip()
    
    # AI 피드백 및 답변 생성
    ai_feedback = generate_response(text)
    
    # 두 결과를 하나의 메시지로 결합하여 전송
    response_message = ""
    if stdout_val:
        response_message += stdout_val
    if ai_feedback:
        if response_message:
            response_message += "\n\n"
        response_message += ai_feedback
        
    if response_message:
        send_message(response_message)

def handle_photo(photo, caption):
    # 가장 큰 크기의 사진 선택
    large_photo = photo[-1]
    file_id = large_photo.get("file_id")
    
    try:
        # 파일 경로 획득
        file_res = requests.get(f"{API_URL}/getFile", params={"file_id": file_id}, timeout=15)
        file_res.raise_for_status()
        file_path = file_res.json().get("result", {}).get("file_path")
        if not file_path:
            send_message("사진 파일 경로를 획득하는 데 실패했습니다.")
            return
            
        # 사진 이진 파일 다운로드
        img_res = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}", timeout=30)
        img_res.raise_for_status()
        image_bytes = img_res.content
    except Exception as e:
        send_message(f"사진 다운로드 중 에러 발생: {e}")
        return

    send_message("사진을 분석하고 있습니다. 잠시만 기다려 주세요...")
    
    # Gemini를 통해 이미지 내용 분석
    ai_raw_response = generate_image_response(image_bytes, mime_type="image/jpeg")
    
    # [기록 데이터] 및 [코칭 피드백] 파싱
    db_text = ""
    coaching_feedback = ""
    
    if "[기록 데이터]" in ai_raw_response:
        parts = ai_raw_response.split("[코칭 피드백]", 1)
        db_part = parts[0].replace("[기록 데이터]", "").strip()
        coaching_part = parts[1].strip() if len(parts) > 1 else ""
        db_text = db_part
        coaching_feedback = coaching_part
    else:
        coaching_feedback = ai_raw_response
        
    # 사용자가 사진과 함께 보낸 캡션(텍스트)이 있다면 분석 텍스트 뒤에 덧붙여 줌
    if caption and db_text:
        db_text += f"\n{caption}"
    elif caption and not db_text:
        db_text = caption

    stdout_val = ""
    if db_text.strip():
        # 데이터베이스 자동 기록을 위한 save_message.py 호출
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "scripts/save_message.py"), db_text],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            stdout_val = result.stdout.strip()
        else:
            stdout_val = f"[기록 저장 실패]\n{result.stderr.strip()}"
            
    # 최종 답변 합산하여 전송
    response_message = ""
    if stdout_val:
        response_message += stdout_val
    if coaching_feedback:
        if response_message:
            response_message += "\n\n"
        response_message += coaching_feedback
        
    if response_message:
        send_message(response_message)

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        
    offset = None
    send_message("AI PT 트레이너가 시작되었습니다. 오늘 기록을 보내주세요.")
    
    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                
                # 설정된 Chat ID 확인
                if str(TELEGRAM_CHAT_ID) and chat_id != str(TELEGRAM_CHAT_ID):
                    continue
                    
                text = message.get("text", "").strip()
                photo = message.get("photo")
                caption = message.get("caption", "").strip()
                
                if photo:
                    handle_photo(photo, caption)
                elif text:
                    handle_text(text)
        except Exception as e:
            print(f"오류 발생: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()