#!/usr/bin/env python3
"""
notion_push.py — 브리핑 마크다운 파일을 노션에 페이지로 저장 (독립 실행)

사용:
  python notion_push.py <브리핑md파일> <아침|저녁> [YYYY-MM-DD]

필요 (.env):
  NOTION_TOKEN            노션 내부 통합 토큰 (ntn_... / secret_...)
  NOTION_BRIEFING_TARGET  대상 ID (32자 hex, 대시 유무 무관).
                          데이터베이스 ID면 → 해당 DB에 행으로 저장.
                          페이지 ID면      → 해당 페이지의 하위 페이지로 저장.
  (하위호환) NOTION_BRIEFING_DB 도 계속 지원 — TARGET 이 없으면 이 값을 사용.

대상 종류는 실행 시 자동 감지한다(DB인지 페이지인지 몰라도 됨):
  - 데이터베이스: 속성 제목(title)/날짜(date)/시간대(multi_select: 아침/저녁) 사용.
    속성 이름이 다르면 아래 PROP_* 상수를 맞춰 수정하세요.
  - 페이지: 하위 페이지로 생성. 날짜/시간대는 본문 첫 줄에 함께 기록한다
    (일반 페이지 하위에는 title 외 속성을 설정할 수 없기 때문).
"""
import os
import re
import sys
from datetime import datetime

import requests


def load_env():
    """python-dotenv 없이 openclaw 루트의 .env 를 읽어 환경변수로 로드."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # openclaw 루트
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

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
# 대상 ID: TARGET 우선, 없으면 하위호환용 DB 변수 사용.
NOTION_TARGET = os.getenv("NOTION_BRIEFING_TARGET") or os.getenv("NOTION_BRIEFING_DB")
NOTION_VERSION = "2022-06-28"

# DB 속성 이름 (노션 DB와 다르면 여기만 고치면 됨)
PROP_TITLE = "제목"
PROP_DATE = "날짜"
PROP_SESSION = "시간대"

API = "https://api.notion.com/v1"
MAX_TEXT = 1900          # 노션 rich_text 1개 최대 2000자 → 여유
MAX_BLOCKS_PER_CALL = 90  # 한 요청당 100 블록 제한 → 여유


def _headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _chunks(text, n=MAX_TEXT):
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def _rt(text):
    """rich_text 배열 (긴 문자열은 자동 분할)."""
    return [{"type": "text", "text": {"content": c}} for c in _chunks(text)]


def md_to_blocks(md):
    """마크다운을 노션 블록으로 (헤딩/불릿/문단, 굵기·링크는 평문 유지)."""
    blocks = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        h = re.match(r"^(#{1,3})\s+(.*)", line)
        if h:
            level = len(h.group(1))
            key = f"heading_{level}"
            blocks.append({"object": "block", "type": key,
                           key: {"rich_text": _rt(h.group(2))}})
        elif re.match(r"^\s*[-*]\s+", line):
            txt = re.sub(r"^\s*[-*]\s+", "", line)
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _rt(txt)}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": _rt(line)}})
    return blocks


def detect_target_kind(target_id):
    """대상 ID 가 데이터베이스인지 일반 페이지인지 자동 감지.

    반환: "database" | "page" | None(둘 다 아님/접근 불가)
    """
    rd = requests.get(f"{API}/databases/{target_id}", headers=_headers(), timeout=30)
    if rd.status_code == 200:
        return "database"
    rp = requests.get(f"{API}/pages/{target_id}", headers=_headers(), timeout=30)
    if rp.status_code == 200:
        return "page"
    print(f"[Error] 대상 ID 확인 실패 (DB {rd.status_code} / 페이지 {rp.status_code}). "
          f"통합이 해당 페이지/DB에 공유돼 있는지 확인하세요.")
    return None


def create_page(title, date_str, session, blocks):
    if not NOTION_TOKEN or not NOTION_TARGET:
        print("[Error] .env 에 NOTION_TOKEN / NOTION_BRIEFING_TARGET(또는 NOTION_BRIEFING_DB) 가 없습니다.")
        return False

    kind = detect_target_kind(NOTION_TARGET)
    if kind is None:
        return False

    if kind == "database":
        first_content = blocks[:MAX_BLOCKS_PER_CALL]
        payload = {
            "parent": {"database_id": NOTION_TARGET},
            "properties": {
                PROP_TITLE: {"title": [{"text": {"content": title}}]},
                PROP_DATE: {"date": {"start": date_str}},
                # 시간대는 multi_select 타입 (DB 스키마 기준)
                PROP_SESSION: {"multi_select": [{"name": session}]},
            },
            "children": first_content,
        }
        consumed = len(first_content)
    else:  # page → 하위 페이지로 생성 (title 외 속성 불가 → 날짜/시간대는 본문에)
        meta_block = {"object": "block", "type": "paragraph",
                      "paragraph": {"rich_text": _rt(f"📅 {date_str} · 🕘 {session}")}}
        first_content = blocks[:MAX_BLOCKS_PER_CALL - 1]  # 메타 블록 1개 자리 확보
        payload = {
            "parent": {"page_id": NOTION_TARGET},
            "properties": {
                "title": {"title": [{"text": {"content": title}}]},
            },
            "children": [meta_block] + first_content,
        }
        consumed = len(first_content)

    r = requests.post(f"{API}/pages", headers=_headers(), json=payload, timeout=30)
    if r.status_code != 200:
        print(f"[Error] 페이지 생성 실패: HTTP {r.status_code} {r.text[:400]}")
        return False
    page_id = r.json()["id"]

    # 첫 요청에 못 담은 초과분은 append 로 이어붙임
    rest = blocks[consumed:]
    while rest:
        batch, rest = rest[:MAX_BLOCKS_PER_CALL], rest[MAX_BLOCKS_PER_CALL:]
        ra = requests.patch(f"{API}/blocks/{page_id}/children",
                            headers=_headers(), json={"children": batch}, timeout=30)
        if ra.status_code != 200:
            print(f"[Warn] 블록 이어붙이기 일부 실패: HTTP {ra.status_code} {ra.text[:200]}")
            break
    return True


def main():
    if len(sys.argv) < 3:
        print("사용법: python notion_push.py <브리핑md파일> <아침|저녁> [YYYY-MM-DD]")
        sys.exit(1)
    path, session = sys.argv[1], sys.argv[2]
    date_str = sys.argv[3] if len(sys.argv) > 3 else datetime.now().strftime("%Y-%m-%d")

    if not os.path.isfile(path):
        print(f"[Error] 파일 없음: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        md = f.read().strip()
    if not md:
        print("[Error] 브리핑 내용이 비어 있습니다.")
        sys.exit(1)

    title = f"{date_str} {session} 신문 브리핑"
    blocks = md_to_blocks(md)
    ok = create_page(title, date_str, session, blocks)
    print("✅ 노션 저장 성공!" if ok else "❌ 노션 저장 실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
