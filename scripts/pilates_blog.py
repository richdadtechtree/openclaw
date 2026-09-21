#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pilates_blog.py — 마이비필라테스 네이버 블로그 글을 매일 1편 만들어 **슬랙 #심부름** 으로 보낸다.

무엇을 하나 (한 줄 요약)
-----------------------
  "오늘 날짜(한국시간) → 오늘의 주제 → AI가 글 작성 → 규칙 자동 점검 → 슬랙 발송"

전체 흐름
---------
  1) 규칙서 읽기   workspace/mybpilates_blog_prompt.md  (제목·본문 규칙 + 30일 주제 풀)
  2) 주제 고르기   한국시간 기준 '며칠' 인지 보고 Day N 주제 선택 (31일 → Day 1 로 순환)
  3) 글 만들기     AI 모델에게 규칙 + 주제 + 최근에 쓴 제목들을 주고 글을 받는다
  4) 자동 점검     제목 길이/특수문자, 본문 글자 수, [사진1~5], 키워드 횟수 … 를 직접 센다
                   → 문제가 있으면 "이 부분이 틀렸다" 고 알려주며 최대 3번까지 다시 쓰게 한다
  5) 슬랙 발송     규칙서의 출력 형식 그대로 #심부름 채널에 올린다

왜 이렇게 만들었나
-----------------
  • **AI 에이전트에게 "블로그 글 써서 보내" 라고 시키는 방식은 쓰지 않는다.**
    예전에 책 글귀를 그렇게 맡겼다가 AI가 스크립트를 안 돌리고 지어낸 사고가 있었다
    (HANDOFF.md 참고). 그래서 여기서는 **스크립트가 주인**이고 AI는 "글 쓰는 일"만 한다.
    주제 선택 · 규칙 점검 · 발송은 전부 코드가 한다.
  • **파이썬 표준 라이브러리만** 쓴다. 서버 시스템 `python3` 에는 `requests` 가 없기 때문.
    (이 리포의 단골 함정 — CLAUDE.md 참고) → cron 에 그냥 `python3` 로 걸어도 된다.

사용법
------
  python3 scripts/pilates_blog.py                 # 오늘 주제로 만들어 슬랙 발송
  python3 scripts/pilates_blog.py --dry-run       # 만들어서 화면에만 출력 (발송 안 함)
  python3 scripts/pilates_blog.py --day 7         # 주제를 7번으로 강제 (미리 만들어 보기)
  python3 scripts/pilates_blog.py --check         # 규칙서가 잘 읽히는지만 점검 (AI 호출 없음)
  python3 scripts/pilates_blog.py --list          # 30일 주제 목록 보기
  python3 scripts/pilates_blog.py --channel C123  # 다른 채널로 보내기

