#!/usr/bin/env python3
"""
troubleshoot_log.py — 그날의 트러블슈팅 항목을 노션 'openclaw 트러블슈팅 로그' DB에 저장.

서버(노션 접근 가능한 환경)에서 매일 1회 실행되도록 설계됨. openclaw 크론(agentTurn)에서
뚜떵또가 그날 git 커밋을 요약해 JSON 으로 만든 뒤 이 스크립트로 넘겨 저장한다.
(claude.ai 샌드박스는 api.notion.com 이그레스가 막혀 있어 저장 불가 → 반드시 서버에서 실행.)

필요 (.env, openclaw 루트):
  NOTION_TROUBLESHOOT_TOKEN  이 DB에 공유된 노션 통합 토큰(ntn_.../secret_...).
                             없으면 NOTION_TOKEN 을 사용.
  (선택) NOTION_TROUBLESHOOT_DB / NOTION_TROUBLESHOOT_DS
                             대상 DB/데이터소스 ID(기본값은 아래 상수).

입력(JSON 배열) — --file 경로 또는 표준입력(stdin):
  [
    {
      "title":    "무엇을 고쳤는지 간결한 제목",   # 필수
      "category": "슬랙",                          # 주식/슬랙/노션/뉴스브리핑/인프라/설정
      "status":   "완료",                          # 완료/진행중 (기본 완료)
      "summary":  "한 줄 요약",                    # 표 '내용' 칸
      "body":     "### 🔎 한 줄 요약\n..."         # 페이지 본문(마크다운, 쉬운 설명)
    }
  ]

사용 예:
  # 오늘 커밋 미리보기 (노션 접근 없음)
  python3 scripts/troubleshoot_log.py --collect
  # 저장(중복 제목은 건너뜀)
  cat entries.json | python3 scripts/troubleshoot_log.py --dedupe
  python3 scripts/troubleshoot_log.py --file entries.json --date 2026-08-10 --dedupe
  # 실제 저장 없이 확인
  python3 scripts/troubleshoot_log.py --file entries.json --dry-run
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # openclaw 루트

# 대상(기본값). 필요 시 .env 로 덮어쓸 수 있음.
DEFAULT_DB = "283037a9-0502-4ab2-8134-6680fa6dbb4d"
DEFAULT_DS = "940b2105-7783-4b11-80a4-25996caae856"

CATEGORIES = ["주식", "슬랙", "노션", "뉴스브리핑", "인프라", "설정"]
STATUSES = ["완료", "진행중"]

API = "https://api.notion.com/v1"
V_OLD = "2022-06-28"      # database_id 기반
V_NEW = "2025-09-03"      # data_source_id 기반(신형 멀티소스 DB 대응)
MAX_TEXT = 1900
MAX_BLOCKS = 90
TIMEOUT = 30


def load_env():
    """python-dotenv 없이 openclaw 루트의 .env 를 읽어 환경변수로 로드."""
    for path in (os.path.join(BASE, ".env"), ".env"):
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

TOKEN = os.getenv("NOTION_TROUBLESHOOT_TOKEN") or os.getenv("NOTION_TOKEN")
DB_ID = os.getenv("NOTION_TROUBLESHOOT_DB") or DEFAULT_DB
DS_ID = os.getenv("NOTION_TROUBLESHOOT_DS") or DEFAULT_DS


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def _chunks(text, n=MAX_TEXT):
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def _rt(text):
    return [{"type": "text", "text": {"content": c}} for c in _chunks(text or "")]


def md_to_blocks(md):
    """마크다운 → 노션 블록(헤딩/불릿/문단). 굵기·링크는 평문 유지."""
    blocks = []
    for raw in (md or "").splitlines():
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


def git_commits(date_str):
    """지정 날짜(KST)의 git 커밋 목록 [{hash, date, subject}] 반환."""
    env = dict(os.environ, TZ="Asia/Seoul")
    fmt = "%h\x1f%ad\x1f%s"
    cmd = ["git", "-C", BASE, "log",
           f"--after={date_str}T00:00:00", f"--before={date_str}T23:59:59",
           "--date=local", f"--pretty=format:{fmt}"]
    try:
        out = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"[Error] git 실행 실패: {e}", file=sys.stderr)
        return []
    commits = []
    for line in out.stdout.splitlines():
        if "\x1f" not in line:
            continue
        h, ad, subj = line.split("\x1f", 2)
        commits.append({"hash": h, "date": ad, "subject": subj})
    return commits


def _headers(version):
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Notion-Version": version,
        "Content-Type": "application/json",
    }


def probe():
    """이 DB에 어떤 API 버전/부모 형태로 접근 가능한지 탐지.

    반환: (version, parent_dict, query_url) 또는 (None, None, None).
    """
    # 1) 구버전(database_id)
    r = requests.get(f"{API}/databases/{DB_ID}", headers=_headers(V_OLD), timeout=TIMEOUT)
    if r.status_code == 200:
        return V_OLD, {"database_id": DB_ID}, f"{API}/databases/{DB_ID}/query"
    # 2) 신버전(data_source_id)
    r2 = requests.get(f"{API}/data_sources/{DS_ID}", headers=_headers(V_NEW), timeout=TIMEOUT)
    if r2.status_code == 200:
        return (V_NEW, {"type": "data_source_id", "data_source_id": DS_ID},
                f"{API}/data_sources/{DS_ID}/query")
    print(f"[Error] DB 접근 실패 (구버전 {r.status_code} / 신버전 {r2.status_code}). "
          f"통합 토큰이 이 DB에 공유돼 있는지 확인하세요.\n"
          f"  구버전 응답: {r.text[:200]}\n  신버전 응답: {r2.text[:200]}",
          file=sys.stderr)
    return None, None, None


def existing_titles(query_url, version, date_str):
    """해당 날짜에 이미 저장된 제목 집합(중복 방지용)."""
    titles = set()
    payload = {"filter": {"property": "날짜", "date": {"equals": date_str}}, "page_size": 100}
    cursor = None
    while True:
        if cursor:
            payload["start_cursor"] = cursor
        r = requests.post(query_url, headers=_headers(version), json=payload, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"[Warn] 기존 항목 조회 실패(HTTP {r.status_code}) → 중복검사 생략: "
                  f"{r.text[:200]}", file=sys.stderr)
            return titles
        data = r.json()
        for pg in data.get("results", []):
            prop = pg.get("properties", {}).get("제목", {})
            for t in prop.get("title", []):
                titles.add(t.get("plain_text", "").strip())
        if data.get("has_more"):
            cursor = data.get("next_cursor")
        else:
            break
    return titles


def build_properties(entry, date_str):
    title = (entry.get("title") or "").strip()
    props = {
        "제목": {"title": [{"text": {"content": title}}]},
        "날짜": {"date": {"start": date_str}},
    }
    summary = (entry.get("summary") or "").strip()
    if summary:
        props["내용"] = {"rich_text": _rt(summary)}
    cat = (entry.get("category") or "").strip()
    if cat in CATEGORIES:
        props["카테고리"] = {"select": {"name": cat}}
    status = (entry.get("status") or "완료").strip()
    if status in STATUSES:
        props["상태"] = {"select": {"name": status}}
    return props


def create_entry(entry, date_str, version, parent, query_url):
    props = build_properties(entry, date_str)
    blocks = md_to_blocks(entry.get("body") or entry.get("summary") or "")
    first = blocks[:MAX_BLOCKS]
    payload = {"parent": parent, "properties": props, "children": first}
    r = requests.post(f"{API}/pages", headers=_headers(version), json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        print(f"[Error] 생성 실패 '{entry.get('title')}': HTTP {r.status_code} {r.text[:300]}",
              file=sys.stderr)
        return False
    page_id = r.json()["id"]
    rest = blocks[MAX_BLOCKS:]
    while rest:
        batch, rest = rest[:MAX_BLOCKS], rest[MAX_BLOCKS:]
        ra = requests.patch(f"{API}/blocks/{page_id}/children",
                            headers=_headers(version), json={"children": batch}, timeout=TIMEOUT)
        if ra.status_code != 200:
            print(f"[Warn] 블록 이어붙이기 일부 실패: HTTP {ra.status_code}", file=sys.stderr)
            break
    return True


def read_entries(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = sys.stdin.read()
    raw = raw.strip()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return data


def main():
    ap = argparse.ArgumentParser(description="트러블슈팅 항목을 노션에 저장")
    ap.add_argument("--file", help="입력 JSON 파일 경로(생략 시 stdin)")
    ap.add_argument("--date", default=today_kst(), help="날짜 YYYY-MM-DD(기본: 오늘 KST)")
    ap.add_argument("--dedupe", action="store_true", help="같은 날짜에 동일 제목이 있으면 건너뜀")
    ap.add_argument("--dry-run", action="store_true", help="실제 저장 없이 미리보기")
    ap.add_argument("--collect", action="store_true", help="해당 날짜 git 커밋만 JSON 출력(노션 접근 없음)")
    args = ap.parse_args()

    if args.collect:
        print(json.dumps(git_commits(args.date), ensure_ascii=False, indent=2))
        return 0

    try:
        entries = read_entries(args)
    except Exception as e:  # noqa: BLE001
        print(f"[Error] 입력 JSON 파싱 실패: {e}", file=sys.stderr)
        return 1
    entries = [e for e in entries if (e.get("title") or "").strip()]
    if not entries:
        print("저장할 항목이 없습니다(빈 입력). 종료.")
        return 0

    if args.dry_run:
        print(f"[dry-run] 날짜 {args.date} · {len(entries)}건 저장 예정:")
        for e in entries:
            print(f"  - [{e.get('category','?')}/{e.get('status','완료')}] {e.get('title')}")
        return 0

    if not TOKEN:
        print("[Error] .env 에 NOTION_TROUBLESHOOT_TOKEN 또는 NOTION_TOKEN 이 없습니다.",
              file=sys.stderr)
        return 1

    version, parent, query_url = probe()
    if version is None:
        return 1

    skip = set()
    if args.dedupe:
        skip = existing_titles(query_url, version, args.date)

    saved, skipped, failed = 0, 0, 0
    for e in entries:
        title = (e.get("title") or "").strip()
        if args.dedupe and title in skip:
            skipped += 1
            continue
        if create_entry(e, args.date, version, parent, query_url):
            saved += 1
            skip.add(title)
        else:
            failed += 1

    print(f"✅ 저장 {saved}건 · 중복건너뜀 {skipped}건 · 실패 {failed}건 (날짜 {args.date})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
