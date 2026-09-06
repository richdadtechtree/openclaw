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
  4순위(후순위): 모양이 어설픈 본문(단어 나열, 너무 짧거나 긴 줄 등)
  ※ `한 문장` / `깨달은 점` 프로퍼티가 채워져 있으면 그게 0순위(직접 고른 문장)
  ※ 노션 **`책읽남` 열이 `제외`** 인 책은 아예 후보에서 뺀다(어록 모음·추천 목록 등)

  **웬만하면 버리지 않는다.** 애매한 줄은 버리는 대신 4순위로 미뤄, 다른 후보가
  없을 때 쓰인다. 빈손으로 "못 찾았습니다" 하는 것보다 노션에 실제로 적힌
  본문 한 줄을 가져오는 게 낫기 때문이다.

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

# 길이 기준을 두 겹으로 둔다.
#   HARD_* 를 벗어나면 진짜로 못 쓰는 줄 → 버린다.
#   GOOD_* 안에 들면 보기 좋은 길이 → 그대로. 벗어나면 버리지 않고 '뒤로 미룬다'.
HARD_MIN, HARD_MAX = 6, 600      # 이 범위 밖만 버림
GOOD_MIN, GOOD_MAX = 10, 300     # 이 범위 밖은 후순위로만
# 엔터 2번으로 묶을 때 한 덩어리가 커질 수 있는 최대 길이
# (불릿 수십 개가 통째로 한 덩어리가 되는 것을 막는다)
GROUP_MAX = 300

# 한 번 실행할 때 노션에서 새로 읽어볼 책 권수 상한.
# (캐시에 없는 책만 해당. 너무 많이 읽으면 슬랙 응답이 느려져서 제한한다)
# 단, 아무것도 못 찾은 '빈손' 상황에서는 아래 배수만큼 더 읽어본다.
DESPERATE_MULTIPLIER = 3

# --list 미리보기에서 한 책이 목록을 독차지하지 않도록 책당 출력 상한
LIST_PER_BOOK = 5

# 책 제목을 감쌀 기호. 브리핑 3번째 줄이 "<책 제목> 저자" 로 나간다.
# 슬랙이 꺾쇠를 링크 문법으로 오해해 삼키면 ("『", "』") 같은 걸로 바꾸면 된다.
TITLE_WRAP = ("<", ">")
MAX_FETCH_PER_RUN = 10

# 노션 프로퍼티 이름
# ⚠️ 실제 이름이 "깨달은 점 "처럼 **뒤에 공백**이 붙어 있어서,
#    prop_text() 는 공백을 지우고 비교한다(이게 없으면 항상 빈값이 나온다).
PROP_TITLE = "책 제목"
PROP_AUTHOR = "저자"
PROP_SENTENCE = "한 문장"
PROP_INSIGHT = "깨달은 점"
# 노션 '책읽남' 열에서 이 값이 선택된 책은 아예 쓰지 않는다.
# (어록 모음, 추천 목록처럼 글귀를 뽑기 부적절한 행을 사용자가 직접 빼둘 수 있게)
PROP_EXCLUDE = "책읽남"
EXCLUDE_VALUES = ("제외",)

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # ~/.openclaw
STATE_PATH = os.path.join(_BASE, "workspace", "bookman", "book_sequence_state.json")
CACHE_PATH = os.path.join(_BASE, "workspace", "bookman", "book_cache.json")
CACHE_VERSION = 5

# 문장 등급(낮을수록 좋은 글귀)
TIER_PROP = 0      # '한 문장' / '깨달은 점' 프로퍼티 = 직접 고른 문장
TIER_EMPH = 1      # 색/형광펜/인용블록 = 읽으면서 칠해둔 진짜 글귀
TIER_BOLD = 2      # 굵게/밑줄
TIER_PLAIN = 3     # 일반 본문
TIER_WEAK = 4      # 모양이 좀 어설픈 본문 (버리지 않고 '맨 뒤'로 미뤄둔다)
TIER_NAME = {0: "직접입력", 1: "강조", 2: "굵게", 3: "본문", 4: "본문(후순위)"}

# 등급별 '뽑힐 가중치'. 3시간마다 보내므로 골고루 나오는 게 가장 중요하다.
# 색칠한 글귀를 제일 자주 보내되, 나머지도 섞여 나오게 확률로 뽑는다.
# 숫자를 키우면 그 등급이 더 자주 나온다. (한 책 안에서 대략 8:8:3:2:0.3 비율)
TIER_WEIGHT = {0: 8.0, 1: 8.0, 2: 3.0, 3: 2.0, 4: 0.15}

