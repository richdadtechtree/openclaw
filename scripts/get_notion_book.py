#!/usr/bin/env python3
"""
get_notion_book.py — 노션 '독서 리스트'에서 **실제로 적혀 있는 문장만** 하나 뽑아온다.

핵심 원칙 (이 스크립트가 존재하는 이유)
---------------------------------------
책읽남(bookman)이 "노션에 없는 글귀"를 가져오는 사고를 막기 위한 스크립트다.
따라서 **지어내는 경로가 하나도 없다**:
  - 노션에서 읽어온 글자만 출력한다.
  - 쓸 만한 문장을 못 찾으면 기본 문구를 만들어내지 않고 **종료코드 2로 실패**한다.
  - 출력 끝에 출처 페이지 URL을 함께 찍어서 사람이 바로 대조할 수 있게 한다.

사용법
------
  python3 ~/.openclaw/scripts/get_notion_book.py             # 브리핑용 한 문장 출력
  python3 ~/.openclaw/scripts/get_notion_book.py --check     # 노션 데이터 상태 점검(어디가 비었나)
  python3 ~/.openclaw/scripts/get_notion_book.py --list 20   # 뽑을 수 있는 문장 미리보기
  python3 ~/.openclaw/scripts/get_notion_book.py --book 그릿  # 특정 책에서만 뽑기
  python3 ~/.openclaw/scripts/get_notion_book.py --reset     # 중복방지 기록 초기화

필요한 환경변수 (~/.openclaw/.env)
---------------------------------
  NOTION_TOKEN        노션 내부 통합(integration) 토큰 (ntn_... / secret_...)
  NOTION_READING_DB   (선택) 독서 리스트 DB ID. 없으면 아래 기본값 사용.

종료코드
--------
  0 = 정상 출력   2 = 노션에 쓸 문장이 없음(절대 지어내지 말 것)   3 = 설정/통신 오류
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys

import requests

# ── 0. 기본 설정 ───────────────────────────────────────────────
# '독서 기록 > 독서 리스트' 데이터베이스 ID (대시 있어도/없어도 동작)
DEFAULT_DB_ID = "678f2c0b-d124-4889-8571-b019ec30f971"
API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# 문장으로 인정할 최소/최대 길이 (너무 짧은 조각·너무 긴 문단 덩어리를 걸러낸다)
MIN_LEN = 10
MAX_LEN = 220

# 문장을 찾아볼 프로퍼티 이름.
# ⚠️ 노션 실제 이름이 "깨달은 점 "처럼 **뒤에 공백**이 붙어 있는 경우가 있어서,
#    아래 lookup 함수는 공백을 지우고 비교한다(이 함수가 없으면 항상 빈값이 나온다).
PROP_TITLE = "책 제목"
PROP_AUTHOR = "저자"
PROP_SENTENCE = "한 문장"
PROP_INSIGHT = "깨달은 점"

# 중복 방지 기록 파일 (한 번 보낸 문장은 다 돌 때까지 다시 안 보낸다)
STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "workspace", "bookman", "book_sequence_state.json",
)


# ── 1. .env 읽기 ──────────────────────────────────────────────
def load_env():
    """python-dotenv 없이 openclaw 루트의 .env 를 읽어 환경변수로 올린다."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ~/.openclaw
    for path in (os.path.join(base, ".env"), ".env"):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break


# ── 2. 노션 API 호출 헬퍼 ──────────────────────────────────────
def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def api_get(token, path, params=None):
    r = requests.get(f"{API}{path}", headers=_headers(token), params=params, timeout=30)
    if r.status_code != 200:
        die(f"노션 GET {path} 실패 ({r.status_code}): {r.text[:300]}")
    return r.json()


def api_post(token, path, payload):
    r = requests.post(f"{API}{path}", headers=_headers(token), json=payload, timeout=30)
    if r.status_code != 200:
        die(f"노션 POST {path} 실패 ({r.status_code}): {r.text[:300]}")
    return r.json()


def die(msg, code=3):
    """설정/통신 오류는 조용히 넘기지 않고 크게 알린다(=agent가 지어내지 못하게)."""
    print(f"❌ [get_notion_book] {msg}", file=sys.stderr)
    sys.exit(code)


