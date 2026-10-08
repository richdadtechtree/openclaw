#!/usr/bin/env python3
"""
mer_blog_slack.py — 메르님 네이버 블로그(ranto28) 새 글 → 슬랙 #메르의-가르침 (AI 미사용, 규칙 기반)

하는 일
  1) 블로그 RSS 에서 글 목록(제목·주소)을 읽는다.
  2) 아직 안 보낸 새 글마다 본문을 열어, 맨 끝의 '한줄평'을 뽑는다.
  3) 슬랙 채널에 "제목 + 한줄평 + 원문 링크" 를 보낸다.

원칙 (지어내기 금지)
  - 한줄평은 글에 **실제로 적힌 문장만** 쓴다. 요약·창작 안 함.
  - 한줄평 자리를 못 찾으면 → 제목+링크만 보내고 "한줄평을 찾지 못했다" 고 솔직히 적는다.
  - 본문을 못 열었으면(일시 오류) 바로 보내지 않고 다음 실행에서 다시 시도(최대 3번).

필요 (.env, openclaw 루트)
  SLACK_BOT_TOKEN      슬랙 봇 토큰 (chat:write). ⚠️ 봇을 #메르의-가르침 에 /invite 해야 함
  SLACK_MER_CHANNEL    #메르의-가르침 채널 ID (C...)

사용
  python3 mer_blog_slack.py              # 새 글만 보냄 (cron 이 10분마다 호출)
  python3 mer_blog_slack.py --dry-run    # 보내지 않고 화면에만 출력
  python3 mer_blog_slack.py --latest     # 가장 최근 글 1건을 지금 보냄 — 연결 시험용
  python3 mer_blog_slack.py --show URL   # 그 글에서 한줄평이 어떻게 뽑히는지만 확인 (슬랙 전송 없음)

표준 라이브러리만 사용 → 시스템 python3 로 그대로 실행됩니다 (venv 불필요).
첫 실행은 '기존 글 전부 읽음 처리'만 하고 아무것도 안 보냅니다(옛날 글 폭탄 방지).
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

BLOG_ID = "ranto28"
RSS_URL = f"https://rss.blog.naver.com/{BLOG_ID}.xml"
POST_URL = "https://blog.naver.com/PostView.naver?blogId={bid}&logNo={no}"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_TRIES = 3          # 본문을 못 열 때 다시 시도하는 최대 횟수 (넘으면 제목만 보냄)
MAX_ONELINER = 400     # 표지 없이 '마지막 문단'을 쓸 때만: 이보다 길면 본문 일부로 보고 버린다
MAX_MARKED = 1500      # '한줄 코멘트' 표지가 직접 붙은 문단은 길어도 그대로 쓴다(실제 글은 300~400자)
# '한줄평' 이라고 직접 적어둔 줄을 찾는 표지. (한줄평 / 한 줄 평 / 한줄 요약 / 한줄 정리 …)
MARKER = re.compile(r"한\s*줄\s*(평|요약|정리|코멘트|총평|결론)")


# ───────────────────────── 환경 / 상태 파일 ─────────────────────────
def load_env():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mer_seen.json")


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            st = json.load(f)
        st.setdefault("sent", [])
        st.setdefault("tries", {})
        return st
    except (OSError, ValueError):
        return {"sent": [], "tries": {}, "seeded": False}


def save_state(st):
    st["sent"] = st["sent"][-300:]  # 무한히 커지지 않게
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


# ───────────────────────── 네이버에서 가져오기 ─────────────────────────
def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, errors="replace")


def log_no(link):
    """글 주소에서 글 번호(logNo)를 뽑는다. .../ranto28/223456789 또는 ?logNo=223456789"""
    m = re.search(r"logNo=(\d+)", link) or re.search(r"/(\d{6,})(?:[/?#]|$)", link)
    return m.group(1) if m else None


def parse_rss(xml_text):
    """RSS 문자열 → [{no,title,link}] (최신순)."""
    root = ET.fromstring(xml_text.lstrip("﻿"))
    posts = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        no = log_no((it.findtext("link") or "").strip())
        if title and no:
            posts.append({"no": no, "title": title,
                          "link": f"https://blog.naver.com/{BLOG_ID}/{no}"})
    return posts


def fetch_posts():
    posts = parse_rss(http_get(RSS_URL))
    if not posts:
        raise RuntimeError("RSS 에서 글을 하나도 못 읽었습니다(주소/형식 변경 가능성).")
    return posts


# ───────────────────────── 본문 → 문단 → 한줄평 ─────────────────────────
class ParaParser(HTMLParser):
    """스마트에디터(se-main-container)의 문단을 순서대로 모은다.
    옛 에디터 글(postViewArea)이면 그 영역을 줄 단위로 모은다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paras = []
        self._buf = []
        self._main = 0     # se-main-container 안쪽 div 깊이
        self._old = 0      # postViewArea 안쪽 div 깊이
        self._skip = 0     # script/style 안쪽

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls, idv = a.get("class") or "", a.get("id") or ""
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "div":
            if self._main or "se-main-container" in cls:
                self._main += 1
            if self._old or idv == "postViewArea":
                self._old += 1
        if self._main or self._old:
            if tag == "br":
                self._buf.append("\n")
            elif tag in ("p", "li") or (tag == "div" and self._old):
                self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        if tag in ("p", "li"):
            self._flush()
        if tag == "div":
            if self._main:
                self._main -= 1
            if self._old:
                self._old -= 1
            self._flush()

    def handle_data(self, data):
        if not self._skip and (self._main or self._old):
            self._buf.append(data)

    def _flush(self):
        text, self._buf = "".join(self._buf), []
        for line in text.split("\n"):
            line = re.sub(r"[​ \s]+", " ", line).strip()
            if line:
                self.paras.append(line)


