#!/usr/bin/env python3
"""
sheets_push.py — 브리핑 md 파일을 구글 시트에 행으로 추가 (Apps Script 웹앱 경유)

사용:  python sheets_push.py <마크다운파일> <아침|저녁|요청> [YYYY-MM-DD]

필요 (.env, openclaw 루트):
  SHEETS_WEBAPP_URL     Apps Script 웹앱 배포 URL (https://script.google.com/macros/s/.../exec)
  SHEETS_WEBAPP_SECRET  웹앱과 공유하는 비밀 문자열 (스크립트의 SECRET 과 동일)

시트에 추가되는 행: [일시(자동), 날짜, 시간대, 제목, 본문(마크다운 전체)]
"""
import os
import sys
from datetime import datetime

import requests


def load_env():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (os.path.join(base, ".env"), ".env"):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            break


load_env()
URL = os.getenv("SHEETS_WEBAPP_URL")
SECRET = os.getenv("SHEETS_WEBAPP_SECRET", "")


def main():
    if len(sys.argv) < 3:
        print("usage: python sheets_push.py <마크다운파일> <아침|저녁|요청> [YYYY-MM-DD]")
        sys.exit(1)
    if not URL:
        print("[Error] .env 에 SHEETS_WEBAPP_URL 이 없습니다.")
        sys.exit(1)
    path, session = sys.argv[1], sys.argv[2]
    date_str = sys.argv[3] if len(sys.argv) > 3 else datetime.now().strftime("%Y-%m-%d")

    if not os.path.isfile(path):
        print(f"[Error] 파일 없음: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        print("[Error] 내용이 비어 있습니다.")
        sys.exit(1)

    title = f"{date_str} {session} 신문 브리핑"
    try:
        r = requests.post(
            URL,
            json={"token": SECRET, "date": date_str, "session": session,
                  "title": title, "content": content},
            timeout=30,
        )
        ok = False
        try:
            ok = bool(r.json().get("ok"))
        except Exception:
            ok = (r.status_code == 200)
        if ok:
            print("✅ 구글 시트 저장 성공!")
            sys.exit(0)
        print(f"[Error] 시트 저장 실패: HTTP {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"[Error] 시트 전송 예외: {e}")
    sys.exit(1)


if __name__ == "__main__":
    main()
