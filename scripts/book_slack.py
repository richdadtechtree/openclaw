#!/usr/bin/env python3
"""
book_slack.py — 노션 독서 글귀를 **슬랙에 직접** 보낸다. (AI를 거치지 않음)

왜 이 스크립트가 필요한가
------------------------
지금까지는 스케줄이 **AI 에이전트에게 "책 글귀 보내"라고 시키는** 구조였다.
그러다 보니 AI가 스크립트를 실행하지 않고 자기 말로 지어내는 사고가 났다.

    "'전자책 쓰기' 책에서 주목할 만한 문장입니다."   ← 노션에 없는 AI 창작
    <전자책 쓰기>

이 스크립트는 **AI를 경로에서 뺀다.** 노션 → 슬랙으로 바로 간다.
글귀가 없으면 **아무것도 보내지 않고 조용히 끝난다.** 지어낼 주체가 아예 없다.

사용법
------
  python3 ~/.openclaw/scripts/book_slack.py            # 뚜떵또 이름으로 발송(기본)
  python3 ~/.openclaw/scripts/book_slack.py --as bookman   # 책읽남 이름으로 발송
  python3 ~/.openclaw/scripts/book_slack.py --dry-run  # 보낼 내용만 확인(발송 안 함)
  python3 ~/.openclaw/scripts/book_slack.py --channel C0BMHERHA77
  python3 ~/.openclaw/scripts/book_slack.py --book 퓨처셀프

누가 보내나 (역할 분담)
----------------------
  📚 책읽남 = **자료 담당** — 노션에서 글귀를 찾아오는 일(`get_notion_book.py`)
  🤖 뚜떵또 = **최종 보고 담당** — 그 결과를 슬랙에 올리는 일(기본 발신자)

  즉 "책읽남이 찾아서 뚜떵또가 보고한다"는 구조를 그대로 따른다.
  다만 **중간에 AI가 문장을 다시 쓰지 않는다.** 찾은 글자를 그대로 올린다.
  발신자를 바꾸려면 `--as bookman` 또는 `.env` 의 `SLACK_BOOK_SENDER=bookman`.

필요한 환경변수 (~/.openclaw/.env)
---------------------------------
  NOTION_TOKEN             노션 통합 토큰 (get_notion_book.py 와 공용)
  SLACK_BOT_TOKEN_DEFAULT  뚜떵또 봇 토큰 (기본 발신자)
  SLACK_BOT_TOKEN_BOOKMAN  책읽남 봇 토큰 (`--as bookman` 일 때)
  SLACK_BOOK_SENDER        기본 발신자: `ddu`(기본) 또는 `bookman`
  SLACK_BOOK_CHANNEL       보낼 채널 ID (없으면 SLACK_BRIEFING_CHANNEL 폴백)

종료코드
--------
  0 = 보냈음    1 = 보낼 글귀가 없어 **아무것도 안 보냄**(정상, 조용히 종료)
  3 = 설정/통신 오류
"""

import argparse
import os
import subprocess
import sys
import time

try:
    import requests
except ModuleNotFoundError:                      # 시스템 python3 엔 requests 가 없을 수 있다
    sys.stderr.write(
        "❌ requests 모듈이 없습니다.\n"
        "   venv 파이썬으로 실행하세요. 예:\n"
        "     /home/ubuntu/newspaper/.venv/bin/python ~/.openclaw/scripts/book_slack.py\n"
        "   또는 설치: pip3 install -r ~/.openclaw/requirements.txt\n")
    sys.exit(3)

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                     # ~/.openclaw
PICKER = os.path.join(HERE, "get_notion_book.py")


def load_env():
    """python-dotenv 없이 openclaw 루트의 .env 를 읽어 환경변수로 올린다."""
    for path in (os.path.join(BASE, ".env"), ".env"):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