# 한 번 뽑을 때 후보를 모을 책 수. 클수록 여러 책이 골고루 섞인다.
BOOKS_PER_PICK = 5


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
# 소제목 블록 → 글귀가 아니라 '목차'인 경우가 많다.
# (예: "지켜야 할 주의 사항", "압구정에서 시작되는 흐름")
# 버리지는 않고 후순위로 내린다. 단, 색칠돼 있으면 사람이 고른 것이므로 예외.
HEADING_BLOCKS = ("heading_1", "heading_2", "heading_3")

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


def collect_blocks(token, block_id, depth=0, out=None):
    """페이지 본문 블록을 **원래 순서 그대로** 평평하게 모은다(묶는 건 다음 단계).

    빈 블록(= 엔터를 두 번 쳐서 생긴 빈 줄)도 그대로 담는다.
    아래 group_blocks() 가 그 빈 줄을 '덩어리 경계'로 쓰기 때문이다.
    """
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
                raw, c_ratio, b_ratio = rich_info(b[btype].get("rich_text", []))
                out.append({"text": raw.strip(), "type": btype,
                            "c": c_ratio, "b": b_ratio})
            # 토글/불릿 안쪽 문장도 '노션에 있는' 문장이므로 1단계까지 따라간다
            if b.get("has_children") and depth < 1:
                collect_blocks(token, b["id"], depth + 1, out)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return out


def group_blocks(items):
    """**엔터 2번(빈 줄)** 을 경계로 블록들을 하나의 글귀 덩어리로 묶는다.

    노션에서 엔터 한 번은 '줄 바꿈'이라 같은 글귀가 여러 블록으로 쪼개져 있을 수 있다.
    그대로 두면 문장이 반 토막 나서 나가므로, 빈 줄이 나올 때까지 이어 붙인다.

    덩어리를 끊는 경우:
      1) 빈 블록(엔터 2번)          ← 기본 경계
      2) 앞 줄이 . ! ? 로 끝났을 때  ← 이미 끝난 문장에 다음 줄을 붙이지 않는다
      3) "22p" 같은 쪽수만 있는 줄   ← 다음 덩어리의 출처 표시로 넘긴다
      4) 소제목 블록                ← 목차는 항상 혼자
      5) 블록 종류가 바뀔 때         ← 문단 ↔ 불릿 ↔ 번호목록
      6) 색칠 여부가 바뀔 때         ← 칠한 글귀에 옆 메모가 섞이지 않게
      7) 너무 길어질 때(GROUP_MAX)   ← 덩어리가 무한정 커지는 것 방지

    즉 **"문장이 안 끝난 채 줄만 바뀐 경우"에만 이어 붙인다.**
    불릿마다 온전한 문장이 적혀 있으면 각각 따로 남는다.

    반환: [(합쳐진 원문, 등급, 쪽수표시), ...]
    """
    groups = []
    cur = []              # 지금 모으는 중인 덩어리
    page_mark = ""        # 바로 위에 나온 "22p"

    def flush():
        """모아둔 블록들을 한 덩어리로 확정한다."""
        nonlocal cur
        if not cur:
            return
        text = " ".join(x["text"] for x in cur)
        # 등급은 덩어리 '전체' 기준으로 다시 계산한다(글자 수로 가중평균)
        total = sum(len(x["text"]) for x in cur) or 1
        c = sum(x["c"] * len(x["text"]) for x in cur) / total
        bd = sum(x["b"] * len(x["text"]) for x in cur) / total
        btype = cur[0]["type"]
        if btype in QUOTE_BLOCKS or c >= 0.5:
            tier = TIER_EMPH        # 색칠·인용 = 사람이 고른 글귀
        elif btype in HEADING_BLOCKS:
            tier = TIER_WEAK        # 소제목 = 목차. 후순위로만
        elif bd >= 0.5:
            tier = TIER_BOLD
        else:
            tier = TIER_PLAIN
        groups.append((text, tier, page_mark))
        cur = []

    for it in items:
        t = it["text"]
        if not t:                              # (1) 빈 줄 = 엔터 2번
            flush()
            continue
        if PAGE_ONLY.match(t):                 # (2) 쪽수 줄
            flush()
            page_mark = t
            continue
        if cur:
            prev = cur[-1]
            finished = bool(TERMINAL.search(prev["text"]))      # (2) 앞 줄이 끝난 문장인가
            changed_type = it["type"] != prev["type"]           # (5)
            changed_emph = (it["c"] >= 0.5) != (prev["c"] >= 0.5)   # (6)
            cur_len = sum(len(x["text"]) for x in cur)
            too_long = cur_len + len(t) + 1 > GROUP_MAX         # (7)
            if finished or changed_type or changed_emph or too_long:
                flush()
        cur.append(it)
        if it["type"] in HEADING_BLOCKS:       # (3) 소제목은 항상 혼자
            flush()
    flush()
    return groups


