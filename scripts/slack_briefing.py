#!/usr/bin/env python3
"""
slack_briefing.py — 대시보드를 캡처해서 슬랙 채널에 이미지로 전송 (독립 실행)

기존 stock 프로젝트의 capture_dashboard() 를 재사용하므로,
이 파일을 stock 폴더에 두고 실행하면 됩니다. (기존 파일은 수정하지 않음)

필요:
  - stock 대시보드 웹서버(scheduler.py/app.py)가 떠 있어야 함 (캡처 대상)
  - .env 에 SLACK_BOT_TOKEN(xoxb, files:write 스코프) 와 SLACK_BRIEFING_CHANNEL(C...)
사용:
  cd ~/stock/stock && python slack_briefing.py
"""
import os
from datetime import datetime

import requests
from dotenv import load_dotenv

# 기존 capture.py 의 캡처 함수/경로 재사용 (파일 수정 없음)
from capture import capture_dashboard, SCREENSHOT_PATH

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_BRIEFING_CHANNEL = os.getenv("SLACK_BRIEFING_CHANNEL") or os.getenv("SLACK_STOCK_CHANNEL")


def send_slack_photo(path, caption=""):
    """슬랙 채널에 이미지 업로드 (files 최신 업로드 API). 성공 시 True."""
    token, channel = SLACK_BOT_TOKEN, SLACK_BRIEFING_CHANNEL
    if not token or not channel:
        print("[Error] .env 에 SLACK_BOT_TOKEN 또는 SLACK_BRIEFING_CHANNEL 이 없습니다.")
        return False
    try:
        filename = os.path.basename(path)
        length = os.path.getsize(path)

        # 1) 업로드 URL 발급
        d1 = requests.get(
            "https://slack.com/api/files.getUploadURLExternal",
            headers={"Authorization": f"Bearer {token}"},
            params={"filename": filename, "length": length},
            timeout=30,
        ).json()
        if not d1.get("ok"):
            print(f"[Error] getUploadURLExternal 실패: {d1}")
            return False

        # 2) 파일 바이트 업로드
        with open(path, "rb") as f:
            r2 = requests.post(d1["upload_url"], data=f.read(), timeout=60)
        if r2.status_code != 200:
            print(f"[Error] 파일 업로드 실패: HTTP {r2.status_code}")
            return False

        # 3) 업로드 완료 + 채널 게시
        payload = {
            "files": [{"id": d1["file_id"], "title": caption or filename}],
            "channel_id": channel,
        }
        if caption:
            payload["initial_comment"] = caption
        d3 = requests.post(
            "https://slack.com/api/files.completeUploadExternal",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            timeout=30,
        ).json()
        if d3.get("ok"):
            return True
        print(f"[Error] completeUploadExternal 실패: {d3}")
    except Exception as e:
        print(f"[Error] 슬랙 전송 예외: {e}")
    return False


def main():
    print("대시보드 캡처 중...")
    if not capture_dashboard(SCREENSHOT_PATH):
        print("[Error] 캡처 실패. 대시보드 웹서버가 떠 있는지 확인하세요.")
        return
    caption = (
        "📈 주요 시장 지수 마감 브리핑\n"
        f"📅 {datetime.now().strftime('%Y년 %m월 %d일 %H:%M 마감')}\n"
        "코스피·코스닥·S&P 500·TQQQ 현황과 투자 타이밍 진행 상태입니다."
    )
    print("슬랙 전송 중...")
    print("✅ 슬랙 전송 성공!" if send_slack_photo(SCREENSHOT_PATH, caption) else "❌ 슬랙 전송 실패")


if __name__ == "__main__":
    main()
