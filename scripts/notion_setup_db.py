#!/usr/bin/env python3
"""
notion_setup_db.py — 지정한 노션 '페이지' 안에 브리핑용 데이터베이스를 새로 만든다 (1회성).

왜 필요한가:
  노션의 '신형(멀티소스) 데이터베이스'나 페이지 안 인라인 DB는 REST API(2022-06-28)로
  database_id 로 직접 읽기/쓰기가 안 될 수 있다(GET 400). 이 스크립트가 REST API 로
  직접 DB를 생성하면, 같은 API 를 쓰는 notion_push.py 가 100% 읽고 쓸 수 있다.

사용:
  python3 scripts/notion_setup_db.py [부모페이지ID] [DB제목]
  - 부모페이지ID 생략 시 기본값 = "⭐ AI꿀팁 모음" 페이지.
  - DB제목    생략 시 기본값 = "신문 브리핑".

필요 (.env): NOTION_TOKEN

성공하면 새 database_id 와 .env 에 붙일 한 줄을 출력한다.
그 값을 NOTION_BRIEFING_TARGET 에 넣으면 이후 브리핑이 이 DB에 '행'으로 저장된다.
"""
import os
import sys

import requests

# notion_push.py 의 로더/상수를 재사용 (같은 폴더).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notion_push import (  # noqa: E402
    NOTION_TOKEN, NOTION_VERSION, API, _headers,
    PROP_TITLE, PROP_DATE, PROP_SESSION,
)

DEFAULT_PARENT_PAGE = "3b5d470c68bd80c1a88dfa79b4581de8"  # ⭐ AI꿀팁 모음
DEFAULT_DB_TITLE = "신문 브리핑"


def create_database(parent_page_id, db_title):
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": db_title}}],
        "properties": {
            PROP_TITLE: {"title": {}},
            PROP_DATE: {"date": {}},
            PROP_SESSION: {"multi_select": {"options": [
                {"name": "아침", "color": "red"},
                {"name": "저녁", "color": "yellow"},
            ]}},
        },
    }
    r = requests.post(f"{API}/databases", headers=_headers(), json=payload, timeout=30)
    if r.status_code != 200:
        print(f"[Error] DB 생성 실패: HTTP {r.status_code} {r.text[:400]}")
        return None
    return r.json()


def main():
    if not NOTION_TOKEN:
        print("[Error] .env 에 NOTION_TOKEN 이 없습니다.")
        sys.exit(1)
    parent = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PARENT_PAGE
    title = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DB_TITLE

    db = create_database(parent, title)
    if not db:
        print("❌ 실패 — 통합이 부모 페이지에 공유(연결)돼 있는지 확인하세요.")
        sys.exit(1)

    db_id = db["id"].replace("-", "")
    url = db.get("url", "")
    print("✅ DB 생성 성공!")
    print(f"   제목      : {title}")
    print(f"   database_id: {db_id}")
    if url:
        print(f"   url       : {url}")
    print()
    print("아래 한 줄을 .env 에 반영하세요(기존 값 대체):")
    print(f"   NOTION_BRIEFING_TARGET={db_id}")
    sys.exit(0)


if __name__ == "__main__":
    main()