필요한 환경변수 (~/.openclaw/.env)
---------------------------------
  SLACK_BOT_TOKEN_DEFAULT   뚜떵또 봇 토큰 (없으면 SLACK_BOT_TOKEN 폴백)
  SLACK_ERRAND_CHANNEL      보낼 채널 ID (없으면 기본값 C0BNB0YRGSY = #심부름)
  GATEWAY_TOKEN             openclaw 게이트웨이 토큰 — 글쓰기 1순위 경로(ChatGPT Plus 구독 사용)
  GEMINI_API_KEY            2순위 경로(제미나이). 게이트웨이가 죽어 있을 때 대신 쓴다.
  (선택) PILATES_MODEL_ORDER   "gateway,gemini" 순서 바꾸기
  (선택) PILATES_GATEWAY_AGENT 게이트웨이로 부를 무툴 에이전트 (기본 openclaw/debate-gpt)
  (선택) PILATES_NOTIFY_ON_FAIL=0  글 생성 실패 시 슬랙에 실패 알림을 보내지 않기

⚠️ 봇이 채널에 없으면 `not_in_channel` 오류가 난다 → 슬랙에서 `/invite @뚜떵또` 한 번 해줄 것.

종료 코드
---------
  0 = 정상 (발송 또는 --dry-run 성공)
  2 = 규칙서 문제 (파일 없음 / 주제를 못 읽음)
  3 = 모델 호출 실패 · 슬랙 발송 실패 · 설정 누락
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# ── 경로 / 상수 ────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                              # ~/.openclaw
DEFAULT_SPEC = os.path.join(BASE, "workspace", "mybpilates_blog_prompt.md")
STATE_DIR = os.path.join(BASE, "workspace", "pilates_blog")   # 지난 글 보관(.gitignore 대상)
HISTORY_FILE = os.path.join(STATE_DIR, "history.jsonl")

KST = timezone(timedelta(hours=9))                        # 서버 시간대와 무관하게 '한국 날짜' 사용
DEFAULT_CHANNEL = "C0BNB0YRGSY"                           # 슬랙 #심부름
LINE = "━" * 28                                           # 규칙서 출력 형식의 구분선

# 제목에 쓰면 안 되는 기호들 (규칙서 "특수문자 사용 금지")
BANNED_TITLE_CHARS = "★☆♥♡◆◇➤▶◀■□●○※✔✅✨🔥💪💛◈♠♣!?~"

# 검증되지 않은 의학적 단정 — 들어가면 안 된다 (규칙서 "금지 사항")
BANNED_PHRASES = [
    "완치", "100% 보장", "100%보장", "즉시 효과", "부작용 없", "무조건 낫",
    "치료됩니다", "디스크가 낫", "병원 안 가도", "의학적으로 입증된 유일",
]

# 본문 글자 수 목표 (규칙서: 1000~1200자, 공백 포함)
BODY_MIN, BODY_MAX = 1000, 1200
BODY_HARD_MIN, BODY_HARD_MAX = 900, 1350   # 이 밖이면 "다시 써" 라고 되돌린다

# 제목 글자 수 목표 (규칙서: 25~35자)
TITLE_MIN, TITLE_MAX = 25, 35
TITLE_HARD_MIN, TITLE_HARD_MAX = 20, 40


# ── 0. .env 읽기 (다른 스크립트와 같은 방식, 추가 라이브러리 없음) ──────────
def load_env():
    """~/.openclaw/.env 파일을 읽어 환경변수로 올린다.

    python-dotenv 같은 외부 라이브러리를 쓰지 않는 이유: 서버 시스템 python3 에
    추가 패키지가 없기 때문. 이미 설정된 환경변수는 덮어쓰지 않는다(setdefault).
    """
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


# ── 1. 규칙서(마크다운) 읽기 ───────────────────────────────────────────────
def read_spec(path):
    """규칙서 파일을 통째로 읽어 문자열로 돌려준다. 없으면 None."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_comments(md):
    """마크다운 주석(<!-- ... -->)을 걷어낸다.

    왜 필요한가: 규칙서 맨 위 '사용법 안내' 주석 안에 예시로 적어둔
    `### Day 3 — …` 같은 줄을 진짜 주제로 잘못 읽는 사고가 있었다.
    (실제로 주제가 30개가 아니라 31개로 세어졌다.)
    """
    return re.sub(r"<!--.*?-->", "", md, flags=re.S)


def split_sections(md):
    """마크다운을 '## 제목' 단위로 잘라 {제목: 본문} 사전으로 만든다.

    이렇게 해두면 규칙서에서 필요한 부분(글 작성 규칙, 사진 컨셉 안내 …)만
    골라 AI에게 전달할 수 있다.
    """
    sections, cur, buf = {}, None, []
    for line in strip_comments(md).splitlines():
        m = re.match(r"^##\s+(?!#)(.*)$", line)     # '##' 만 (### 은 소제목이라 제외)
        if m:
            if cur is not None:
                sections[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1).strip(), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        sections[cur] = "\n".join(buf).strip()
    return sections


def parse_topics(md):
    """'### Day N — 이름' 블록들을 읽어 주제 목록으로 만든다.

    각 주제는 이렇게 생긴 사전이 된다:
      {"day": 1, "name": "필라테스 초보", "main": "필라테스 초보",
       "subs": ["필라테스 입문", ...], "direction": "...", "photos": ["...", ...]}
    """
    topics = []
    cur = None
    for raw in strip_comments(md).splitlines():
        # 제목(### Day N)은 반드시 줄 맨 앞에서 시작해야 한다.
        # 들여쓴 줄은 '예시로 적어둔 글' 이지 진짜 주제가 아니다.
        m = re.match(r"^###\s+Day\s+(\d+)\s*[—\-–]\s*(.+)$", raw)
        line = raw.strip()
        if m:
            if cur:
                topics.append(cur)
            cur = {"day": int(m.group(1)), "name": m.group(2).strip(),
                   "main": "", "subs": [], "direction": "", "photos": []}
            continue
        if cur is None:
            continue
        m = re.match(r"^-\s*메인:\s*(.+?)\s*\|\s*서브:\s*(.+)$", line)
        if m:
            cur["main"] = m.group(1).strip()
            cur["subs"] = [s.strip() for s in m.group(2).split(",") if s.strip()]
            continue
        m = re.match(r"^-\s*방향:\s*(.+)$", line)
        if m:
            cur["direction"] = m.group(1).strip()
            continue
        m = re.match(r"^-\s*사진:\s*(.+)$", line)
        if m:
            # "①스튜디오 전경 ②호흡 연습" → ["스튜디오 전경", "호흡 연습", ...]
            parts = re.split(r"[①②③④⑤⑥⑦⑧⑨⑩]", m.group(1))
            cur["photos"] = [p.strip(" ·,") for p in parts if p.strip(" ·,")]
    if cur:
        topics.append(cur)
    topics.sort(key=lambda t: t["day"])
    return topics


def pick_topic(topics, day_of_month):
    """오늘 날짜(며칠)에 해당하는 주제를 고른다.

    규칙서: 1일→주제1 … 30일→주제30, 31일→주제1 로 순환.
    주제가 30개가 아니어도(예: 20개만 써둠) 나머지 연산으로 안전하게 돈다.
    """
    if not topics:
        return None
    idx = (day_of_month - 1) % len(topics)
    return topics[idx]


# ── 2. AI에게 줄 지시문 만들기 ─────────────────────────────────────────────
def build_rules_text(sections):
    """규칙서에서 'AI가 알아야 할 규칙' 부분만 모아 하나의 글로 만든다.

    '출력 형식' 섹션은 일부러 뺀다 — 최종 모양은 이 스크립트가 직접 조립하기 때문.
    (AI가 형식까지 흉내 내면 파싱이 흔들린다.)
    """
    want = ["글 작성 규칙", "사진 컨셉 안내", "참고: 네이버 상위노출 핵심 원칙"]
    chunks = []
    for name in want:
        for key, body in sections.items():
            if key.startswith(name):
                chunks.append(f"## {key}\n{body}")
                break
    return "\n\n".join(chunks).strip()


SYSTEM_PROMPT = """너는 '마이비필라테스' 네이버 블로그를 직접 운영하는 필라테스 전문 강사다.
독자가 읽고 "나도 이런 적 있어" 하고 고개를 끄덕일 만한, 솔직하고 담백한 글을 쓴다.

반드시 지킬 것:
- 아래 '규칙'을 글자 그대로 지킨다. 특히 글자 수와 [사진N] 표시.
- 검증되지 않은 의학적 주장(완치, 100% 보장 등)은 절대 쓰지 않는다.
- 다른 운동이나 다른 업체를 깎아내리지 않는다.
- AI 티가 나는 말버릇("~해볼까요?", "~인데요!")을 남발하지 않는다.
- 출력은 지정된 형식만 낸다. 설명·인사말·사과문을 덧붙이지 않는다."""

OUTPUT_FORMAT = """출력은 아래 세 덩어리로만, 표시를 그대로 붙여서 낸다.

[제목]
(제목 한 줄. 25~35자. 특수문자 없이.)

[본문]
(본문 1000~1200자. 소제목은 **굵게**. [사진1]~[사진5] 를 본문 흐름에 맞게 한 번씩 배치.)

[사진컨셉]
1. (사진1 설명 — 무엇을 어떤 각도로 찍을지)
2. (사진2 설명)
3. (사진3 설명)
4. (사진4 설명)
5. (사진5 설명)"""


def build_user_prompt(rules, topic, today_str, recent_titles, feedback=None):
    """AI에게 보낼 실제 주문서. 규칙 + 오늘 주제 + 겹치면 안 되는 최근 제목 + (재작성 시) 지적사항."""
    subs = ", ".join(topic["subs"]) if topic["subs"] else "(없음)"
    photos = "\n".join(f"  {i}. {p}" for i, p in enumerate(topic["photos"], 1)) or "  (지정 없음)"

    parts = [
        f"# 규칙\n{rules}",
        "\n# 오늘 쓸 글\n"
        f"- 날짜: {today_str}\n"
        f"- 주제: Day {topic['day']} — {topic['name']}\n"
        f"- 메인 키워드: {topic['main']}  ← 제목 앞부분에 넣고, 본문에 3~4회만 자연스럽게\n"
        f"- 서브 키워드: {subs}  ← 본문에 1~2회\n"
        f"- 글의 방향: {topic['direction']}\n"
        f"- 사진 자리 힌트(이 순서대로 [사진1]~[사진5]):\n{photos}",
    ]
    if recent_titles:
        joined = "\n".join(f"  - {t}" for t in recent_titles)
        parts.append("\n# 최근에 이미 올린 제목들 (표현·구성이 겹치지 않게 할 것)\n" + joined)
    if feedback:
        parts.append("\n# ⚠️ 직전 원고에서 발견된 문제 (이번엔 반드시 고칠 것)\n"
                     + "\n".join(f"  - {f}" for f in feedback))
    parts.append("\n# 출력 형식\n" + OUTPUT_FORMAT)
    return "\n".join(parts)


# ── 3. 모델 호출 (표준 라이브러리 HTTP) ────────────────────────────────────
def http_post_json(url, headers, payload, timeout):
    """JSON 을 POST 하고 (상태코드, 응답문자열) 을 돌려준다. requests 없이 동작."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:                     # 4xx/5xx 도 본문을 봐야 원인을 안다
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                  # 타임아웃·연결 실패 등
        return 0, f"{type(e).__name__}: {e}"


def call_gateway(system_prompt, user_prompt, timeout):
    """1순위: openclaw 게이트웨이(OpenAI 호환 Chat Completions).

    debate.py 와 같은 길이다. 별도 API 키 없이 ChatGPT Plus 구독 세션을 쓰고,
    툴이 막힌 전용 에이전트(debate-gpt)를 부르므로 글만 써서 돌려준다.
    """
    token = os.getenv("GATEWAY_TOKEN", "")
    if not token:
        return None, "GATEWAY_TOKEN 없음"
    url = os.getenv("PILATES_GATEWAY_URL", "http://127.0.0.1:18789/v1/chat/completions")
    agent = os.getenv("PILATES_GATEWAY_AGENT", "openclaw/debate-gpt")
    status, body = http_post_json(
        url,
        {"Authorization": f"Bearer {token}"},
        {"model": agent,
         "messages": [{"role": "system", "content": system_prompt},
                      {"role": "user", "content": user_prompt}],
         "max_tokens": 2200, "temperature": 0.8},
        timeout,
    )
    if status != 200:
        return None, f"게이트웨이 오류({status}): {body[:200]}"
    try:
        return json.loads(body)["choices"][0]["message"]["content"].strip(), None
    except Exception as e:
        return None, f"게이트웨이 응답 파싱 실패: {e}"


def call_gemini(system_prompt, user_prompt, timeout):
    """2순위: 제미나이 REST API 직접 호출. 게이트웨이가 죽어 있어도 글이 나오게 하는 보험."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None, "GEMINI_API_KEY 없음"
    model = os.getenv("PILATES_GEMINI_MODEL", "gemini-flash-latest")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    status, body = http_post_json(
        url,
        {"x-goog-api-key": key},
        {"systemInstruction": {"parts": [{"text": system_prompt}]},
         "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
         "generationConfig": {"maxOutputTokens": 2600, "temperature": 0.8}},
        timeout,
    )
    if status != 200:
        return None, f"제미나이 오류({status}): {body[:200]}"
    try:
        parts = json.loads(body)["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        return (text, None) if text else (None, "빈 응답(안전 필터 가능)")
    except Exception as e:
        return None, f"제미나이 응답 파싱 실패: {e}"


def generate(system_prompt, user_prompt, timeout, order=None):
    """설정된 순서대로 모델을 시도한다. 하나라도 성공하면 그 글을 쓴다."""
    backends = {"gateway": call_gateway, "gemini": call_gemini}
    order = order or [s.strip() for s in
                      os.getenv("PILATES_MODEL_ORDER", "gateway,gemini").split(",") if s.strip()]
    errors = []
    for name in order:
        fn = backends.get(name)
        if not fn:
            errors.append(f"{name}: 알 수 없는 경로")
            continue
        text, err = fn(system_prompt, user_prompt, timeout)
        if text:
            return text, name, errors
        errors.append(f"{name}: {err}")
        print(f"   … {name} 실패 → {err}", file=sys.stderr)
    return None, None, errors


# ── 4. AI 답변 쪼개기 ──────────────────────────────────────────────────────
def parse_draft(text):
    """AI가 낸 글을 [제목]/[본문]/[사진컨셉] 세 덩어리로 나눈다.

    AI가 표시를 조금 다르게 써도(**[제목]**, 【제목】 등) 최대한 알아듣게 만든다.
    """
    if not text:
        return None, None, []
    t = text.replace("【", "[").replace("】", "]")
    t = re.sub(r"\*\*\s*\[(제목|본문|사진컨셉)\]\s*\*\*", r"[\1]", t)
    t = re.sub(r"^#+\s*\[(제목|본문|사진컨셉)\]", r"[\1]", t, flags=re.M)

    def grab(tag, nexts):
        stop = "|".join(re.escape(f"[{n}]") for n in nexts)
        pat = re.escape(f"[{tag}]") + r"\s*(.*?)(?=" + (stop + r"|\Z" if stop else r"\Z") + r")"
        m = re.search(pat, t, flags=re.S)
        return m.group(1).strip() if m else ""

    title = grab("제목", ["본문", "사진컨셉"])
    body = grab("본문", ["사진컨셉"])
    photo_raw = grab("사진컨셉", [])

    # 제목은 한 줄만. 앞에 "제목:" 이 또 붙어 있으면 떼어낸다.
    title = title.splitlines()[0].strip() if title else ""
    title = re.sub(r"^제목\s*[:：]\s*", "", title).strip().strip('"').strip("'")

    # 사진 컨셉은 "1. ..." 형태 다섯 줄을 뽑는다.
    photos = []
    for line in photo_raw.splitlines():
        m = re.match(r"^\s*(\d+)[.)]\s*(.+)$", line.strip())
        if m:
            photos.append(m.group(2).strip())
    return title or None, body or None, photos


# ── 5. 자동 점검 (규칙을 코드가 직접 센다) ─────────────────────────────────
def body_length(body):
    """본문 글자 수. [사진N] 표시와 줄바꿈은 빼고, 공백은 포함해서 센다.

    ([사진N] 은 나중에 사진으로 바뀔 자리 표시라 '글' 로 치지 않는 게 맞다.)
    """
    t = re.sub(r"\[사진\s*\d+\]", "", body)
    t = t.replace("\r", "")
    return len(t.replace("\n", ""))


def count_keyword(text, keyword):
    """키워드가 몇 번 나오는지 센다(띄어쓰기 차이는 무시)."""
    if not keyword:
        return 0
    norm = lambda s: re.sub(r"\s+", "", s)
    return norm(text).count(norm(keyword))


def validate(title, body, photos, topic):
    """규칙 위반 목록을 돌려준다. (빈 목록 = 완벽)

    두 종류로 나눈다:
      hard  … 다시 쓰게 만들 정도의 문제 (글자 수 크게 벗어남, 사진 표시 누락 등)
      soft  … 알려는 주되 그냥 보내도 되는 정도 (목표 범위에서 살짝 벗어남)
    """
    hard, soft = [], []
    main = topic["main"]

    # (1) 제목
    tlen = len(title)
    if tlen < TITLE_HARD_MIN or tlen > TITLE_HARD_MAX:
        hard.append(f"제목이 {tlen}자다. 25~35자로 다시 써라.")
    elif tlen < TITLE_MIN or tlen > TITLE_MAX:
        soft.append(f"제목 {tlen}자 (권장 25~35자)")
    bad = [c for c in title if c in BANNED_TITLE_CHARS]
    if bad:
        hard.append(f"제목에 금지된 특수문자 {''.join(sorted(set(bad)))} 가 있다. 빼고 다시 써라.")
    if count_keyword(title, main) == 0:
        hard.append(f"제목에 메인 키워드 '{main}' 이 없다. 제목 앞부분에 넣어라.")
    else:
        pos = re.sub(r"\s+", "", title).find(re.sub(r"\s+", "", main))
        if pos > max(4, len(re.sub(r"\s+", "", title)) // 2):
            soft.append(f"메인 키워드가 제목 뒤쪽({pos}번째 글자)에 있다 — 앞부분 권장")

    # (2) 본문 길이
    blen = body_length(body)
    if blen < BODY_HARD_MIN or blen > BODY_HARD_MAX:
        hard.append(f"본문이 {blen}자다. 1000~1200자로 맞춰 다시 써라.")
    elif blen < BODY_MIN or blen > BODY_MAX:
        soft.append(f"본문 {blen}자 (권장 1000~1200자)")

    # (3) 사진 자리 표시 [사진1]~[사진5]
    missing = [n for n in range(1, 6) if not re.search(rf"\[사진\s*{n}\]", body)]
    if missing:
        hard.append("본문에 " + ", ".join(f"[사진{n}]" for n in missing) + " 표시가 빠졌다. 넣어라.")

    # (4) 메인 키워드 횟수 (3~4회)
    kc = count_keyword(body, main)
    if kc < 3:
        hard.append(f"본문에 메인 키워드 '{main}' 이 {kc}번뿐이다. 3~4번 자연스럽게 넣어라.")
    elif kc > 5:
        hard.append(f"본문에 '{main}' 이 {kc}번 나온다 — 네이버 스팸 처리 위험. 3~4번으로 줄여라.")
    elif kc == 5:
        soft.append(f"메인 키워드 {kc}회 (권장 3~4회)")

    # (5) 소제목 2~3개 (**굵게** 표시)
    subs = re.findall(r"\*\*([^*\n]{2,40})\*\*", body)
    if len(subs) < 2:
        hard.append(f"굵은 소제목이 {len(subs)}개다. 2~3개로 나눠 써라.")
    elif len(subs) > 3:
        soft.append(f"소제목 {len(subs)}개 (권장 2~3개)")

    # (6) 사진 컨셉 5개
    if len(photos) != 5:
        hard.append(f"사진 컨셉이 {len(photos)}개다. 정확히 5개를 써라.")

    # (7) 금지 표현 (검증되지 않은 의학적 주장)
    hits = [p for p in BANNED_PHRASES if p in body]
    if hits:
        hard.append("검증되지 않은 표현 " + ", ".join(f"'{h}'" for h in hits) + " 를 빼라.")

    # (8) 키워드가 좁은 구간에 몰려 반복되는지 (규칙: 같은 키워드 3회 이상 연속 반복 금지)
    flat = re.sub(r"\s+", "", body)
    k = re.sub(r"\s+", "", main)
    if k:
        for m in re.finditer(re.escape(k), flat):
            window = flat[m.start(): m.start() + 60]
            if window.count(k) >= 3:
                soft.append("메인 키워드가 좁은 구간에 3번 이상 몰려 있다")
                break
    return hard, soft


# ── 6. 최종 메시지 조립 + 슬랙 발송 ────────────────────────────────────────
def to_slack_bold(text):
    """마크다운 **굵게** 를 슬랙 표기 *굵게* 로 바꾼다 (슬랙에서 실제로 굵게 보이도록)."""
    return re.sub(r"\*\*([^*\n]+)\*\*", r"*\1*", text)


def build_message(date_str, topic, title, body, photos, warnings):
    """규칙서의 '출력 형식' 그대로 최종 메시지를 만든다."""
    subs = ", ".join(topic["subs"]) if topic["subs"] else "-"
    photo_lines = "\n".join(f"{i}. {p}" for i, p in enumerate(photos, 1))
    msg = (
        f"📝 *마이비필라테스 블로그 글* ({date_str})\n"
        f"🔑 메인 키워드: {topic['main']}\n"
        f"🏷️ 서브 키워드: {subs}\n"
        f"{LINE}\n\n"
        f"제목: {title}\n\n"
        f"{to_slack_bold(body).strip()}\n\n"
        f"{LINE}\n\n"
        f"📷 오늘의 사진 컨셉:\n{photo_lines}\n\n"
        f"{LINE}\n"
        f"✅ 발행 전 체크리스트:\n"
        f"- [ ] 본인 경험 한두 문장 추가\n"
        f"- [ ] 직접 찍은 사진 5장 매칭\n"
        f"- [ ] 제목 앞부분에 키워드 확인\n"
        f"- [ ] 발행 시 주제 카테고리 선택"
    )
    if warnings:
        msg += "\n\n⚠️ 자동 점검에서 걸린 부분 (발행 전 눈으로 확인):\n" + \
               "\n".join(f"- {w}" for w in warnings)
    return msg


def chunk(text, limit=3500):
    """슬랙 한 메시지 한도(4000자)를 넘지 않게 줄 단위로 쪼갠다.

    ⚠️ 한 줄 자체가 한도보다 길 수도 있다(줄바꿈 없이 긴 문단).
       그때는 글자 수로 잘라야 한다 — 안 그러면 슬랙이 `msg_too_long` 으로 거절한다.
    """
    parts, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:                 # 한 줄이 한도보다 길면 통째로 잘라 넣는다
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) > limit and cur:
            parts.append(cur)
            cur = ""
        cur += line
    if cur:
        parts.append(cur)
    return parts or [text]


def post_to_slack(text, channel, token):
    """슬랙에 글을 올린다. 성공하면 True."""
    ok_all = True
    parts = chunk(text)
    for i, part in enumerate(parts, 1):
        prefix = f"(이어서 {i}/{len(parts)})\n" if i > 1 else ""
        status, body = http_post_json(
            "https://slack.com/api/chat.postMessage",
            {"Authorization": f"Bearer {token}"},
            {"channel": channel, "text": prefix + part, "unfurl_links": False},
            30,
        )
        try:
            data = json.loads(body)
        except Exception:
            data = {"ok": False, "error": f"HTTP {status}: {body[:120]}"}
        if not data.get("ok"):
            err = data.get("error")
            print(f"❌ 슬랙 발송 실패: {err}", file=sys.stderr)
            if err == "not_in_channel":
                print("   💡 슬랙 채널에서 `/invite @뚜떵또` 로 봇을 초대하세요.", file=sys.stderr)
            elif err == "channel_not_found":
                print("   💡 채널 ID 를 확인하세요 (.env 의 SLACK_ERRAND_CHANNEL).", file=sys.stderr)
            ok_all = False
        time.sleep(0.3)
    return ok_all


# ── 7. 지난 글 기록 (같은 제목·구성 반복 방지) ─────────────────────────────
def load_recent_titles(limit=12):
    """최근에 보낸 제목들을 읽어온다. AI에게 '이것들과 겹치지 마라' 고 알려주기 위함."""
    if not os.path.isfile(HISTORY_FILE):
        return []
    titles = []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    titles.append(json.loads(line).get("title", ""))
                except Exception:
                    continue
    except OSError:
        return []
    return [t for t in titles if t][-limit:]


def save_history(record):
    """오늘 보낸 글을 기록으로 남긴다 (한 줄 JSON)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[경고] 기록 저장 실패(무시하고 계속): {e}", file=sys.stderr)


# ── 8. 메인 ────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="마이비필라테스 블로그 글 자동 생성 → 슬랙 #심부름")
    ap.add_argument("--dry-run", action="store_true", help="발송하지 않고 화면에만 출력")
    ap.add_argument("--check", action="store_true", help="규칙서 파싱만 점검 (AI 호출 없음)")
    ap.add_argument("--list", action="store_true", help="30일 주제 목록 보기")
    ap.add_argument("--day", type=int, help="주제 번호 강제 지정 (1~30)")
    ap.add_argument("--date", help="기준 날짜 강제 (YYYY-MM-DD)")
    ap.add_argument("--channel", help="보낼 슬랙 채널 ID")
    ap.add_argument("--spec", default=os.getenv("PILATES_SPEC", DEFAULT_SPEC), help="규칙서 경로")
    ap.add_argument("--retries", type=int, default=2, help="규칙 위반 시 다시 쓰게 할 횟수 (기본 2)")
    ap.add_argument("--timeout", type=float, default=float(os.getenv("PILATES_TIMEOUT_SEC", "180")),
                    help="모델 응답 대기 초 (기본 180)")
    ap.add_argument("--no-history", action="store_true", help="기록 파일에 남기지 않음")
    args = ap.parse_args(argv)

    load_env()

    # 1) 규칙서 읽기
    md = read_spec(args.spec)
    if md is None:
        print(f"❌ 규칙서가 없습니다: {args.spec}", file=sys.stderr)
        return 2
    sections = split_sections(md)
    topics = parse_topics(md)
    rules = build_rules_text(sections)

    if args.list:
        for t in topics:
            print(f"Day {t['day']:2d} — {t['name']}  (메인: {t['main']}, 사진 {len(t['photos'])}개)")
        return 0

    if args.check:
        print(f"규칙서: {args.spec}")
        print(f"  섹션 {len(sections)}개, 주제 {len(topics)}개, 규칙 본문 {len(rules)}자")
        problems = []
        seen = {}
        for t in topics:
            seen.setdefault(t["day"], 0)
            seen[t["day"]] += 1
        dups = [d for d, n in seen.items() if n > 1]
        if dups:
            problems.append("Day 번호가 중복됨: " + ", ".join(str(d) for d in sorted(dups)))
        if len(topics) < 28:
            problems.append(f"주제가 {len(topics)}개뿐 (30개 권장)")
        for t in topics:
            if not t["main"]:
                problems.append(f"Day {t['day']}: 메인 키워드 없음")
            if len(t["photos"]) != 5:
                problems.append(f"Day {t['day']}: 사진 힌트 {len(t['photos'])}개 (5개 필요)")
            if not t["direction"]:
                problems.append(f"Day {t['day']}: 방향 없음")
        if not rules:
            problems.append("'글 작성 규칙' 섹션을 못 찾음")
        print(f"  토큰: 게이트웨이 {'O' if os.getenv('GATEWAY_TOKEN') else 'X'} / "
              f"제미나이 {'O' if os.getenv('GEMINI_API_KEY') else 'X'} / "
              f"슬랙 {'O' if (os.getenv('SLACK_BOT_TOKEN_DEFAULT') or os.getenv('SLACK_BOT_TOKEN')) else 'X'}")
        print(f"  채널: {args.channel or os.getenv('SLACK_ERRAND_CHANNEL') or DEFAULT_CHANNEL}")
        if problems:
            print("⚠️ 문제:")
            for p in problems:
                print(f"  - {p}")
            return 2
        print("✅ 규칙서 이상 없음")
        return 0

    # 2) 오늘 주제 고르기 (한국시간 기준 — 서버 시간대와 무관하게 정확)
    if args.date:
        try:
            today = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
        except ValueError:
            print("❌ --date 형식은 YYYY-MM-DD 입니다.", file=sys.stderr)
            return 2
    else:
        today = datetime.now(KST)
    date_str = today.strftime("%Y-%m-%d")
    topic = pick_topic(topics, args.day if args.day else today.day)
    if not topic or not topic["main"]:
        print("❌ 오늘 주제를 규칙서에서 읽지 못했습니다. `--check` 로 확인하세요.", file=sys.stderr)
        return 2
    print(f"📅 {date_str} → Day {topic['day']} — {topic['name']} (메인: {topic['main']})")

    # 3) 글 만들기 + 자동 점검 (문제가 있으면 지적해서 다시 쓰게 한다)
    recent = load_recent_titles()
    feedback, best, errors = None, None, []
    for attempt in range(1, args.retries + 2):
        prompt = build_user_prompt(rules, topic, date_str, recent, feedback)
        print(f"✍️  원고 작성 중… (시도 {attempt}/{args.retries + 1})")
        raw, backend, errs = generate(SYSTEM_PROMPT, prompt, args.timeout)
        errors.extend(errs)
        if not raw:
            continue
        title, body, photos = parse_draft(raw)
        if not title or not body:
            feedback = ["[제목]/[본문]/[사진컨셉] 표시를 붙여 형식대로 다시 내라."]
            print("   … 형식을 못 알아봐서 다시 요청합니다.", file=sys.stderr)
            continue
        hard, soft = validate(title, body, photos, topic)
        cand = {"title": title, "body": body, "photos": photos,
                "hard": hard, "soft": soft, "backend": backend}
        if best is None or len(hard) < len(best["hard"]):
            best = cand                                   # 가장 흠 적은 원고를 들고 있는다
        if not hard:
            print(f"   ✅ 점검 통과 (모델: {backend}, 본문 {body_length(body)}자)")
            break
        print("   ⚠️ 점검에 걸림 → 다시 요청: " + " / ".join(hard), file=sys.stderr)
        feedback = hard

    if best is None:
        print("❌ 글을 만들지 못했습니다: " + " | ".join(errors[-3:]), file=sys.stderr)
        # 조용히 사라지면 "오늘 글이 안 왔네?" 를 알 수 없으니 실패 사실만 짧게 알린다.
        if os.getenv("PILATES_NOTIFY_ON_FAIL", "1") != "0" and not args.dry_run:
            token = os.getenv("SLACK_BOT_TOKEN_DEFAULT") or os.getenv("SLACK_BOT_TOKEN")
            channel = args.channel or os.getenv("SLACK_ERRAND_CHANNEL") or DEFAULT_CHANNEL
            if token:
                post_to_slack(
                    f"⚠️ {date_str} 마이비필라테스 블로그 글을 만들지 못했습니다.\n"
                    f"(주제: Day {topic['day']} {topic['name']} / 사유: {errors[-1] if errors else '알 수 없음'})\n"
                    f"수동 재시도: `python3 ~/.openclaw/scripts/pilates_blog.py`",
                    channel, token)
        return 3

    warnings = best["hard"] + best["soft"]
    message = build_message(date_str, topic, best["title"], best["body"], best["photos"], warnings)

    # 4) 발송
    if args.dry_run:
        print("── 보낼 내용 (실제 발송 안 함) " + "─" * 20)
        print(message)
        return 0

    token = os.getenv("SLACK_BOT_TOKEN_DEFAULT") or os.getenv("SLACK_BOT_TOKEN")
    channel = args.channel or os.getenv("SLACK_ERRAND_CHANNEL") or DEFAULT_CHANNEL
    if not token:
        print("❌ SLACK_BOT_TOKEN_DEFAULT(또는 SLACK_BOT_TOKEN)이 .env 에 없습니다.", file=sys.stderr)
        return 3
    if not post_to_slack(message, channel, token):
        return 3

    print(f"✅ 발송 완료 → {channel} (모델: {best['backend']}, 본문 {body_length(best['body'])}자)")
    if warnings:
        print("   ⚠️ 남은 점검 사항: " + " / ".join(warnings))
    if not args.no_history:
        save_history({"date": date_str, "day": topic["day"], "topic": topic["name"],
                      "main": topic["main"], "title": best["title"],
                      "backend": best["backend"], "chars": body_length(best["body"]),
                      "warnings": warnings})
    return 0


# 테스트에서 "명령줄로 부른 것처럼" 돌려보기 위한 이름 (test_pilates_blog.py 사용)
main_for_test = main


if __name__ == "__main__":
    sys.exit(main())
