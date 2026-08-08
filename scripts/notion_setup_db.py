#!/usr/bin/env python3
"""
notion_setup_db.py — 지정한 노션 '페이지' 안에 브리핑용 데이터베이스를 새로 만든다 (1회성).

왜 필요한가:
  노션의 '신형(멀티소스) 데이터베이스'나 페이지 안 인라인 DB는 REST API(2022-06-28)로
  database_id 로 직접 읽기/쓰기가 안 될 수 있다(GET 400). 이 스크립트가 REST API 로
  직접 DB를 생성하면, 같은 API 를 쓰는 notion_push.py 가 100% 읽고 쓸 수 있다.

사용:
  python3 scripts/notion_setup_db.py [부모페이지ID] [DB제목] [--page "중간페이지제목"]
  - 부모페이지ID 생략 시 기본값 = "⭐ AI꿀팁 모음" 페이지.
  - DB제목       생략 시 기본값 = "신문 브리핑".
  - --page "제목" 주면: 부모 안에 그 이름의 '페이지'를 먼저 만들고, DB를 그 페이지 안에 넣는다.
      예) python3 scripts/notion_setup_db.py --page "AI꿀팁"
          → ⭐ AI꿀팁 모음 / AI꿀팁(새 페이지) / 신문 브리핑(DB) 구조 생성.

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


def create_database(parent_page_id, db_title, with_session=False):
    props = {
        PROP_TITLE: {"title": {}},
        PROP_DATE: {"date": {}},
        "URL": {"url": {}},
    }
    if with_session:  # 신문 브리핑처럼 아침/저녁 구분이 필요할 때만
        props[PROP_SESSION] = {"multi_select": {"options": [
            {"name": "아침", "color": "red"},
            {"name": "저녁", "color": "yellow"},
        ]}}
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": db_title}}],
        "properties": props,
    }
    r = requests.post(f"{API}/databases", headers=_headers(), json=payload, timeout=30)
    if r.status_code != 200:
        print(f"[Error] DB 생성 실패: HTTP {r.status_code} {r.text[:400]}")
        return None
    return r.json()


def create_wrapper_page(parent_page_id, title):
    """부모 페이지 안에 하위 '페이지'를 만든다. 성공 시 새 페이지 id 반환."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {"title": {"title": [{"text": {"content": title}}]}},
    }
    r = requests.post(f"{API}/pages", headers=_headers(), json=payload, timeout=30)
    if r.status_code != 200:
        print(f"[Error] 페이지 생성 실패: HTTP {r.status_code} {r.text[:400]}")
        return None
    return r.json()


def main():
    if not NOTION_TOKEN:
        print("[Error] .env 에 NOTION_TOKEN 이 없습니다.")
        sys.exit(1)

    # 옵션 파싱
    #   --page "제목"  : DB를 새로 만든 하위 페이지 안에 넣는다.
    #   --env  VARNAME : .env 에 넣을 변수명을 지정(예: NOTION_BOOK_TARGET). 기본 NOTION_BRIEFING_TARGET.
    #   --session      : 시간대(아침/저녁) 컬럼 추가(신문 브리핑용). 기본 없음.
    args = sys.argv[1:]
    wrapper_title = None
    env_name = "NOTION_BRIEFING_TARGET"
    with_session = False
    if "--session" in args:
        with_session = True
        args.remove("--session")
    if "--page" in args:
        i = args.index("--page")
        if i + 1 >= len(args):
            print("[Error] --page 뒤에 페이지 제목을 적어주세요. 예: --page \"AI꿀팁\"")
            sys.exit(1)
        wrapper_title = args[i + 1]
        del args[i:i + 2]
    if "--env" in args:
        i = args.index("--env")
        if i + 1 >= len(args):
            print("[Error] --env 뒤에 변수명을 적어주세요. 예: --env NOTION_BOOK_TARGET")
            sys.exit(1)
        env_name = args[i + 1]
        del args[i:i + 2]

    parent = args[0] if len(args) > 0 else DEFAULT_PARENT_PAGE
    title = args[1] if len(args) > 1 else DEFAULT_DB_TITLE

    # 1) (옵션) 중간 페이지 생성 → 그 페이지를 DB의 부모로 사용
    if wrapper_title:
        page = create_wrapper_page(parent, wrapper_title)
        if not page:
            print("❌ 실패 — 통합이 부모 페이지에 공유(연결)돼 있는지 확인하세요.")
            sys.exit(1)
        parent = page["id"]
        print(f"✅ 페이지 생성: '{wrapper_title}'  ({page.get('url', '')})")

    # 2) DB 생성
    db = create_database(parent, title, with_session=with_session)
    if not db:
        print("❌ 실패 — 통합이 부모 페이지에 공유(연결)돼 있는지 확인하세요.")
        sys.exit(1)

    db_id = db["id"].replace("-", "")
    url = db.get("url", "")
    print("✅ DB 생성 성공!")
    print(f"   제목       : {title}")
    print(f"   database_id: {db_id}")
    if url:
        print(f"   url        : {url}")
    print(f"DB_ID={db_id}")  # 스크립트에서 파싱하기 쉬운 한 줄
    print()
    print("아래 한 줄을 .env 에 반영하세요(기존 값 대체):")
    print(f"   {env_name}={db_id}")
    sys.exit(0)


if __name__ == "__main__":
    main()