# ── 3. 프로퍼티/블록에서 '평문 텍스트' 뽑기 ─────────────────────
def _norm(name):
    """프로퍼티 이름 비교용: 공백을 모두 없앤다. '깨달은 점 ' == '깨달은점'."""
    return re.sub(r"\s+", "", name or "")


def prop_text(props, wanted):
    """DB 행(page)의 프로퍼티에서 텍스트를 꺼낸다. 이름 뒤 공백 차이를 무시한다."""
    target = _norm(wanted)
    for name, val in (props or {}).items():
        if _norm(name) != target:
            continue
        t = val.get("type")
        if t in ("title", "rich_text"):
            return "".join(x.get("plain_text", "") for x in val.get(t, [])).strip()
        if t == "select":
            return ((val.get("select") or {}).get("name") or "").strip()
        if t == "url":
            return (val.get("url") or "").strip()
    return ""


# 본문에서 글을 뽑아올 블록 종류 (제목·구분선·이미지 등은 문장이 아니라 제외)
TEXT_BLOCKS = (
    "paragraph", "bulleted_list_item", "numbered_list_item",
    "quote", "callout", "toggle", "to_do",
)


def block_lines(token, block_id, depth=0, out=None):
    """페이지 본문 블록을 훑어 문장 후보(평문 줄)를 모은다. 하위 블록 1단계까지."""
    out = [] if out is None else out
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        data = api_get(token, f"/blocks/{block_id}/children", params)
        for b in data.get("results", []):
            btype = b.get("type")
            if btype in TEXT_BLOCKS:
                txt = "".join(x.get("plain_text", "") for x in b[btype].get("rich_text", []))
                if txt.strip():
                    out.append(txt.strip())
            # 토글/불릿 안에 들어있는 문장도 노션에 '있는' 문장이므로 1단계까지 따라간다
            if b.get("has_children") and depth < 1:
                block_lines(token, b["id"], depth + 1, out)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return out


# ── 4. '문장다운 문장'만 남기는 필터 ────────────────────────────
# 앞에 붙는 페이지 표시 제거: "153p ", "p.153 ", "12쪽 "
PAGE_MARK = re.compile(r"^\s*(?:p\.?\s*\d+|\d+\s*(?:p|쪽))[.\s:]*", re.IGNORECASE)
HANGUL = re.compile(r"[가-힣]")
URLISH = re.compile(r"https?://|www\.")
# 문장 끝맺음(어미·문장부호)  예: "…된다." "…없어" "…하자"
SENT_END = re.compile(r"(?:[.!?…\"'”’]|다|요|어|아|자|라|까|네|음|함|임|것|해|야|지)$")
# 조사 + 공백  예: "단독자가 ", "글쓰기는 "  → 단어 나열이 아니라 문장이라는 신호
PARTICLE = re.compile(r"(?:은|는|이|가|을|를|에|의|도|와|과|로|만|부터|까지|에서|처럼|보다)\s")
# "심리동사 : 좋다. 나쁘다." 처럼 '짧은 라벨 : 나열' 형태 (글귀가 아니라 정리 메모)
LABEL_LIST = re.compile(r"^[^:]{1,12}\s*:\s")


def clean_sentence(s):
    """앞뒤 군더더기를 털어낸다. **내용은 절대 바꾸지 않는다**(노션 원문 유지)."""
    s = s.replace("​", " ").strip()
    s = PAGE_MARK.sub("", s)                 # "153p 정확한 단어를…" → "정확한 단어를…"
    s = re.sub(r"\*\*|__", "", s)             # 굵게 표시 기호가 섞여 들어온 경우 제거
    s = re.sub(r"^[-•*•\s]+", "", s)    # 앞의 불릿 기호 제거
    s = re.sub(r"\s+", " ", s).strip()       # 연속 공백 1칸으로
    return s.strip(" ·-–—")


