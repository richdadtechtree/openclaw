#!/usr/bin/env python3
"""
slack_digest.py — 하루치 슬랙 로그(JSONL)를 데일리 다이제스트 아티팩트용 JSON 으로 출력.

슬랙 뷰어 아티팩트(claude.ai)에 '그날 실제 내용'을 채우기 위한 도구.
slack_log.py 가 ~/.openclaw/slack_logs/<날짜>.jsonl 에 쌓아둔 발신 메시지를 읽어
아티팩트의 DATA 형식({date, messages[]})으로 한 줄 JSON 을 stdout 에 출력한다.

사용:
  python3 ~/.openclaw/scripts/slack_digest.py             # 오늘(KST)
  python3 ~/.openclaw/scripts/slack_digest.py 2026-08-05  # 특정 날짜

→ 출력된 JSON 한 줄을 복사해 Claude 에게 붙이면, 아티팩트가 그날 실데이터로 갱신됨.
"""
import json
import os
import sys
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = None

LOG_DIR = os.path.expanduser("~/.openclaw/slack_logs")


def main():
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = (datetime.now(KST) if KST else datetime.now()).strftime("%Y-%m-%d")

    path = os.path.join(LOG_DIR, f"{date}.jsonl")
    msgs = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                # 아티팩트에 필요한 필드만 추림
                msgs.append({
                    "ts": rec.get("ts", ""),
                    "source": rec.get("source", "unknown"),
                    "kind": rec.get("kind", "text"),
                    "text": rec.get("text", ""),
                })
    msgs.sort(key=lambda m: m.get("ts", ""))

    print(json.dumps({"date": date, "messages": msgs}, ensure_ascii=False))
    print(f"\n# {len(msgs)}개 메시지 ({date}). 위 JSON 한 줄을 복사해 Claude 에게 붙이세요.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