def page_blocks(token, block_id):
    """페이지 본문 → (덩어리 원문, 등급, 쪽수표시) 목록."""
    return group_blocks(collect_blocks(token, block_id))


# ── 5. 문장 등급 매기기 (버리기보다 '뒤로 미루기') ──────────────
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
# 문장이 제대로 끝났는지 (마침표/느낌표/물음표. 뒤에 닫는 따옴표가 붙어도 인정)
TERMINAL = re.compile(r"[.!?…][\"\'”’」』)\]]*$")
# 소제목처럼 보이는 길이 기준: 이보다 짧고 끝맺음 부호가 없으면 목차일 확률이 높다
HEADINGISH_LEN = 40


def clean_sentence(s):
    """앞뒤 군더더기만 턴다. **내용은 절대 바꾸지 않는다**(노션 원문 유지)."""
    s = (s or "").replace("​", " ").strip()
    s = PAGE_MARK.sub("", s)                  # "22p 왜를 아는 것이…" → "왜를 아는 것이…"
    s = re.sub(r"\*\*|__", "", s)              # 굵게 기호가 섞여 들어온 경우 제거
    s = re.sub(r"^[-•*·\s]+", "", s)           # 앞의 불릿 기호 제거
    s = re.sub(r"\s+", " ", s).strip()         # 연속 공백 1칸으로
    return s.strip(" ·-–—")                    # ※ 마침표는 원문이므로 남긴다


def score_sentence(s, tier=TIER_PLAIN):
    """문장의 최종 등급을 매긴다. 못 쓰는 줄이면 None.

    설계 원칙: **웬만하면 버리지 않는다.**
    빈손으로 "못 찾았습니다" 하는 것보다, 조금 어설퍼도 노션에 실제로 적힌
    본문 한 줄을 가져오는 게 낫다. 그래서 애매한 줄은 **버리는 대신
    후순위(TIER_WEAK)로 미뤄** 다른 후보가 없을 때만 쓰이게 한다.

    진짜로 버리는 것은 넷뿐:
      길이가 말도 안 됨 / 한글 없음 / 링크 줄 / 쪽수만 있는 줄
    """
    if not s:
        return None
    if not (HARD_MIN <= len(s) <= HARD_MAX):
        return None                            # 6자 미만·600자 초과는 문장이 아님
    if not HANGUL.search(s):
        return None                            # 한글 없는 줄(영문코드·숫자 등)
    if URLISH.search(s):
        return None                            # 링크 줄
    if PAGE_ONLY.match(s):
        return None                            # "22p" 처럼 쪽수만 있는 줄

    if tier <= TIER_EMPH:
        return tier                            # 직접 입력·색칠한 문장은 그대로 최우선

    # ↓ 아래 조건에 걸리면 '버리지 않고' 후순위로만 미룬다
    weak = False
    if not (GOOD_MIN <= len(s) <= GOOD_MAX):
        weak = True                            # 너무 짧거나 너무 긴 줄
    if s.count(",") + s.count("/") >= 4:
        weak = True                            # 단어 나열(예: 보전과 보존, 부분과 부문 …)
    if re.fullmatch(r"(첫째|둘째|셋째|넷째|다섯째|여섯째)[,.\s].{0,10}", s):
        weak = True                            # 목록 뼈대만 있는 줄
    if re.search(r"(없는가|있는가)[.?]?$", s):
        weak = True                            # 퇴고 체크리스트 항목
    if LABEL_LIST.search(s):
        weak = True                            # "심리동사 : 좋다. 나쁘다."
    if not (SENT_END.search(s) or PARTICLE.search(s)):
        weak = True                            # 끝맺음도 조사도 없으면 단어 나열 같음
    if tier == TIER_PLAIN and len(s) < HEADINGISH_LEN and not TERMINAL.search(s):
        # 마침표 없이 짧게 끝나는 줄은 대개 소제목이다.
        #   예) "지켜야 할 주의 사항", "압구정에서 시작되는 흐름",
        #       "100날 투자 공부해도 부자가 될 수 없는 이유"
        # 색칠·굵게 표시된 줄은 사람이 고른 것이므로 이 규칙을 적용하지 않는다.
        weak = True
    return TIER_WEAK if weak else tier