def pick_quote(book=None):
    """get_notion_book.py 를 실행해 글귀 2줄을 받아온다.

    반환: (본문, 출처)  — 글귀가 없으면 (None, 사유)
    ⚠️ 여기서 절대 대체 문구를 만들지 않는다. 없으면 없는 대로 None 을 돌려준다.
    """
    cmd = [sys.executable, PICKER]              # 같은 파이썬(venv 포함)으로 실행
    if book:
        cmd += ["--book", book]
    print("… 노션에서 글귀를 찾는 중 "
          "(캐시가 비어 있으면 책 본문을 읽느라 1~2분 걸릴 수 있습니다)", file=sys.stderr)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    print(f"… {time.time() - t0:.1f}초 걸림", file=sys.stderr)
    text = (r.stdout or "").strip()
    note = (r.stderr or "").strip()

    if r.returncode != 0 or not text:
        return None, note or f"get_notion_book.py 종료코드 {r.returncode}"

    # 안전장치: 최소 2줄(글귀 + <제목>)이 아니면 보내지 않는다.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None, f"출력이 2줄 미만이라 발송하지 않음: {text!r}"
    return text, note


def post_to_slack(text, channel, token):
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        json={"channel": channel, "text": text, "unfurl_links": False},
        timeout=30,
    )
    data = r.json()
    if not data.get("ok"):
        print(f"❌ 슬랙 발송 실패: {data.get('error')}", file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="노션 독서 글귀를 슬랙에 직접 발송")
    ap.add_argument("--dry-run", action="store_true", help="발송하지 않고 내용만 출력")
    ap.add_argument("--channel", help="보낼 채널 ID (기본: .env 설정)")
    ap.add_argument("--book", help="특정 책에서만 뽑기")
    ap.add_argument("--as", dest="sender", choices=["ddu", "bookman"],
                    help="누구 이름으로 보낼지 (기본: 뚜떵또)")
    args = ap.parse_args()

    load_env()

    text, note = pick_quote(args.book)

    # ── 핵심: 글귀가 없으면 아무것도 보내지 않는다 ──────────────────
    if text is None:
        print(f"ℹ️  보낼 글귀가 없어 발송하지 않았습니다. ({note})", file=sys.stderr)
        return 1        # 조용히 종료. 슬랙에는 아무 메시지도 가지 않는다.

    if note:
        print(note, file=sys.stderr)          # [출처] ... 는 로그로만

    if args.dry_run:
        print("── 보낼 내용 (실제 발송 안 함) ──")
        print(text)
        return 0

    # 발신자 선택: 인자 > .env 설정 > 기본값(뚜떵또)
    sender = args.sender or os.getenv("SLACK_BOOK_SENDER") or "ddu"
    if sender == "bookman":
        token = os.getenv("SLACK_BOT_TOKEN_BOOKMAN") or os.getenv("SLACK_BOT_TOKEN")
        who = "책읽남"
    else:
        token = os.getenv("SLACK_BOT_TOKEN_DEFAULT") or os.getenv("SLACK_BOT_TOKEN")
        who = "뚜떵또"
    channel = args.channel or os.getenv("SLACK_BOOK_CHANNEL") or os.getenv("SLACK_BRIEFING_CHANNEL")
    if not token:
        var = "SLACK_BOT_TOKEN_BOOKMAN" if sender == "bookman" else "SLACK_BOT_TOKEN_DEFAULT"
        print(f"❌ {var}(또는 SLACK_BOT_TOKEN)이 .env 에 없습니다.", file=sys.stderr)
        return 3
    if not channel:
        print("❌ SLACK_BOOK_CHANNEL(또는 SLACK_BRIEFING_CHANNEL)이 .env 에 없습니다.", file=sys.stderr)
        return 3

    if not post_to_slack(text, channel, token):
        return 3
    print(f"✅ {who} 이름으로 발송 완료 → {channel}")
    print("─" * 40)
    print(text)                                  # 실제로 보낸 내용을 로그에 남긴다
    return 0


if __name__ == "__main__":
    sys.exit(main())
