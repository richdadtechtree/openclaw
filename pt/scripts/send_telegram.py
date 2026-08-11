import sys
from pathlib import Path

# 파이썬이 pt_system 폴더를 최상위 경로로 인식하도록 추가합니다.
sys.path.append(str(Path("/home/ubuntu/pt_system")))
sys.path.append(str(Path(__file__).resolve().parents[1]))

import requests
from scripts.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram 설정이 비어 있습니다.")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }
    
    res = requests.post(url, json=payload, timeout=15)
    res.raise_for_status()
    return res.json()

if __name__ == "__main__":
    send_message("AI PT 트레이너 Telegram 발송 테스트입니다.")
    print("전송 완료")