def extract_sentences(token, page):
    """책 1권(노션 페이지)에서 쓸 수 있는 문장 후보를 등급과 함께 모은다."""
    props = page.get("properties", {})
    cands = []

    # 0순위: 직접 입력한 프로퍼티
    for key in (PROP_SENTENCE, PROP_INSIGHT):
        v = clean_sentence(prop_text(props, key))
        t = score_sentence(v, TIER_PROP)
        if t is not None:
            cands.append({"t": v, "tier": t, "p": key})

    # 1~4순위: 본문 블록 (색칠 > 굵게 > 일반 > 후순위)
    for raw, tier, page_mark in page_blocks(token, page["id"]):
        v = clean_sentence(raw)
        t = score_sentence(v, tier)
        if t is not None:
            cands.append({"t": v, "tier": t, "p": page_mark})

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


def is_excluded(page):
    """노션 '책읽남' 열이 '제외'면 True. (열 이름·값의 공백 차이는 무시)"""
    v = prop_text(page.get("properties", {}), PROP_EXCLUDE)
    return _norm(v) in {_norm(x) for x in EXCLUDE_VALUES}


def usable_rows(rows):
    """'제외' 표시된 책을 걸러낸 목록."""
    return [p for p in rows if not is_excluded(p)]


def filter_rows(rows, keyword):
    """'제외' 표시된 책을 먼저 빼고, 키워드가 있으면 제목으로 한 번 더 거른다."""
    rows = usable_rows(rows)
    if not keyword:
        return rows
    return [p for p in rows if keyword.lower() in row_title(p).lower()]


