#!/usr/bin/env python3
"""
patch_scheduler_slack.py — stock/scheduler.py 의 alert_job 에 슬랙 관심종목 알림
연결(stock_alert_slack.notify_events)을 자동 삽입하는 일회성 패처.

무엇을 하나:
  alert_job 안에서 관심 종목 텔레그램을 보내는 줄
      sent = send_telegram_message(custom_message)
  **바로 다음**에 아래 블록을 같은 들여쓰기로 삽입:
      try:
          import stock_alert_slack as sas
          sas.notify_events(custom_events)   # 게이팅 통과분만 슬랙 전송
      except Exception as _e:
          print(f"[Warn] Slack custom alert failed: {_e}")

특징:
  - 멱등: 이미 'stock_alert_slack' 이 파일에 있으면 아무것도 안 함.
  - 백업: scheduler.py.bak-slack-<epoch> 로 원본 보존.
  - 검증: 삽입 후 ast.parse 로 문법 확인, 실패 시 원복.
  - 텔레그램 로직은 건드리지 않음(슬랙만 추가).

사용(서버):
  cp ~/.openclaw/scripts/stock_alert_slack.py ~/stock/stock/
  cd ~/stock/stock && venv/bin/python ~/.openclaw/scripts/patch_scheduler_slack.py
  # 또는 대상 경로 지정:
  venv/bin/python ~/.openclaw/scripts/patch_scheduler_slack.py /경로/scheduler.py
그 뒤: systemctl --user restart stock-dashboard   (또는 scheduler 재실행)
"""
import ast
import os
import re
import sys
import time

MARKER = "stock_alert_slack"
# 관심 종목 텔레그램 전송 지점 (custom_message 변수로 특정)
ANCHOR = re.compile(
    r"^(?P<indent>[ \t]*)(?P<lhs>[A-Za-z_][\w]*\s*=\s*)?send_telegram_message\(\s*custom_message\s*\)[ \t]*$",
    re.MULTILINE,
)


def build_block(indent):
    inner = indent + "    "
    return "\n".join([
        f"{indent}try:",
        f"{inner}import stock_alert_slack as sas",
        f"{inner}sas.notify_events(custom_events)   # 게이팅 통과분만 슬랙 전송",
        f"{indent}except Exception as _e:",
        f'{inner}print(f"[Warn] Slack custom alert failed: {{_e}}")',
    ])


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/stock/stock/scheduler.py")
    if not os.path.isfile(path):
        print(f"[Error] 파일 없음: {path}")
        sys.exit(1)

    src = open(path, encoding="utf-8").read()

    if MARKER in src:
        print(f"ℹ️ 이미 슬랙 연결이 있습니다({MARKER}). 변경 없음: {path}")
        sys.exit(0)

    m = ANCHOR.search(src)
    if not m:
        print("[Error] 삽입 기준 줄을 못 찾음: 'send_telegram_message(custom_message)'.")
        print("        scheduler.py alert_job 를 직접 확인하세요.")
        sys.exit(2)

    indent = m.group("indent")
    block = build_block(indent)
    anchor_line = m.group(0)
    new_src = src[:m.end()] + "\n" + block + src[m.end():]

    # 문법 검증
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"[Error] 삽입 후 문법 오류로 중단(원본 보존): {e}")
        sys.exit(3)

    backup = f"{path}.bak-slack-{int(time.time())}"
    with open(backup, "w", encoding="utf-8") as f:
        f.write(src)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"✅ 삽입 완료: {path}")
    print(f"   기준 줄: {anchor_line.strip()}")
    print(f"   백업:    {backup}")
    print("   다음: systemctl --user restart stock-dashboard  (또는 scheduler 재실행)")


if __name__ == "__main__":
    main()