def parse_paragraphs(page_html):
    p = ParaParser()
    p.feed(page_html)
    p._flush()
    return p.paras


def pick_oneliner(paras):
    """문단 목록에서 한줄평을 고른다. → (문장 or None, 방식 'marker'|'last'|None)

    1순위: 뒤에서부터 '한줄평' 표지가 붙은 줄을 찾는다.
           표지 줄에 내용이 같이 있으면 그것, 표지만 있으면 바로 다음 줄.
    2순위: 표지가 없으면 글의 **마지막 문단**(짧을 때만). 해시태그·출처 줄은 건너뛴다.
    """
    for i in range(len(paras) - 1, -1, -1):
        line = paras[i]
        m = MARKER.search(line)
        if not m or len(line) > MAX_MARKED:
            continue
        tail = re.sub(r"^[\s\W_]*", "", line[m.end():]).strip()   # '평:' '평 -' 등 앞 기호 제거
        if tail:
            return tail, "marker"
        nxt = paras[i + 1] if i + 1 < len(paras) else ""     # 표지만 있으면 바로 다음 문단 하나
        if nxt and not nxt.startswith("#") and len(nxt) <= MAX_MARKED:
            return nxt, "marker"
    for line in reversed(paras):
        if re.fullmatch(r"(#\S+\s*)+", line) or re.match(r"^(출처|source|참고)\b", line, re.I):
            continue
        return (line, "last") if len(line) <= MAX_ONELINER else (None, None)
    return None, None


def fetch_oneliner(no):
    """본문을 열어 한줄평 추출. 열기 실패는 예외로 알린다(→ 재시도)."""
    paras = parse_paragraphs(http_get(POST_URL.format(bid=BLOG_ID, no=no)))
    if not paras:
        raise RuntimeError("본문 문단을 못 읽음(아직 로딩 전이거나 구조 변경).")
    return pick_oneliner(paras)


# ───────────────────────── 슬랙 ─────────────────────────
def slack_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(post, one, how):
    head = f"📚 *{slack_escape(post['title'])}*"
    if one:
        tag = "" if how == "marker" else "  _(글의 마지막 문장)_"
        body = f"💬 *한줄평*{tag}\n> {slack_escape(one)}"
    else:
        body = "_이 글에서 한줄평을 찾지 못했어요. 원문을 확인해 주세요._"
    return f"{head}\n{body}\n<{post['link']}|원문 보기>"


def slack_post(text):
    token, channel = os.getenv("SLACK_BOT_TOKEN"), os.getenv("SLACK_MER_CHANNEL")
    if not token or not channel:
        raise RuntimeError("SLACK_BOT_TOKEN / SLACK_MER_CHANNEL 이 .env 에 없습니다.")
    body = json.dumps({"channel": channel, "text": text,
                       "unfurl_links": False, "unfurl_media": False}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage", data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        hint = {"not_in_channel": " → 봇을 채널에 /invite 하세요",
                "channel_not_found": " → SLACK_MER_CHANNEL(채널 ID) 확인"}.get(res.get("error"), "")
        raise RuntimeError(f"슬랙 오류: {res.get('error')}{hint}")


# ───────────────────────── 메인 ─────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 출력만")
    ap.add_argument("--latest", action="store_true", help="가장 최근 글 1건을 지금 보냄(시험)")
    ap.add_argument("--show", metavar="URL", help="그 글의 한줄평 추출 결과만 확인")
    args = ap.parse_args()
    load_env()

    if args.show:
        one, how = fetch_oneliner(log_no(args.show) or args.show)
        print(f"방식={how}\n한줄평={one}")
        return 0 if one else 2

    try:
        posts = fetch_posts()
    except Exception as e:  # 네트워크/형식 변경 — 조용히 넘기지 않고 로그에 남김
        print(f"❌ 글 목록 읽기 실패: {e}", file=sys.stderr)
        return 1

    st = load_state()
    if args.latest:
        todo = posts[:1]
    elif not st.get("seeded"):
        st["sent"] = [p["no"] for p in posts]      # 첫 실행: 기존 글은 읽음 처리만
        st["seeded"] = True
        if not args.dry_run:
            save_state(st)
        print(f"첫 실행: 기존 글 {len(posts)}건을 읽음 처리했습니다. 이후 새 글부터 보냅니다.")
        return 0
    else:
        todo = [p for p in reversed(posts) if p["no"] not in st["sent"]]   # 오래된 것부터

    rc = 0
    for p in todo:
        tries = st["tries"].get(p["no"], 0)
        try:
            one, how = fetch_oneliner(p["no"])
        except Exception as e:
            if tries + 1 < MAX_TRIES and not args.latest:
                st["tries"][p["no"]] = tries + 1
                print(f"⏳ {p['title']} — 본문 열기 실패({e}). 다음 실행에서 재시도 ({tries + 1}/{MAX_TRIES})")
                continue
            one, how = None, None          # 끝내 못 열면 제목만이라도 보낸다
        msg = build_message(p, one, how)
        if args.dry_run:
            print(msg + "\n" + "-" * 40)
            continue
        try:
            slack_post(msg)
        except Exception as e:
            print(f"❌ 슬랙 전송 실패({p['title']}): {e}", file=sys.stderr)
            rc = 1
            break                          # 순서 유지: 실패한 글부터 다음에 다시
        if p["no"] not in st["sent"]:
            st["sent"].append(p["no"])
        st["tries"].pop(p["no"], None)
        print(f"✅ 전송: {p['title']} (한줄평: {how or '없음'})")
    if not args.dry_run:
        save_state(st)
    return rc


if __name__ == "__main__":
    sys.exit(main())
