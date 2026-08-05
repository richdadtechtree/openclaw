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


def _fetch_slack_history_api(date_str):
    import requests
    from datetime import timezone, timedelta
    try:
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            return []
        
        # Configure channels to pull from
        news_ch = os.getenv("SLACK_NEWS_CHANNEL")
        alert_ch = os.getenv("SLACK_ALERT_CHANNEL")
        brief_ch = os.getenv("SLACK_BRIEFING_CHANNEL")
        
        channels = []
        if news_ch:
            channels.append((news_ch, "news"))
        if alert_ch:
            channels.append((alert_ch, "stock"))
        if brief_ch:
            channels.append((brief_ch, "stock"))
        
        seen_channels = set()
        unique_channels = []
        for ch, room_name in channels:
            if ch not in seen_channels:
                seen_channels.add(ch)
                unique_channels.append((ch, room_name))
                
        if not unique_channels:
            return []

        # Start and end of the day in KST (UTC+9)
        dt_start = datetime.strptime(date_str, "%Y-%m-%d")
        kst_tz = timezone(timedelta(hours=9))
        dt_start_kst = datetime(dt_start.year, dt_start.month, dt_start.day, tzinfo=kst_tz)
        ts_start = dt_start_kst.timestamp()
        ts_end = ts_start + 24 * 3600
        
        headers = {"Authorization": f"Bearer {token}"}
        
        all_messages = []
        for channel, room_name in unique_channels:
            params = {
                "channel": channel,
                "oldest": str(ts_start),
                "latest": str(ts_end),
                "limit": 200
            }
            res = requests.get("https://slack.com/api/conversations.history", headers=headers, params=params, timeout=15).json()
            if not res.get("ok"):
                continue
                
            for msg in reversed(res.get("messages", [])):
                ts_val = float(msg.get("ts", 0))
                dt = datetime.fromtimestamp(ts_val, kst_tz)
                ts_iso = dt.isoformat(timespec="seconds")
                text = msg.get("text", "")
                
                bot_id = msg.get("bot_id")
                source = "unknown"
                if bot_id:
                    if "투자 타이밍 알림" in text:
                        source = "index-alert"
                    elif "시장 변동성 경보" in text:
                        source = "sidecar"
                    elif "관심 종목" in text:
                        source = "custom-alert"
                    elif "신문 브리핑" in text:
                        source = "news"
                    elif "시장 브리핑" in text or "주식 브리핑" in text:
                        source = "stock-briefing"
                    else:
                        source = "bot"
                else:
                    source = "user"
                    
                all_messages.append({
                    "ts": ts_iso,
                    "source": source,
                    "kind": "text",
                    "text": text,
                    "room": room_name
                })
        return all_messages
    except Exception as e:
        print(f"[Slack API History] Fetch failed: {e}", file=sys.stderr)
        return []


def main():
    # Load .env variables first to read SLACK_BOT_TOKEN
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for env_path in (os.path.join(base, ".env"), ".env"):
        if os.path.isfile(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            break

    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = (datetime.now(KST) if KST else datetime.now()).strftime("%Y-%m-%d")

    path = os.path.join(LOG_DIR, f"{date}.jsonl")
    local_msgs = []
    
    news_ch = os.getenv("SLACK_NEWS_CHANNEL")
    alert_ch = os.getenv("SLACK_ALERT_CHANNEL")
    brief_ch = os.getenv("SLACK_BRIEFING_CHANNEL")
    
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
                
                ch_id = rec.get("channel", "")
                room_name = "other"
                if news_ch and ch_id == news_ch:
                    room_name = "news"
                elif (alert_ch and ch_id == alert_ch) or (brief_ch and ch_id == brief_ch):
                    room_name = "stock"
                elif rec.get("source") in ["index-alert", "sidecar", "custom-alert", "stock-briefing"]:
                    room_name = "stock"
                elif rec.get("source") in ["news"]:
                    room_name = "news"
                    
                local_msgs.append({
                    "ts": rec.get("ts", ""),
                    "source": rec.get("source", "unknown"),
                    "kind": rec.get("kind", "text"),
                    "text": rec.get("text", ""),
                    "room": room_name
                })
                
    api_msgs = _fetch_slack_history_api(date)
    seen = set()
    merged = []
    
    for m in api_msgs:
        key = (m["ts"][:16], m["text"][:50])
        seen.add(key)
        merged.append(m)
        
    for m in local_msgs:
        key = (m["ts"][:16], m["text"][:50])
        if key not in seen:
            seen.add(key)
            merged.append(m)
            
    merged.sort(key=lambda m: m["ts"])

    print(json.dumps({"date": date, "messages": merged}, ensure_ascii=False))
    print(f"\n# {len(merged)}개 메시지 ({date}). 위 JSON 한 줄을 복사해 Claude 에게 붙이세요.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