# ── 8. 실행 모드 ──────────────────────────────────────────────
def cmd_check(token, db_id):
    """왜 문장이 안 나오는지 진단용. 노션 데이터 + 캐시 상태를 보여준다."""
    all_rows = fetch_rows(token, db_id)
    excluded = [p for p in all_rows if is_excluded(p)]
    rows = usable_rows(all_rows)
    cache = load_cache()
    n_prop = sum(1 for p in rows if prop_text(p.get("properties", {}), PROP_SENTENCE).strip()
                 or prop_text(p.get("properties", {}), PROP_INSIGHT).strip())
    # 캐시에는 예전에 읽었지만 지금은 제외됐거나 노션에서 사라진 책도 남아 있다.
    # 헷갈리지 않게 **지금 실제로 쓰는 책**만 세어 보여준다.
    live_ids = {p["id"] for p in rows}
    cached = [c for pid, c in cache["pages"].items() if pid in live_ids]
    stale = len(cache["pages"]) - len(cached)
    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for c in cached:
        for s in c.get("sentences", []):
            tier_counts[s.get("tier", 3)] = tier_counts.get(s.get("tier", 3), 0) + 1
    total_sent = sum(tier_counts.values())

    print(f"📚 독서 리스트 총 {len(all_rows)}권 "
          f"(사용 {len(rows)}권 · '책읽남=제외' {len(excluded)}권)")
    for p in excluded:
        print(f"      ⛔ 제외: {row_title(p)}")
    print(f"  · '한 문장'/'깨달은 점' 칸이 채워진 책 : {n_prop}권")
    print(f"  · 본문까지 읽어둔 책(캐시)            : {len(cached)}권 / {len(rows)}권")
    print(f"  · 캐시에 모인 문장                    : {total_sent}개")
    print(f"      직접입력 {tier_counts[0]} · 강조(색칠) {tier_counts[1]} · "
          f"굵게 {tier_counts[2]} · 본문 {tier_counts[3]} · 후순위 {tier_counts[4]}")
    if len(cached) < len(rows):
        print(f"  💡 아직 안 읽은 책 {len(rows) - len(cached)}권 → get_notion_book.py --build-cache")
    if stale:
        print(f"  🧹 안 쓰는 캐시 {stale}권분 (제외됐거나 노션에서 사라진 책) — "
              f"정리하려면 --clear-cache 후 --build-cache")
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
        # 한 책이 목록을 독차지하지 않게 책당 상한을 둔다(여러 책을 골고루 검수)
        per_book = sents if keyword else sents[:LIST_PER_BOOK]
        for s in per_book:
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
    """브리핑용 한 문장 1건을 **확률 추첨**으로 고른다.

    예전에는 색칠한 문장이 있으면 무조건 그것만 나갔다. 3시간마다 보내는 상황에서는
    금방 단조로워지므로, 아래처럼 바꿨다.

      1) 후보가 있는 책을 최대 BOOKS_PER_PICK 권 모은다 (책 순서는 매번 랜덤)
      2) **책마다 총 몫을 1로 맞춘다** → 어떤 책이든 뽑힐 확률이 같다(골고루).
      3) 그 1을 등급 비율(TIER_WEIGHT)대로 나누고, 등급 몫은 그 등급의 문장들이 나눠 갖는다.
         → 본문이 200줄인 책이 판을 독차지하지 못하고, 색칠이 없는 책도 밀리지 않는다.
      4) 가중치대로 딱 하나를 추첨한다.

    결과적으로 **책은 골고루, 그 안에서는 색칠한 글귀가 가장 자주** 나온다.
    못 뽑으면 지어내지 않고 실패(코드 2).
    """
    all_rows = fetch_rows(token, db_id)
    rows = filter_rows(all_rows, keyword)
    if not rows:
        if keyword and any(keyword.lower() in row_title(p).lower()
                           for p in all_rows if is_excluded(p)):
            die(f"'{keyword}' 은 노션 '책읽남' 열이 '제외'로 되어 있어 쓰지 않습니다.", 2)
        die(f"'{keyword}' 이라는 책을 독서 리스트에서 찾지 못했습니다.", 2)

    cache = load_cache()
    state = load_state()
    used = set(state["used"])

    random.shuffle(rows)                        # 매번 다른 책부터 살펴본다

    pool = []          # [(문장, 페이지, 가중치), ...] ← 추첨함
    seen_used = None   # 이미 보낸 문장(전부 소진됐을 때 쓸 예비책)
    fetched = 0        # 이번 실행에서 노션에서 새로 읽은 책 수
    books = 0          # 후보를 건진 책 수

    for page in rows:
        # 평소엔 최대 MAX_FETCH_PER_RUN 권만 새로 읽는다(응답 속도).
        # 아직 후보를 하나도 못 찾은 '빈손' 상태면 더 읽어본다.
        empty_handed = not pool and seen_used is None
        budget = MAX_FETCH_PER_RUN * (DESPERATE_MULTIPLIER if empty_handed else 1)
        allow = bool(keyword) or fetched < budget
        sents, did = sentences_for(token, page, cache, allow_fetch=allow)
        fetched += int(did)
        if not sents:
            continue

        fresh = [x for x in sents if fingerprint(x["t"]) not in used]
        if not fresh:
            seen_used = seen_used or (sents[0], page)
            continue

        # 같은 책 안에서 등급별로 묶는다
        by_tier = {}
        for x in fresh:
            by_tier.setdefault(x["tier"], []).append(x)
        # 책 하나가 갖는 총 몫을 1로 맞춘다(= 책은 균등). 그 1을 등급 비율대로 나누고,
        # 각 등급 몫은 그 등급의 문장들이 다시 똑같이 나눠 갖는다.
        #   → 색칠이 하나도 없는 책도 색칠 많은 책과 똑같은 확률로 뽑힌다.
        book_total = sum(TIER_WEIGHT.get(t, 1.0) for t in by_tier) or 1.0
        for tier, group in by_tier.items():
            share = TIER_WEIGHT.get(tier, 1.0) / book_total / len(group)
            for x in group:
                pool.append((x, page, share))

        books += 1
        if books >= BOOKS_PER_PICK:
            break

    _save_json(CACHE_PATH, cache)

    if pool:
        weights = [w for _, _, w in pool]
        sent, page, _ = random.choices(pool, weights=weights, k=1)[0]
        return emit(sent, page, state)

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
    """SOUL.md 브리핑 양식(2줄) 그대로 출력. 출처는 stderr(로그)로 따로 남긴다."""
    title = row_title(page)
    author = prop_text(page.get("properties", {}), PROP_AUTHOR)

    # 브리핑은 2줄: 글귀 / <제목> 저자  (머리말 줄은 쓰지 않는다)
    print(sent["t"])
    lo, hi = TITLE_WRAP
    print(f"{lo}{title}{hi}" + (f" {author}" if author else ""))

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