def is_good_sentence(s):
    """브리핑에 쓸 만한 '한 문장'인지 판단. 애매하면 버린다(품질 우선)."""
    if not (MIN_LEN <= len(s) <= MAX_LEN):
        return False                          # 너무 짧은 조각/너무 긴 문단 제외
    if not HANGUL.search(s):
        return False                          # 한글 없는 줄(URL·영문코드 등) 제외
    if URLISH.search(s):
        return False                          # 링크가 섞인 줄 제외
    # 쉼표/슬래시가 많으면 '단어 나열'(예: 유머 위트 해학 기지…) → 문장이 아님
    if s.count(",") + s.count("/") >= 4:
        return False
    # "첫째, 둘째," 같은 목록 뼈대만 있는 줄 제외
    if re.fullmatch(r"(첫째|둘째|셋째|넷째|다섯째|여섯째)[,.\s].{0,10}", s):
        return False
    # 체크리스트 질문("~없는가", "~있는가")은 글귀가 아니라 점검항목이라 제외
    if re.search(r"(없는가|있는가)[.?]?$", s):
        return False
    # "심리동사 : 좋다. 나쁘다." 같은 정리 메모 제외
    if LABEL_LIST.search(s):
        return False
    # 문장 끝맺음도 없고 조사도 없으면 '단어 나열'로 본다.
    #   예) "유머 위트 해학 기지 재치 익살 풍자 조크" → 글귀가 아님
    if not (SENT_END.search(s) or PARTICLE.search(s)):
        return False
    return True


def sentences_of(token, page, use_body=True):
    """책 1권(노션 페이지)에서 쓸 수 있는 문장 후보를 우선순위대로 모은다.

    1) '한 문장' 프로퍼티      ← 사용자가 직접 고른 문장이라 가장 정확
    2) '깨달은 점' 프로퍼티
    3) 페이지 본문 블록        ← 실제로 밑줄 친 문장들이 여기 다 들어있다
    """
    props = page.get("properties", {})
    cands = []
    for key, src in ((PROP_SENTENCE, "한 문장"), (PROP_INSIGHT, "깨달은 점")):
        v = clean_sentence(prop_text(props, key))
        if is_good_sentence(v):
            cands.append((v, src))
    if use_body:
        for line in block_lines(token, page["id"]):
            v = clean_sentence(line)
            if is_good_sentence(v):
                cands.append((v, "본문"))
    # 같은 페이지 안 중복 제거(순서 유지)
    seen, uniq = set(), []
    for v, src in cands:
        if v not in seen:
            seen.add(v)
            uniq.append((v, src))
    return uniq


# ── 5. 중복 방지 상태 파일 ─────────────────────────────────────
def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            st = json.load(f)
            if isinstance(st, dict):
                return st
    except Exception:
        pass
    return {"used": [], "round": 0}


def save_state(st):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    st["used"] = st.get("used", [])[-2000:]      # 무한정 커지지 않게 최근 것만 유지
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)                  # 쓰다 죽어도 파일이 깨지지 않게


