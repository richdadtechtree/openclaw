#!/usr/bin/env python3
"""
get_notion_book.py — 노션 '독서 리스트'에서 **실제로 적혀 있는 글귀만** 하나 뽑아온다.

핵심 원칙 (이 스크립트가 존재하는 이유)
---------------------------------------
책읽남(bookman)이 "노션에 없는 글귀"를 지어내는 사고를 막기 위한 스크립트다.
**지어내는 경로가 코드에 하나도 없다**:
  - 노션에서 읽어온 글자만 출력한다.
  - 쓸 만한 문장을 못 찾으면 기본 문구를 만들지 않고 **종료코드 2로 실패**한다.
  - 출처(책 제목 · 페이지 URL · 몇 쪽)를 stderr 로 남겨 사람이 바로 대조할 수 있다.

글귀를 어디서 찾나 (형준님 노션 구조에 맞춤)
-------------------------------------------
노션 책 페이지는 보통 이렇게 생겼다.

    22p                                    ← 쪽수만 있는 줄
    왜를 아는 것이 가장 심오하고 …          ← 주황색으로 칠한 '진짜 글귀'
    인간의 책임감을 자극하는 표현으로 …      ← 색 없는 일반 메모

그래서 아래 순서로 점수를 매겨 **색칠·인용한 문장을 최우선**으로 고른다.

  1순위(강조) : 글자에 **색/형광펜**이 칠해졌거나 인용(>)·콜아웃 블록
  2순위(굵게) : **굵게/밑줄** 표시된 문장
  3순위(본문) : 그 외 일반 본문 문장
  ※ `한 문장` / `깨달은 점` 프로퍼티가 채워져 있으면 그게 0순위(직접 고른 문장)

사용법
------
  python3 ~/.openclaw/scripts/get_notion_book.py              # 브리핑용 한 문장
  python3 ~/.openclaw/scripts/get_notion_book.py --check      # 데이터/캐시 상태 점검
  python3 ~/.openclaw/scripts/get_notion_book.py --list 20    # 뽑히는 문장 미리보기
  python3 ~/.openclaw/scripts/get_notion_book.py --book 퓨처셀프  # 특정 책에서만
  python3 ~/.openclaw/scripts/get_notion_book.py --build-cache   # 전체 미리 읽어두기(1회)
  python3 ~/.openclaw/scripts/get_notion_book.py --reset      # 중복방지 기록 초기화

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

# 문장으로 인정할 최소/최대 길이 (짧은 조각·긴 문단 덩어리를 걸러낸다)
MIN_LEN = 10
MAX_LEN = 260

# 한 번 실행할 때 노션에서 새로 읽어볼 책 권수 상한.
# (캐시에 없는 책만 해당. 너무 많이 읽으면 슬랙 응답이 느려져서 제한한다)
MAX_FETCH_PER_RUN = 8

# 노션 프로퍼티 이름
# ⚠️ 실제 이름이 "깨달은 점 "처럼 **뒤에 공백**이 붙어 있어서,
#    prop_text() 는 공백을 지우고 비교한다(이게 없으면 항상 빈값이 나온다).
PROP_TITLE = "책 제목"
PROP_AUTHOR = "저자"
PROP_SENTENCE = "한 문장"
PROP_INSIGHT = "깨달은 점"

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ~/.openclaw
STATE_PATH = os.path.join(_BASE, "workspace", "bookman", "book_sequence_state.json")
CACHE_PATH = os.path.join(_BASE, "workspace", "bookman", "book_cache.json")
CACHE_VERSION = 2

# 문장 등급(낮을수록 좋은 글귀)
TIER_PROP = 0      # '한 문장' / '깨달은 점' 프로퍼티 = 직접 고른 문장
TIER_EMPH = 1      # 색/형광펜/인용블록 = 읽으면서 칠해둔 진짜 글귀
TIER_BOLD = 2      # 굵게/밑줄
TIER_PLAIN = 3     # 일반 본문
TIER_NAME = {0: "직접입력", 1: "강조", 2: "굵게", 3: "본문"}


# ── 1. .env 읽기 ──────────────────────────────────────────────
def load_env():
    """python-dotenv 없이 openclaw 루트의 .env 를 읽어 환경변수로 올린다."""
    for path in (os.path.join(_BASE, ".env"), ".env"):
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


def die(msg, code=3):
    """설정/통신 오류는 조용히 넘기지 않는다(=agent 가 대신 지어내지 못하게)."""
    print(f"❌ [get_notion_book] {msg}", file=sys.stderr)
    sys.exit(code)


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


# ── 3. 프로퍼티 읽기 ───────────────────────────────────────────
def _norm(name):
    """프로퍼티 이름 비교용: 공백을 모두 없앤다. '깨달은 점 ' == '깨달은점'."""
    return re.sub(r"\s+", "", name or "")


def prop_text(props, wanted):
    """DB 행(page)의 프로퍼티에서 텍스트를 꺼낸다. 이름의 공백 차이를 무시한다."""
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


# ── 4. 본문 블록에서 문장 + '강조 여부' 뽑기 ────────────────────
# 글을 뽑아올 블록 종류 (구분선·이미지·표 등은 문장이 아니라 제외)
TEXT_BLOCKS = (
    "paragraph", "bulleted_list_item", "numbered_list_item",
    "quote", "callout", "toggle", "to_do",
    "heading_1", "heading_2", "heading_3",
)
# 그 자체로 '인용'인 블록 → 무조건 강조 취급
QUOTE_BLOCKS = ("quote", "callout")

# "22p" 처럼 쪽수만 있는 줄 (글귀가 아니라 '다음 문장의 쪽수 표시')
PAGE_ONLY = re.compile(r"^\s*(?:p\.?\s*\d{1,4}|\d{1,4}\s*(?:p|쪽|페이지))\s*[.:]?\s*$",
                       re.IGNORECASE)


def rich_info(rich):
    """rich_text 배열 → (평문, 색칠비율, 굵게비율).

    노션은 글자마다 annotations(color/bold/underline)를 준다.
    형준님이 **주황색으로 칠해둔 문장**을 골라내기 위해 이 비율을 쓴다.
    """
    text = "".join(x.get("plain_text", "") for x in rich or [])
    total = len(text.strip()) or 1
    colored = bold = 0
    for x in rich or []:
        t = x.get("plain_text", "")
        a = x.get("annotations") or {}
        if a.get("color", "default") != "default":   # 글자색 + 형광펜(_background) 둘 다 포함
            colored += len(t)
        if a.get("bold") or a.get("underline"):
            bold += len(t)
    return text, colored / total, bold / total


def page_blocks(token, block_id, depth=0, out=None):
    """페이지 본문을 훑어 (원문, 등급, 직전 쪽수) 목록을 만든다. 하위 1단계까지."""
    out = [] if out is None else out
    cursor = None
    last_page_mark = ""     # 바로 위에 나온 "22p" 를 기억해 출처 표시에 쓴다
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        data = api_get(token, f"/blocks/{block_id}/children", params)
        for b in data.get("results", []):
            btype = b.get("type")
            if btype in TEXT_BLOCKS:
                raw, c_ratio, b_ratio = rich_info(b[btype].get("rich_text", []))
                stripped = raw.strip()
                if PAGE_ONLY.match(stripped):
                    last_page_mark = stripped        # 쪽수 줄은 글귀가 아니라 표시로만 쓴다
                elif stripped:
                    if btype in QUOTE_BLOCKS or c_ratio >= 0.5:
                        tier = TIER_EMPH
                    elif b_ratio >= 0.5:
                        tier = TIER_BOLD
                    else:
                        tier = TIER_PLAIN
                    out.append((stripped, tier, last_page_mark))
            # 토글/불릿 안쪽 문장도 '노션에 있는' 문장이므로 1단계까지 따라간다
            if b.get("has_children") and depth < 1:
                page_blocks(token, b["id"], depth + 1, out)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return out


# ── 5. '글귀다운 문장'만 남기는 필터 ────────────────────────────
# 문장 앞에 붙은 쪽수 제거: "153p 정확한…" → "정확한…"
PAGE_MARK = re.compile(r"^\s*(?:p\.?\s*\d{1,4}|\d{1,4}\s*(?:p|쪽|페이지))[.\s:]+", re.IGNORECASE)
HANGUL = re.compile(r"[가-힣]")
URLISH = re.compile(r"https?://|www\.")
# 문장 끝맺음(어미·문장부호)  예: "…된다." "…없어" "…살아라!"
SENT_END = re.compile(r"(?:[.!?…\"'”’]|다|요|어|아|자|라|까|네|음|함|임|것|해|야|지)$")
# 조사 + 공백  예: "단독자가 ", "글쓰기는 " → 단어 나열이 아니라 문장이라는 신호
PARTICLE = re.compile(r"(?:은|는|이|가|을|를|에|의|도|와|과|로|만|부터|까지|에서|처럼|보다)\s")
# "심리동사 : 좋다. 나쁘다." 처럼 '짧은 라벨 : 나열' (글귀가 아니라 정리 메모)
LABEL_LIST = re.compile(r"^[^:]{1,12}\s*:\s")


def clean_sentence(s):
    """앞뒤 군더더기만 턴다. **내용은 절대 바꾸지 않는다**(노션 원문 유지)."""
    s = (s or "").replace("​", " ").strip()
    s = PAGE_MARK.sub("", s)                  # "22p 왜를 아는 것이…" → "왜를 아는 것이…"
    s = re.sub(r"\*\*|__", "", s)              # 굵게 기호가 섞여 들어온 경우 제거
    s = re.sub(r"^[-•*·\s]+", "", s)           # 앞의 불릿 기호 제거
    s = re.sub(r"\s+", " ", s).strip()         # 연속 공백 1칸으로
    return s.strip(" ·-–—")                    # ※ 마침표는 원문이므로 남긴다


def is_good_sentence(s, tier=TIER_PLAIN):
    """브리핑에 쓸 만한 '한 문장'인지 판단. 애매하면 버린다(품질 우선).

    단, 형준님이 직접 칠하거나 입력한 문장(0·1순위)은 이미 '고른 문장'이므로
    단어 나열 검사 같은 까다로운 규칙은 건너뛴다.
    """
    picked = tier <= TIER_EMPH                 # 사람이 직접 고른 문장인가

    if not (MIN_LEN <= len(s) <= MAX_LEN):
        return False                           # 너무 짧은 조각/너무 긴 덩어리 제외
    if not HANGUL.search(s):
        return False                           # 한글 없는 줄(URL·영문코드 등) 제외
    if URLISH.search(s):
        return False                           # 링크가 섞인 줄 제외
    if picked:
        return True                            # 여기까지 왔으면 채택

    # ↓ 아래는 '색칠 안 된 일반 본문'에만 적용하는 까다로운 규칙
    if s.count(",") + s.count("/") >= 4:
        return False                           # 단어 나열(예: 보전과 보존, 부분과 부문 …)
    if re.fullmatch(r"(첫째|둘째|셋째|넷째|다섯째|여섯째)[,.\s].{0,10}", s):
        return False                           # 목록 뼈대만 있는 줄
    if re.search(r"(없는가|있는가)[.?]?$", s):
        return False                           # 퇴고 체크리스트 항목
    if LABEL_LIST.search(s):
        return False                           # "심리동사 : 좋다. 나쁘다."
    if not (SENT_END.search(s) or PARTICLE.search(s)):
        return False                           # 끝맺음도 조사도 없으면 단어 나열
    return True


def extract_sentences(token, page):
    """책 1권(노션 페이지)에서 쓸 수 있는 문장 후보를 등급과 함께 모은다."""
    props = page.get("properties", {})
    cands = []

    # 0순위: 직접 입력한 프로퍼티
    for key in (PROP_SENTENCE, PROP_INSIGHT):
        v = clean_sentence(prop_text(props, key))
        if is_good_sentence(v, TIER_PROP):
            cands.append({"t": v, "tier": TIER_PROP, "p": key})

    # 1~3순위: 본문 블록 (색칠 > 굵게 > 일반)
    for raw, tier, page_mark in page_blocks(token, page["id"]):
        v = clean_sentence(raw)
        if is_good_sentence(v, tier):
            cands.append({"t": v, "tier": tier, "p": page_mark})

    # 같은 페이지 안 중복 제거(등급 좋은 것 우선 유지)
    best = {}
    for c in cands:
        old = best.get(c["t"])
        if old is None or c["tier"] < old["tier"]:
            best[c["t"]] = c
    return sorted(best.values(), key=lambda c: c["tier"])


# ── 6. 캐시 & 중복방지 상태 ────────────────────────────────────
def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
            return v if isinstance(v, dict) else default
    except Exception:
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)          # 쓰다가 죽어도 파일이 깨지지 않게 원자적 교체


def load_cache():
    c = _load_json(CACHE_PATH, {})
    if c.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "pages": {}}
    c.setdefault("pages", {})
    return c


def load_state():
    st = _load_json(STATE_PATH, {})
    st.setdefault("used", [])
    st.setdefault("round", 0)
    return st


def save_state(st):
    st["used"] = st.get("used", [])[-3000:]   # 무한정 커지지 않게 최근 것만
    _save_json(STATE_PATH, st)


def fingerprint(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def sentences_for(token, page, cache, allow_fetch=True):
    """캐시 우선. 책이 수정됐거나(last_edited 변경) 처음 보는 책이면 노션에서 읽는다."""
    pid = page["id"]
    edited = page.get("last_edited_time", "")
    hit = cache["pages"].get(pid)
    if hit and hit.get("edited") == edited:
        return hit["sentences"], False          # 캐시 적중 → API 호출 없음
    if not allow_fetch:
        return (hit or {}).get("sentences", []), False
    sents = extract_sentences(token, page)
    cache["pages"][pid] = {
        "title": row_title(page),
        "author": prop_text(page.get("properties", {}), PROP_AUTHOR),
        "url": page.get("url", ""),
        "edited": edited,
        "sentences": sents,
    }
    return sents, True                          # True = 이번에 새로 읽었음


# ── 7. DB 전체 행 읽기 ────────────────────────────────────────
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


def filter_rows(rows, keyword):
    if not keyword:
        return rows
    return [p for p in rows if keyword.lower() in row_title(p).lower()]


# ── 8. 실행 모드 ──────────────────────────────────────────────
def cmd_check(token, db_id):
    """왜 문장이 안 나오는지 진단용. 노션 데이터 + 캐시 상태를 보여준다."""
    rows = fetch_rows(token, db_id)
    cache = load_cache()
    n_prop = sum(1 for p in rows if prop_text(p.get("properties", {}), PROP_SENTENCE).strip()
                 or prop_text(p.get("properties", {}), PROP_INSIGHT).strip())
    cached = [c for pid, c in cache["pages"].items()]
    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for c in cached:
        for s in c.get("sentences", []):
            tier_counts[s.get("tier", 3)] = tier_counts.get(s.get("tier", 3), 0) + 1
    total_sent = sum(tier_counts.values())

    print(f"📚 독서 리스트 총 {len(rows)}권")
    print(f"  · '한 문장'/'깨달은 점' 칸이 채워진 책 : {n_prop}권")
    print(f"  · 본문까지 읽어둔 책(캐시)            : {len(cached)}권 / {len(rows)}권")
    print(f"  · 캐시에 모인 문장                    : {total_sent}개")
    print(f"      직접입력 {tier_counts[0]} · 강조(색칠) {tier_counts[1]} · "
          f"굵게 {tier_counts[2]} · 본문 {tier_counts[3]}")
    if len(cached) < len(rows):
        print("  💡 전부 미리 읽어두려면: get_notion_book.py --build-cache")
    print(f"  · 이미 보낸 문장 기록: {len(load_state()['used'])}개")
    return 0


def cmd_build_cache(token, db_id, keyword):
    """전체 책을 한 번 훑어 캐시에 담는다(느리지만 1회성). 이후 실행이 빨라진다."""
    rows = filter_rows(fetch_rows(token, db_id), keyword)
    cache = load_cache()
    fetched = 0
    for i, page in enumerate(rows, 1):
        sents, did = sentences_for(token, page, cache, allow_fetch=True)
        fetched += int(did)
        mark = "읽음" if did else "캐시"
        print(f"[{i}/{len(rows)}] {mark} · {row_title(page)} → 문장 {len(sents)}개")
        if did and fetched % 10 == 0:
            _save_json(CACHE_PATH, cache)       # 중간중간 저장(중단돼도 진행분 보존)
    _save_json(CACHE_PATH, cache)
    print(f"\n✅ 완료. 새로 읽은 책 {fetched}권 / 전체 {len(rows)}권")
    return 0


def cmd_list(token, db_id, limit, keyword):
    """뽑히는 문장을 눈으로 확인. 캐시에 있으면 API 호출 없이 바로 보여준다."""
    rows = filter_rows(fetch_rows(token, db_id), keyword)
    cache = load_cache()
    shown, fetched = 0, 0
    for page in rows:
        allow = fetched < MAX_FETCH_PER_RUN or bool(keyword)
        sents, did = sentences_for(token, page, cache, allow_fetch=allow)
        fetched += int(did)
        for s in sents:
            where = f" {s['p']}" if s.get("p") and s["p"] not in (PROP_SENTENCE, PROP_INSIGHT) else ""
            print(f"[{TIER_NAME.get(s['tier'], '?')}{where}] {row_title(page)} — {s['t']}")
            shown += 1
            if shown >= limit:
                _save_json(CACHE_PATH, cache)
                return 0
    _save_json(CACHE_PATH, cache)
    if shown == 0:
        print("(뽑을 수 있는 문장이 하나도 없습니다. --build-cache 로 본문을 읽어보세요)")
    return 0


def cmd_pick(token, db_id, keyword):
    """브리핑용 한 문장 1건. 못 뽑으면 지어내지 않고 실패(코드 2)."""
    rows = filter_rows(fetch_rows(token, db_id), keyword)
    if not rows:
        die(f"'{keyword}' 이라는 책을 독서 리스트에서 찾지 못했습니다.", 2)

    cache = load_cache()
    state = load_state()
    used = set(state["used"])

    random.shuffle(rows)                        # 매번 다른 책부터 살펴본다

    best = None        # 지금까지 본 것 중 가장 등급이 좋은 후보
    seen_used = None   # 이미 보낸 적 있는 문장(전부 소진됐을 때 쓸 예비책)
    fetched = 0

    for page in rows:
        allow = fetched < MAX_FETCH_PER_RUN or bool(keyword)
        sents, did = sentences_for(token, page, cache, allow_fetch=allow)
        fetched += int(did)
        if not sents:
            continue

        fresh = [s for s in sents if fingerprint(s["t"]) not in used]
        if not fresh:
            seen_used = seen_used or (sents[0], page)
            continue

        top = fresh[0]                          # sentences_for 결과는 등급순 정렬돼 있다
        if top["tier"] <= TIER_EMPH:            # 직접 입력 or 색칠한 문장 → 즉시 채택
            _save_json(CACHE_PATH, cache)
            return emit(top, page, state)
        if best is None or top["tier"] < best[0]["tier"]:
            best = (top, page)
        if fetched >= MAX_FETCH_PER_RUN and best:
            break                               # 충분히 봤으면 그만 (응답 속도 확보)

    _save_json(CACHE_PATH, cache)

    if best:
        return emit(best[0], best[1], state)

    if seen_used:                               # 한 바퀴 다 돌았으면 기록 비우고 재순환
        state["used"] = []
        state["round"] += 1
        return emit(seen_used[0], seen_used[1], state)

    # 진짜로 노션에 쓸 문장이 없다 → 여기서 멈춘다. 절대 만들어내지 않는다.
    print("NO_QUOTE", file=sys.stderr)
    print("❌ 노션 독서 리스트에서 쓸 수 있는 문장을 찾지 못했습니다. "
          "('한 문장' 칸을 채우거나 책 페이지 본문에 문장을 적어주세요)", file=sys.stderr)
    return 2


def emit(sent, page, state):
    """SOUL.md 브리핑 양식 그대로 출력. 출처는 stderr(로그)로 따로 남긴다."""
    title = row_title(page)
    author = prop_text(page.get("properties", {}), PROP_AUTHOR)

    print('"좋은 글 한문장"')
    print(sent["t"])
    print(title + (f" {author}" if author else ""))

    where = f" {sent['p']}" if sent.get("p") else ""
    print(f"[출처] {TIER_NAME.get(sent['tier'], '?')}{where} / {page.get('url', '')}",
          file=sys.stderr)

    state["used"].append(fingerprint(sent["t"]))
    save_state(state)
    return 0


def main():
    ap = argparse.ArgumentParser(description="노션 독서 리스트에서 실제 글귀만 가져온다")
    ap.add_argument("--check", action="store_true", help="노션 데이터/캐시 상태 점검")
    ap.add_argument("--list", type=int, nargs="?", const=20, metavar="N",
                    help="뽑히는 문장 N개 미리보기 (기본 20)")
    ap.add_argument("--build-cache", action="store_true",
                    help="전체 책 본문을 한 번 읽어 캐시에 담는다(1회, 느림)")
    ap.add_argument("--book", metavar="제목일부", help="특정 책에서만 뽑기")
    ap.add_argument("--reset", action="store_true", help="중복방지 기록 초기화")
    ap.add_argument("--clear-cache", action="store_true", help="본문 캐시 삭제(다시 읽게)")
    args = ap.parse_args()

    if args.reset:
        save_state({"used": [], "round": 0})
        print("✅ 중복방지 기록을 비웠습니다.")
        return 0
    if args.clear_cache:
        _save_json(CACHE_PATH, {"version": CACHE_VERSION, "pages": {}})
        print("✅ 본문 캐시를 비웠습니다.")
        return 0

    load_env()
    token = os.getenv("NOTION_TOKEN")
    if not token:
        die("NOTION_TOKEN 이 없습니다. ~/.openclaw/.env 에 넣어주세요.")
    db_id = (os.getenv("NOTION_READING_DB") or DEFAULT_DB_ID).replace("-", "")

    if args.check:
        return cmd_check(token, db_id)
    if args.build_cache:
        return cmd_build_cache(token, db_id, args.book)
    if args.list is not None:
        return cmd_list(token, db_id, args.list, args.book)
    return cmd_pick(token, db_id, args.book)


if __name__ == "__main__":
    sys.exit(main())
