#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pilates_blog.py — 미리 써둔 마이비필라테스 블로그 글을 **하루 한 편씩** 슬랙 #심부름 으로 배달한다.

무엇을 하나 (한 줄 요약)
-----------------------
  "창고(workspace/pilates_posts/)에서 아직 안 보낸 글 중 제일 앞 것 → 규칙 점검 → 슬랙 발송"

⚠️ 이 스크립트는 **글을 쓰지 않는다.** AI도 부르지 않는다.
   글은 **클로드가 미리 써서 창고에 넣어둔다.** 이 스크립트는 우체부일 뿐이다.

왜 이렇게 바꿨나 (2026-09-21)
----------------------------
  처음엔 이 스크립트가 직접 AI를 불러 글을 쓰게 만들었다. 그런데 서버에서 돌려보니
    · 게이트웨이(ChatGPT 구독 경유) → 500 internal error
    · 제미나이 키 → 401 "service account is deleted or disabled" (키가 죽어 있음)
  둘 다 죽어 있었다. 매일 아침 글이 나와야 하는데 **남의 서비스 상태에 목을 매는 구조**였다.

  그래서 역할을 갈랐다:
    ✍️  글쓰기 = **클로드**(사람이 대화로 부탁 → 품질 확인 → 창고에 저장)
    📮 배달   = **이 스크립트**(키도, 인터넷 AI도 필요 없음. 슬랙 토큰 하나면 끝)
  이러면 모델이 죽어도 창고에 글이 남아 있는 한 배달은 멈추지 않는다.
  (같은 이유로 book_slack.py 도 'AI 미경유' 구조다 — HANDOFF.md 참고)

배달은 멈추지 않는다
-------------------
  · 한 바퀴(창고 전체)를 다 보내면 **자동으로 처음부터 다시** 돈다. 그래서 글이 끊기지 않는다.
  · 다시 보내는 글에는 "🔁 N회차 — 전에 보낸 글" 안내가 붙는다.
    네이버는 같은 글을 그대로 올리면 중복 문서로 보므로, 도입부와 경험 문장을 바꿔 올리시면 된다.
  · 새 글이 5편 이하로 남으면 미리 알려준다 → 클로드에게 "필라테스 글 더 써줘" 하면 창고가 늘어난다.
  · 새로 넣은 글은 **보낸 횟수가 0이라 가장 먼저** 나간다.

글 파일 형식 (workspace/pilates_posts/day01-….md)
-------------------------------------------------
    제목: 필라테스 초보가 첫 수업 전에 알아야 할 세 가지
    메인: 필라테스 초보
    서브: 필라테스 입문, 필라테스 준비물, 처음 필라테스
    주제: Day 1 — 필라테스 초보
    ===본문===
    (본문 1000~1200자, 소제목은 **굵게**, [사진1]~[사진5] 배치)
    ===사진===
    1. 사진1 컨셉
    ... 5번까지

사용법
------
  python3 scripts/pilates_blog.py                 # 다음 차례 글을 #심부름 에 배달
  python3 scripts/pilates_blog.py --dry-run       # 배달 안 하고 화면에만 보기
  python3 scripts/pilates_blog.py --check         # 창고 전체를 규칙에 맞는지 검사
  python3 scripts/pilates_blog.py --list          # 창고 목록(보냄/안 보냄) 보기
  python3 scripts/pilates_blog.py --day 7         # 7번 글을 지정해서 배달
  python3 scripts/pilates_blog.py --file <경로>   # 특정 파일을 배달
  python3 scripts/pilates_blog.py --reset         # '보냄' 기록 지우기(처음부터 다시)

