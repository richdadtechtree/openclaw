#!/usr/bin/env python3
"""
slack_log.py — 시스템이 슬랙으로 보낸 메시지를 날짜별 JSONL 로 기록.

슬랙 접속이 안 되는 환경에서 '그날 슬랙에 올라온 내용'을 웹앱(아티팩트)으로
읽기 위한 로그 수집기. 각 전송 지점에서 성공 후 log_slack(...) 을 호출한다.

저장: ~/.openclaw/slack_logs/YYYY-MM-DD.jsonl  (KST 기준, gitignored)
각 줄: {"ts": ISO8601, "source": "news|stock-briefing|custom-alert|sidecar|...",
        "channel": "C...", "kind": "text|image", "text": "..."}

원칙: 로깅 실패가 전송 흐름을 막으면 안 되므로 절대 예외를 올리지 않는다.
      (openclaw scripts/ 와 stock/ 양쪽에 동일 파일을 두어 각자 import.)
"""
import json
import os
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo("Asia/Seoul")
except Exception:  # pragma: no cover
    _KST = None

LOG_DIR = os.path.expanduser("~/.openclaw/slack_logs")


def _now():
    return datetime.now(_KST) if _KST else datetime.now()


def log_slack(text, source="unknown", channel=None, kind="text"):
    """슬랙 전송 내용을 하루치 JSONL 에 append. 조용히 실패."""
    try:
        if not text:
            return
        now = _now()
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, now.strftime("%Y-%m-%d") + ".jsonl")
        rec = {
            "ts": now.isoformat(timespec="seconds"),
            "source": source,
            "channel": channel or "",
            "kind": kind,
            "text": text,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 로깅 실패가 전송을 막으면 안 됨