def fingerprint(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ── 6. DB 전체 행 읽기 ────────────────────────────────────────
def fetch_rows(token, db_id):
    rows, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        data = api_post(token, f"/databases/{db_id}/query", payload)
        rows.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return rows


def row_title(page):
    return prop_text(page.get("properties", {}), PROP_TITLE) or "(제목 없음)"


# ── 7. 각 실행 모드 ───────────────────────────────────────────
def cmd_check(token, db_id):
    """노션 데이터가 얼마나 채워져 있는지 점검(왜 문장이 안 나오는지 진단용)."""
    rows = fetch_rows(token, db_id)
    n_sent = sum(1 for p in rows if is_good_sentence(clean_sentence(
        prop_text(p.get("properties", {}), PROP_SENTENCE))))
    n_ins = sum(1 for p in rows if is_good_sentence(clean_sentence(
        prop_text(p.get("properties", {}), PROP_INSIGHT))))
    print(f"📚 독서 리스트 총 {len(rows)}권")
    print(f"  · '한 문장' 프로퍼티가 채워진 책 : {n_sent}권")
    print(f"  · '깨달은 점' 프로퍼티가 채워진 책: {n_ins}권")
    print(f"  · 나머지는 본문 블록에서 문장을 찾아 씁니다(--list 로 확인).")
    return 0


def cmd_list(token, db_id, limit, book_filter):
    rows = fetch_rows(token, db_id)
    if book_filter:
        rows = [p for p in rows if book_filter in row_title(p)]
    shown = 0
    for p in rows:
        for text, src in sentences_of(token, p):
            print(f"[{src}] {row_title(p)} — {text}")
            shown += 1
            if shown >= limit:
                return 0
    if shown == 0:
        print("(뽑을 수 있는 문장이 하나도 없습니다)")
    return 0


def cmd_pick(token, db_id, book_filter, no_body):
    """브리핑용 한 문장 1건을 뽑는다. 못 뽑으면 지어내지 않고 실패(코드 2)."""
    rows = fetch_rows(token, db_id)
    if book_filter:
        rows = [p for p in rows if book_filter in row_title(p)]
        if not rows:
            die(f"'{book_filter}' 이라는 책을 독서 리스트에서 찾지 못했습니다.", 2)

    state = load_state()
    used = set(state.get("used", []))

    # 매번 다른 책부터 살펴보도록 섞는다(중복은 아래 fingerprint 로 한 번 더 막는다)
    random.shuffle(rows)

    fallback = None  # 이미 보낸 적 있는 문장(전부 소진됐을 때 쓰는 '노션 원문' 예비책)
    for page in rows:
        for text, src in sentences_of(token, page, use_body=not no_body):
            fp = fingerprint(text)
            item = (text, src, page)
            if fp in used:
                fallback = fallback or item
                continue
            return emit(item, fp, state)

    # 여기까지 왔다 = 새 문장이 없음. 한 바퀴 다 돌았으면 기록을 비우고 재사용.
    if fallback:
        state["used"] = []
        state["round"] = state.get("round", 0) + 1
        return emit(fallback, fingerprint(fallback[0]), state)

    # 진짜로 노션에 쓸 문장이 없다 → 여기서 멈춘다. 절대 만들어내지 않는다.
    print("NO_QUOTE", file=sys.stderr)
    print("❌ 노션 독서 리스트에서 쓸 수 있는 문장을 찾지 못했습니다. "
          "('한 문장' 칸을 채우거나 책 페이지 본문에 문장을 적어주세요)", file=sys.stderr)
    return 2


def emit(item, fp, state):
    """SOUL.md 브리핑 양식 그대로 출력 + 출처는 stderr(로그)로."""
    text, src, page = item
    title = row_title(page)
    author = prop_text(page.get("properties", {}), PROP_AUTHOR)

    print('"좋은 글 한문장"')
    print(text)
    print(f"{title}" + (f" {author}" if author else ""))

    print(f"[출처] {src} / {page.get('url', '')}", file=sys.stderr)

    state.setdefault("used", []).append(fp)
    save_state(state)
    return 0


def main():
    ap = argparse.ArgumentParser(description="노션 독서 리스트에서 실제 문장만 가져온다")
    ap.add_argument("--check", action="store_true", help="노션 데이터 채움 상태 점검")
    ap.add_argument("--list", type=int, nargs="?", const=20, metavar="N",
                    help="뽑을 수 있는 문장 N개 미리보기 (기본 20)")
    ap.add_argument("--book", metavar="제목일부", help="특정 책에서만 뽑기")
    ap.add_argument("--no-body", action="store_true",
                    help="본문 블록은 쓰지 않고 '한 문장'/'깨달은 점' 칸만 사용")
    ap.add_argument("--reset", action="store_true", help="중복방지 기록 초기화")
    args = ap.parse_args()

    if args.reset:
        save_state({"used": [], "round": 0})
        print("✅ 중복방지 기록을 비웠습니다.")
        return 0

    load_env()
    token = os.getenv("NOTION_TOKEN")
    if not token:
        die("NOTION_TOKEN 이 없습니다. ~/.openclaw/.env 에 넣어주세요.")
    db_id = (os.getenv("NOTION_READING_DB") or DEFAULT_DB_ID).replace("-", "")

    if args.check:
        return cmd_check(token, db_id)
    if args.list is not None:
        return cmd_list(token, db_id, args.list, args.book)
    return cmd_pick(token, db_id, args.book, args.no_body)


if __name__ == "__main__":
    sys.exit(main())