필요한 환경변수 (~/.openclaw/.env)  ← AI 키는 하나도 필요 없다
------------------------------------------------------------
  SLACK_BOT_TOKEN_DEFAULT   뚜떵또 봇 토큰 (없으면 SLACK_BOT_TOKEN 폴백)
  SLACK_ERRAND_CHANNEL      보낼 채널 ID (없으면 기본값 C0BNB0YRGSY = #심부름)
  (선택) PILATES_LOW_STOCK  재고 경고를 띄울 기준 편수 (기본 5)
  (선택) PILATES_POSTS_DIR  창고 폴더 경로

⚠️ 봇이 채널에 없으면 `not_in_channel` 오류 → 슬랙에서 `/invite @뚜떵또` 한 번.

종료 코드
---------
  0 = 정상 (배달 또는 --dry-run 성공)
  1 = 창고에 글 파일이 하나도 없음 — 안내만 보내고 조용히 끝
  2 = 창고/파일 형식 문제
  3 = 슬랙 발송 실패 · 설정 누락
"""

from __future__ import annotations

import argparse
import glob
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
BASE = os.path.dirname(HERE)                                   # ~/.openclaw
POSTS_DIR = os.getenv("PILATES_POSTS_DIR") or os.path.join(BASE, "workspace", "pilates_posts")
STATE_DIR = os.path.join(BASE, "workspace", "pilates_blog")    # 보냄 기록(.gitignore 대상)
SENT_FILE = os.path.join(STATE_DIR, "sent.jsonl")

KST = timezone(timedelta(hours=9))                             # 서버 시간대와 무관하게 '한국 날짜'
DEFAULT_CHANNEL = "C0BNB0YRGSY"                                # 슬랙 #심부름
LINE = "━" * 28

# 제목에 쓰면 안 되는 기호들 (규칙서 "특수문자 사용 금지")
BANNED_TITLE_CHARS = "★☆♥♡◆◇➤▶◀■□●○※✔✅✨🔥💪💛◈♠♣!?~"

# 검증되지 않은 의학적 단정 — 들어가면 안 된다 (규칙서 "금지 사항")
BANNED_PHRASES = [
    "완치", "100% 보장", "100%보장", "즉시 효과", "부작용 없", "무조건 낫",
    "치료됩니다", "디스크가 낫", "병원 안 가도", "의학적으로 입증된 유일",
]

BODY_MIN, BODY_MAX = 1000, 1200        # 본문 글자 수 목표 (규칙서)
TITLE_MIN, TITLE_MAX = 25, 35          # 제목 글자 수 목표 (규칙서)

BODY_MARK = "===본문==="
PHOTO_MARK = "===사진==="


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


# ── 1. 창고에서 글 읽기 ────────────────────────────────────────────────────
def parse_post(text):
    """글 파일 한 개를 제목·키워드·본문·사진컨셉으로 나눈다.

    형식이 어긋나면 (None, 사유) 를 돌려준다 — **추측해서 보내지 않는다.**
    """
    if BODY_MARK not in text:
        return None, f"'{BODY_MARK}' 표시가 없습니다"
    head, rest = text.split(BODY_MARK, 1)

    if PHOTO_MARK in rest:
        body, photo_raw = rest.split(PHOTO_MARK, 1)
    else:
        body, photo_raw = rest, ""

    post = {"title": "", "main": "", "subs": [], "topic": "",
            "body": body.strip(), "photos": []}

    # 머리말: "키: 값" 줄들
    for line in head.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(제목|메인|서브|주제)\s*[:：]\s*(.+)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "제목":
            post["title"] = val
        elif key == "메인":
            post["main"] = val
        elif key == "서브":
            post["subs"] = [s.strip() for s in val.split(",") if s.strip()]
        elif key == "주제":
            post["topic"] = val

    # 사진 컨셉: "1. ..." 로 시작하고, 번호 없는 다음 줄들은 그 사진의 추가 설명이다.
    #   1. 촬영: 무엇을 어떤 각도로
    #      포인트: 사진에 꼭 담겨야 할 동작 정보
    #      캡션: 사진 밑에 넣을 한 줄
    for line in photo_raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^(\d+)[.)]\s*(.+)$", stripped)
        if m:
            post["photos"].append(m.group(2).strip())
        elif post["photos"]:
            # 번호 없는 줄 = 바로 앞 사진의 이어지는 설명
            post["photos"][-1] += "\n" + stripped

    if not post["title"]:
        return None, "'제목:' 줄이 없습니다"
    if not post["main"]:
        return None, "'메인:' 줄이 없습니다"
    if not post["body"]:
        return None, "본문이 비어 있습니다"
    return post, None


def read_post(path):
    """파일 한 개를 읽어 (글, 사유) 로 돌려준다."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return None, f"파일을 못 읽음: {e}"
    post, err = parse_post(text)
    if post:
        post["file"] = path
    return post, err


def list_post_files(posts_dir=None):
    """창고의 글 파일을 이름순으로 모은다 (day01, day02, … 순서 = 배달 순서)."""
    d = posts_dir or POSTS_DIR
    return sorted(glob.glob(os.path.join(d, "*.md")))


# ── 2. '보냄' 기록 (같은 글을 두 번 보내지 않기) ───────────────────────────
def load_sent(state_file=None):
    """이미 보낸 글 파일 이름들을 읽어온다."""
    path = state_file or SENT_FILE
    sent = set()
    if not os.path.isfile(path):
        return sent
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    name = json.loads(line).get("file")
                except Exception:
                    continue
                if name:
                    sent.add(os.path.basename(name))
    except OSError:
        pass
    return sent


def load_sent_counts(state_file=None):
    """글마다 **몇 번** 보냈는지 센다. (바퀴 수 계산에 쓴다)"""
    path = state_file or SENT_FILE
    counts = {}
    if not os.path.isfile(path):
        return counts
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    name = json.loads(line).get("file")
                except Exception:
                    continue
                if name:
                    name = os.path.basename(name)
                    counts[name] = counts.get(name, 0) + 1
    except OSError:
        pass
    return counts


def mark_sent(record, state_file=None):
    """방금 보낸 글을 기록에 남긴다 (한 줄 JSON)."""
    path = state_file or SENT_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[경고] 보냄 기록 저장 실패(무시하고 계속): {e}", file=sys.stderr)


def pick_next(posts_dir=None, state_file=None):
    """다음에 배달할 글을 고른다. **창고가 비지 않는 한 배달은 멈추지 않는다.**

    고르는 방법: 지금까지 **가장 적게 보낸 글** 중 파일 이름이 제일 앞인 것.
      · 1바퀴째에는 결국 day01 → day02 → … 순서가 된다.
      · 한 바퀴를 다 돌면 자동으로 2바퀴째가 시작된다(다시 day01부터).
      · 중간에 새 글을 넣으면 보낸 횟수가 0이므로 **새 글이 먼저** 나간다.

    반환: (파일경로 또는 None, 이번 바퀴에 남은 편수, 지금이 몇 바퀴째인지)
    """
    files = list_post_files(posts_dir)
    if not files:
        return None, 0, 1
    counts = load_sent_counts(state_file)
    per_file = [(counts.get(os.path.basename(f), 0), f) for f in files]
    fewest = min(n for n, _ in per_file)
    candidates = sorted(f for n, f in per_file if n == fewest)
    return candidates[0], len(candidates), fewest + 1


# ── 3. 규칙 점검 (클로드가 쓴 글이라도 기계가 한 번 더 센다) ───────────────
def body_length(body):
    """본문 글자 수. [사진N] 표시와 줄바꿈은 빼고, 공백은 포함해서 센다."""
    t = re.sub(r"\[사진\s*\d+\]", "", body).replace("\r", "")
    return len(t.replace("\n", ""))


def count_keyword(text, keyword):
    """키워드가 몇 번 나오는지 센다(띄어쓰기 차이는 무시)."""
    if not keyword:
        return 0
    norm = lambda s: re.sub(r"\s+", "", s)
    return norm(text).count(norm(keyword))


def validate(post):
    """규칙 위반 목록을 돌려준다. (빈 목록 = 완벽)

    글은 클로드가 쓰지만, 사람도 기계도 실수한다. 그래서 **보내기 직전에** 한 번 더 센다:
    제목 길이·특수문자, 본문 글자 수, [사진1~5], 키워드 횟수, 소제목 개수, 금지 표현.
    """
    issues = []
    title, body, main = post["title"], post["body"], post["main"]

    # (1) 제목
    tlen = len(title)
    if tlen < TITLE_MIN or tlen > TITLE_MAX:
        issues.append(f"제목 {tlen}자 (권장 25~35자)")
    bad = [c for c in title if c in BANNED_TITLE_CHARS]
    if bad:
        issues.append(f"제목에 금지 특수문자 {''.join(sorted(set(bad)))}")
    if count_keyword(title, main) == 0:
        issues.append(f"제목에 메인 키워드 '{main}' 없음")
    else:
        pos = re.sub(r"\s+", "", title).find(re.sub(r"\s+", "", main))
        if pos > max(4, len(re.sub(r"\s+", "", title)) // 2):
            issues.append(f"메인 키워드가 제목 뒤쪽({pos}번째 글자) — 앞부분 권장")

    # (2) 본문 길이
    blen = body_length(body)
    if blen < BODY_MIN or blen > BODY_MAX:
        issues.append(f"본문 {blen}자 (권장 1000~1200자)")

    # (3) 사진 자리 표시 [사진1]~[사진5]
    missing = [n for n in range(1, 6) if not re.search(rf"\[사진\s*{n}\]", body)]
    if missing:
        issues.append("본문에 " + ", ".join(f"[사진{n}]" for n in missing) + " 없음")

    # (4) 메인 키워드 횟수 (3~4회, 5회 초과는 네이버 스팸 위험)
    kc = count_keyword(body, main)
    if kc < 3:
        issues.append(f"본문 메인 키워드 {kc}회 (권장 3~4회)")
    elif kc > 4:
        issues.append(f"본문 메인 키워드 {kc}회 — 과다(스팸 위험)")

    # (5) 굵은 소제목 2~3개
    subs = re.findall(r"\*\*([^*\n]{2,40})\*\*", body)
    if len(subs) < 2 or len(subs) > 3:
        issues.append(f"굵은 소제목 {len(subs)}개 (권장 2~3개)")

    # (6) 사진 컨셉 5개
    if len(post["photos"]) != 5:
        issues.append(f"사진 컨셉 {len(post['photos'])}개 (5개 필요)")

    thin = [i for i, p in enumerate(post["photos"], 1) if len(p.replace("\n", "")) < 20]
    if thin:
        issues.append("사진 컨셉 " + ", ".join(f"{i}번" for i in thin) + " 설명이 너무 짧음")

    # (7) 검증되지 않은 의학적 단정
    hits = [p for p in BANNED_PHRASES if p in body]
    if hits:
        issues.append("금지 표현 " + ", ".join(f"'{h}'" for h in hits))

    # (8) 키워드가 좁은 구간에 몰려 반복되는지
    flat, k = re.sub(r"\s+", "", body), re.sub(r"\s+", "", main)
    if k:
        for m in re.finditer(re.escape(k), flat):
            if flat[m.start(): m.start() + 60].count(k) >= 3:
                issues.append("메인 키워드가 좁은 구간에 3번 이상 몰림")
                break
    return issues


# ── 4. 최종 메시지 조립 + 슬랙 발송 ────────────────────────────────────────
def to_slack_bold(text):
    """마크다운 **굵게** 를 슬랙 표기 *굵게* 로 바꾼다 (슬랙에서 실제로 굵게 보이도록)."""
    return re.sub(r"\*\*([^*\n]+)\*\*", r"*\1*", text)


def render_photos(photos):
    """사진 컨셉을 보기 좋게 편다. 여러 줄짜리는 들여쓰기해서 붙인다."""
    out = []
    for i, p in enumerate(photos, 1):
        parts = p.split("\n")
        out.append(f"{i}. {parts[0]}")
        out.extend(f"    {extra}" for extra in parts[1:])
    return "\n".join(out)


def build_message(date_str, post, warnings=None, remaining=None, low_stock=5, round_no=1):
    """규칙서의 '출력 형식' 그대로 최종 메시지를 만든다."""
    subs = ", ".join(post["subs"]) if post["subs"] else "-"
    photo_lines = render_photos(post["photos"])
    msg = (
        f"📝 *마이비필라테스 블로그 글* ({date_str})\n"
        f"🔑 메인 키워드: {post['main']}\n"
        f"🏷️ 서브 키워드: {subs}\n"
        f"{LINE}\n\n"
        f"제목: {post['title']}\n\n"
        f"{to_slack_bold(post['body']).strip()}\n\n"
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
    if round_no >= 2:
        # 한 바퀴를 다 돌아 **다시 보내는 글**이다. 그대로 올리면 네이버에서 중복 문서로 본다.
        msg += (f"\n\n🔁 *{round_no}회차 — 전에 한 번 보낸 글입니다.*\n"
                f"그대로 올리지 마시고 도입부와 경험 문장만 새로 바꿔서 올려주세요.\n"
                f"새 글이 필요하면 클로드에게 \"필라테스 글 더 써줘\" 라고 부탁하세요.")
    elif remaining is not None and remaining <= low_stock:
        msg += (f"\n\n📦 새 글이 {remaining}편 남았습니다. "
                f"다 떨어지면 처음 글부터 다시 보내드립니다(내용은 같습니다).\n"
                f"새 글이 필요하면 클로드에게 \"필라테스 글 더 써줘\" 라고 부탁하세요.")
    return msg


def chunk(text, limit=3500):
    """슬랙 한 메시지 한도(4000자)를 넘지 않게 줄 단위로 쪼갠다.

    ⚠️ 한 줄 자체가 한도보다 길 수도 있다(줄바꿈 없이 긴 문단).
       그때는 글자 수로 잘라야 한다 — 안 그러면 슬랙이 `msg_too_long` 으로 거절한다.
    """
    parts, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
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


def http_post_json(url, headers, payload, timeout=30):
    """JSON 을 POST 하고 (상태코드, 응답문자열) 을 돌려준다. requests 없이 동작."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


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
            elif err in ("invalid_auth", "not_authed", "token_revoked"):
                print("   💡 SLACK_BOT_TOKEN_DEFAULT 토큰을 확인하세요.", file=sys.stderr)
            ok_all = False
        time.sleep(0.3)
    return ok_all


def slack_creds(args):
    """보낼 토큰과 채널을 정한다. 토큰이 없으면 (None, 채널)."""
    token = os.getenv("SLACK_BOT_TOKEN_DEFAULT") or os.getenv("SLACK_BOT_TOKEN")
    channel = args.channel or os.getenv("SLACK_ERRAND_CHANNEL") or DEFAULT_CHANNEL
    return token, channel


# ── 5. 메인 ────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="미리 써둔 마이비필라테스 블로그 글을 하루 한 편씩 슬랙 #심부름 으로 배달")
    ap.add_argument("--dry-run", action="store_true", help="배달하지 않고 화면에만 출력")
    ap.add_argument("--check", action="store_true", help="창고 전체를 규칙에 맞는지 검사")
    ap.add_argument("--list", action="store_true", help="창고 목록(보냄/안 보냄) 보기")
    ap.add_argument("--day", type=int, help="dayNN 로 시작하는 글을 지정해 배달")
    ap.add_argument("--file", help="특정 글 파일을 지정해 배달")
    ap.add_argument("--channel", help="보낼 슬랙 채널 ID")
    ap.add_argument("--posts-dir", default=POSTS_DIR, help="창고 폴더 경로")
    ap.add_argument("--reset", action="store_true", help="'보냄' 기록을 지운다(처음부터 다시)")
    ap.add_argument("--no-mark", action="store_true", help="보내되 '보냄' 기록은 남기지 않음")
    args = ap.parse_args(argv)

    load_env()
    posts_dir = args.posts_dir
    low_stock = int(os.getenv("PILATES_LOW_STOCK", "5"))
    today = datetime.now(KST).strftime("%Y-%m-%d")

    # --reset : 보냄 기록 비우기
    if args.reset:
        if os.path.isfile(SENT_FILE):
            os.remove(SENT_FILE)
            print(f"🧹 '보냄' 기록을 지웠습니다: {SENT_FILE}")
        else:
            print("ℹ️  지울 기록이 없습니다.")
        return 0

    files = list_post_files(posts_dir)
    sent = load_sent()

    # --list : 창고 목록
    if args.list:
        if not files:
            print(f"창고가 비어 있습니다: {posts_dir}")
            return 1
        counts = load_sent_counts()
        print(f"창고: {posts_dir}  (총 {len(files)}편, 보낸 적 있는 글 {len(sent)}편)")
        for f in files:
            post, err = read_post(f)
            n = counts.get(os.path.basename(f), 0)
            mark = f"✔ {n}번" if n else "· 대기"
            title = post["title"] if post else f"[형식 오류] {err}"
            print(f"  {mark}  {os.path.basename(f):<28} {title}")
        return 0

    # --check : 창고 전체 규칙 검사 (발송 없음)
    if args.check:
        if not files:
            print(f"❌ 창고가 비어 있습니다: {posts_dir}", file=sys.stderr)
            return 2
        bad = 0
        for f in files:
            post, err = read_post(f)
            name = os.path.basename(f)
            if not post:
                print(f"❌ {name}: {err}")
                bad += 1
                continue
            issues = validate(post)
            if issues:
                print(f"⚠️  {name} ({body_length(post['body'])}자)")
                for i in issues:
                    print(f"      - {i}")
                bad += 1
            else:
                print(f"✅ {name}  {body_length(post['body']):>4}자  {post['title']}")
        token, channel = slack_creds(args)
        print(f"\n총 {len(files)}편 / 문제 {bad}편 / 남은(안 보낸) 글 "
              f"{len([f for f in files if os.path.basename(f) not in sent])}편")
        print(f"슬랙 토큰 {'O' if token else 'X'} / 채널 {channel}")
        return 2 if bad else 0

    # ── 배달할 글 고르기 ───────────────────────────────────────────────────
    remaining, round_no = len(files), 1
    if args.file:
        target = args.file
        if not os.path.isfile(target):
            print(f"❌ 파일이 없습니다: {target}", file=sys.stderr)
            return 2
    elif args.day:
        matches = [f for f in files
                   if os.path.basename(f).startswith(f"day{args.day:02d}")]
        if not matches:
            print(f"❌ day{args.day:02d} 로 시작하는 글이 없습니다.", file=sys.stderr)
            return 2
        target = matches[0]
    else:
        target, remaining, round_no = pick_next(posts_dir)

    # 창고에 글 파일이 **하나도 없을 때만** 배달을 멈춘다.
    # (전부 보낸 경우에는 멈추지 않고 처음부터 다시 돈다 — pick_next 참고)
    if not target:
        print("ℹ️  창고에 글 파일이 하나도 없습니다.", file=sys.stderr)
        if not args.dry_run:
            token, channel = slack_creds(args)
            if token:
                post_to_slack(
                    f"📭 {today} 보낼 필라테스 블로그 글이 없습니다.\n"
                    f"클로드에게 \"필라테스 글 더 써줘\" 라고 부탁해 창고를 채워주세요.\n"
                    f"(창고: `{posts_dir}`)",
                    channel, token)
        return 1

    post, err = read_post(target)
    if not post:
        print(f"❌ {os.path.basename(target)} 형식 오류: {err}", file=sys.stderr)
        return 2

    warnings = validate(post)
    message = build_message(today, post, warnings, remaining, low_stock, round_no)

    if args.dry_run:
        print(f"── 배달할 글: {os.path.basename(target)} (발송 안 함) " + "─" * 12)
        print(message)
        if warnings:
            print("\n[점검] " + " / ".join(warnings), file=sys.stderr)
        return 0

    token, channel = slack_creds(args)
    if not token:
        print("❌ SLACK_BOT_TOKEN_DEFAULT(또는 SLACK_BOT_TOKEN)이 .env 에 없습니다.", file=sys.stderr)
        return 3
    if not post_to_slack(message, channel, token):
        return 3

    print(f"✅ 배달 완료 → {channel}  [{os.path.basename(target)}] {post['title']}")
    print(f"   {round_no}바퀴째 / 이번 바퀴에 남은 글 {max(remaining - 1, 0)}편")
    if warnings:
        print("   ⚠️ 점검 사항: " + " / ".join(warnings))
    if not args.no_mark:
        mark_sent({"date": today, "file": os.path.basename(target),
                   "title": post["title"], "main": post["main"],
                   "chars": body_length(post["body"]), "round": round_no,
                   "warnings": warnings})
    return 0


# 테스트에서 "명령줄로 부른 것처럼" 돌려보기 위한 이름 (test_pilates_blog.py 사용)
main_for_test = main


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # `... | head` 처럼 출력을 중간에 끊으면 나는 오류다. 잘못된 게 아니니 조용히 끝낸다.
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n중단했습니다.", file=sys.stderr)
        sys.exit(130)
