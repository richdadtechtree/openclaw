#!/usr/bin/env python3
"""
slack_text.py — 마크다운 파일 내용을 슬랙 채널에 텍스트로 게시 (길면 자동 분할)

사용:  python slack_text.py <마크다운파일>

필요 (.env, openclaw 루트):
  SLACK_BOT_TOKEN      슬랙 봇 토큰 (xoxb-..., chat:write 스코프)
  SLACK_NEWS_CHANNEL   신문 브리핑을 올릴 채널 ID (C...)
                       (없으면 SLACK_BRIEFING_CHANNEL 로 폴백)
"""
import os
import re
import sys

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
TOKEN = os.getenv("SLACK_BOT_TOKEN")
CHANNEL = os.getenv("SLACK_NEWS_CHANNEL")


def md_to_mrkdwn(md):
    """표준 마크다운을 슬랙 mrkdwn 으로 가볍게 변환."""
    out = []
    for line in md.splitlines():
        h = re.match(r"^#{1,6}\s+(.*)", line)
        if h:
            line = f"*{h.group(1).strip()}*"
        # [텍스트](URL) -> <URL|텍스트>
        line = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"<\2|\1>", line)
        # **굵게** -> *굵게*
        line = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", line)
        out.append(line)
    return "\n".join(out)


def chunk(text, limit=3500):
    parts, cur = [], ""
    for line in text.splitlines(keepends=True):
        if len(cur) + len(line) > limit and cur:
            parts.append(cur)
            cur = ""
        cur += line
    if cur:
        parts.append(cur)
    return parts or [text]


def post(text):
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Content-Type": "application/json; charset=utf-8"},
        json={"channel": CHANNEL, "text": text,
              "unfurl_links": False, "unfurl_media": False},
        timeout=30,
    ).json()
    return r.get("ok"), r


def main():
    if len(sys.argv) < 2:
        print("usage: python slack_text.py <마크다운파일>")
        sys.exit(1)
    if not TOKEN or not CHANNEL:
        print("[Error] .env 에 SLACK_BOT_TOKEN 또는 SLACK_NEWS_CHANNEL 이 없습니다.")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"[Error] 파일 없음: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        md = f.read().strip()
    if not md:
        print("[Error] 내용이 비어 있습니다.")
        sys.exit(1)

    parts = chunk(md_to_mrkdwn(md))
    ok_all = True
    for i, p in enumerate(parts, 1):
        prefix = f"📰 *신문 브리핑* ({i}/{len(parts)})\n" if len(parts) > 1 else "📰 *신문 브리핑*\n"
        ok, r = post(prefix + p)
        if not ok:
            print(f"[Error] 슬랙 전송 실패: {r}")
            ok_all = False
        else:
            try:
                from slack_log import log_slack
                log_slack(prefix + p, source="news", channel=CHANNEL)
            except Exception:
                pass
    print("✅ 슬랙 전송 성공!" if ok_all else "❌ 슬랙 전송 실패")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
