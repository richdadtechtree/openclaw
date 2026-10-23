"""매일경제 '디그(Dig)' 경제 뉴스레터(Gmail) → 웹 열람용 데이터 (2026-10-23 사용자 요청).

흐름
  Gmail(IMAP) ──fetch──▶ 메일 HTML ──parse──▶ 블록 목록(제목·소제목·문단·사진·3줄요약) ──▶ ~/.openclaw/dig_cache/<날짜>.json
  웹(/dig) 은 이 캐시 JSON 만 읽는다 → Gmail 이 느리거나 끊겨도 화면은 멀쩡하다.

규칙
  * 표준 라이브러리만 쓴다(시스템 python3 로도 돈다, requests 불필요).
  * 메일에 **적혀 있는 글만** 옮긴다. 요약·창작·추측 없음(AI 미사용).
  * 비밀번호는 코드에 쓰지 않는다 → .env 의 DIG_GMAIL_USER / DIG_GMAIL_APP_PASSWORD.

사용
  python3 dig_mail.py                    # 최근 60일 새 메일 가져와 캐시 (cron 용, 이미 받은 호는 건너뜀)
  python3 dig_mail.py --days 365         # 더 먼 과거까지(처음 한 번 채우기)
  python3 dig_mail.py --from-html 파일    # 서버 없이 HTML 파일로 파서만 시험(JSON 출력)
  python3 dig_mail.py --list             # 캐시된 목록
"""
import base64
import email
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

KST = timezone(timedelta(hours=9))
CACHE_DIR = os.path.expanduser(os.getenv("DIG_CACHE_DIR", "~/.openclaw/dig_cache"))
DIG_SENDER = os.getenv("DIG_SENDER", "dig@mk.co.kr")
DEFAULT_DAYS = int(os.getenv("DIG_DAYS", "60"))        # 자동 수집이 되돌아보는 기간(서버가 한동안 멈춰도 빠진 호를 메움)

# 본문이 아닌 링크(공유·구독·앱 설치·설문 등)는 화면에 링크로 안 살린다.
_JUNK_HOSTS = ("facebook.com", "twitter.com", "x.com", "play.google.com", "apps.apple.com",
               "docs.google.com", "page.stibee.com", "stib.ee")
_JUNK_TEXT = ("크게보기", "공유하기", "구독하기")


# ───────────────────────── HTML → 블록 ─────────────────────────
_VOID = {"br", "img", "meta", "link", "hr", "input", "col", "area", "base", "wbr"}
_LINEBREAK = {"div", "p", "br", "tr", "td", "table", "li", "h1", "h2", "h3", "h4", "ul", "ol"}


def _decode_stibee(url):
    """스티비 추적 링크(event.stibee.com/v2/click/<a>/<b64(실제주소)>) → 실제 주소. 못 풀면 ''."""
    try:
        u = urlparse(url)
        if not u.netloc.endswith("stibee.com") or "/click/" not in u.path:
            return url
        seg = u.path.rstrip("/").split("/")[-1]
        seg += "=" * (-len(seg) % 4)
        real = base64.urlsafe_b64decode(seg).decode("utf-8", "replace")
        return real if real.startswith(("http://", "https://")) else ""
    except Exception:
        return ""


def _good_link(url, text):
    if not url or any(j in text for j in _JUNK_TEXT):
        return ""
    host = (urlparse(url).netloc or "").lower()
    if any(host == j or host.endswith("." + j) for j in _JUNK_HOSTS):
        return ""
    return url


def _style_val(style, prop):
    m = re.search(r"(?:^|;)\s*" + re.escape(prop) + r"\s*:\s*([^;]+)", style or "", re.I)
    return m.group(1).strip() if m else ""


class _Walker(HTMLParser):
    """메일 HTML 을 '줄(run 목록)'과 '이미지' 의 순서열로 바꾼다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []        # [{tag,size,bold,color,href,hidden,skip}]
        self.items = []        # ("line", [run...]) | ("img", {src,alt})
        self.cur = []          # 지금 쓰는 줄의 run: (text,size,bold,color,href)
        self.hidden_text = []  # display:none 머리글(해시태그 줄)

    def _top(self):
        return self.stack[-1] if self.stack else {"size": 16, "bold": False, "color": "", "href": "",
                                                  "hidden": False, "skip": False}

    def flush(self):
        runs = [r for r in self.cur if r[0]]
        self.cur = []
        if any(r[0].strip() for r in runs):
            self.items.append(("line", runs))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _LINEBREAK:
            self.flush()
        if tag == "img":
            w, h = (a.get("width") or "").strip(), (a.get("height") or "").strip()
            src = a.get("src") or ""
            if src and w != "0" and h != "0" and "/v2/open" not in src and "/editor/icon" not in src:
                self.flush()
                self.items.append(("img", {"src": src, "alt": a.get("alt") or ""}))
            return
        if tag in _VOID:
            return
        top = self._top()
        style = a.get("style") or ""
        size = top["size"]
        m = re.match(r"(\d+(?:\.\d+)?)px", _style_val(style, "font-size"))
        if m:
            size = float(m.group(1))
        bold = top["bold"] or tag in ("b", "strong") or \
            _style_val(style, "font-weight").lower() in ("bold", "700", "800", "900")
        color = _style_val(style, "color") or top["color"]
        href = a.get("href") if tag == "a" else top["href"]
        hidden = top["hidden"] or "display:none" in style.replace(" ", "").lower()
        skip = top["skip"] or tag in ("style", "script", "head", "title")
        self.stack.append({"tag": tag, "size": size, "bold": bold, "color": color, "href": href or "",
                           "hidden": hidden, "skip": skip})

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if tag in _LINEBREAK:
            self.flush()
        for i in range(len(self.stack) - 1, -1, -1):      # 짝 맞는 가장 가까운 열린 태그까지 닫기
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        t = self._top()
        if t["skip"]:
            return
        if t["hidden"]:
            self.hidden_text.append(data)
            return
        data = re.sub(r"[ \t\r\n ​‌ ͏]+", " ", data)   # 스티비의 보이지 않는 공백 포함
        if data:
            self.cur.append((data, t["size"], t["bold"], t["color"], t["href"]))

    def close(self):
        super().close()
        self.flush()


def _runs_to_inline(runs):
    """줄의 run → 화면용 인라인 조각 [{t,b,a}] (b=굵게, a=링크). 같은 속성은 합친다."""
    out = []
    for text, _size, bold, _color, href in runs:
        link = ""
        if href:
            real = _decode_stibee(href)
            link = _good_link(real, text)
        piece = {"t": text}
        if bold:
            piece["b"] = 1
        if link:
            piece["a"] = link
        if out and {k: v for k, v in out[-1].items() if k != "t"} == {k: v for k, v in piece.items() if k != "t"}:
            out[-1]["t"] += text
        else:
            out.append(piece)
    if out:
        out[0]["t"] = out[0]["t"].lstrip()
        out[-1]["t"] = out[-1]["t"].rstrip()
    return [p for p in out if p["t"]]


def _plain(runs):
    return re.sub(r"\s+", " ", "".join(r[0] for r in runs)).strip()


def parse_digest(html):
    """메일 HTML → {tags, date_text, title, blocks}.

    blocks:  {"k":"sec","text":"오늘의 디깅"}            큰 구역 이름(오늘의 디깅 / 뉴스픽 / 3줄 요약)
             {"k":"title","text":...}                    기사(또는 뉴스픽 항목) 제목
             {"k":"h","text":...}                        본문 소제목
             {"k":"p","parts":[{t,b?,a?}]}               문단
             {"k":"img","src":...}  /  {"k":"cap",...}   사진 / 사진 설명
             {"k":"sum","text":...}                      3줄 요약 한 줄
    """
    w = _Walker()
    w.feed(html)
    w.close()

    tags = " ".join(re.findall(r"#[^\s#]+", " ".join(w.hidden_text)))
    blocks, date_text = [], ""
    group = []     # 연속된 '큰 글씨' 줄(구역 이름·┃·제목)
    in_summary = False   # '3줄 요약' 아래 줄들. 새 구역·제목이 나오면 풀린다(뉴스픽 문단과 구분)

    def flush_group():
        nonlocal group, in_summary
        if not group:
            return
        in_summary = False
        lines = [_plain(r) for r in group]
        group = []
        if "┃" in lines:                                   # [구역이름] ┃ [제목 줄들]
            i = lines.index("┃")
            sec = " ".join(l for l in lines[:i] if l)
            title = " ".join(l for l in lines[i + 1:] if l and l != "┃")
            if sec:
                blocks.append({"k": "sec", "text": sec})
            if title:
                blocks.append({"k": "title", "text": title})
        else:                                              # 본문 속 소제목
            for l in lines:
                if l:
                    blocks.append({"k": "h", "text": l})

    for kind, val in w.items:
        if kind == "img":
            flush_group()
            blocks.append({"k": "img", "src": val["src"]})
            continue
        runs = val
        text = _plain(runs)
        if not text:
            continue
        if any(j in text for j in _JUNK_TEXT) and len(text) < 40:    # '크게보기 공유하기 구독하기' 줄
            continue
        m = re.fullmatch(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*\(([월화수목금토일])\)", text)
        if m:
            flush_group()
            date_text = text
            continue
        size = max(r[1] for r in runs)
        if size >= 18:
            group.append(runs)
            continue
        flush_group()
        if text in ("게시하기", "게시", "좋아요"):            # 공유 버튼 글자
            continue
        if text == "웹에서 보기":                          # 이 아래는 광고 이미지·주소·수신거부 푸터
            break
        if text == "3줄 요약":
            in_summary = True
            blocks.append({"k": "sec", "text": text})
            continue
        if size <= 12.5 and not in_summary:
            blocks.append({"k": "cap", "text": text})
            continue
        if in_summary:
            if len(text) < 6:
                continue
            blocks.append({"k": "sum", "text": text})
            continue
        parts = _runs_to_inline(runs)
        if parts:
            blocks.append({"k": "p", "parts": parts})
    flush_group()

    first = next((i for i, b in enumerate(blocks) if b["k"] in ("sec", "title")), 0)
    blocks = blocks[first:]                                # 맨 위 로고 이미지 제거
    title = next((b["text"] for b in blocks if b["k"] == "title"), "")
    return {"tags": tags, "date_text": date_text, "title": title, "blocks": blocks}


# ───────────────────────── Gmail(IMAP) ─────────────────────────
def _hdr(msg, name):
    try:
        return str(make_header(decode_header(msg.get(name, "")))).strip()
    except Exception:
        return msg.get(name, "") or ""


def _html_of(msg):
    """MIME 메일에서 text/html 부분을 꺼낸다(문자셋 처리)."""
    best = ""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            cs = part.get_content_charset() or "utf-8"
            try:
                best = payload.decode(cs, "replace")
            except LookupError:
                best = payload.decode("utf-8", "replace")
            break
    return best


def issue_from_message(raw):
    """원본 메일 바이트 → 캐시에 저장할 dict. 디그 메일이 아니면 None."""
    msg = email.message_from_bytes(raw)
    html = _html_of(msg)
    if not html:
        return None
    sent = parsedate_to_datetime(msg["Date"]).astimezone(KST) if msg.get("Date") else datetime.now(KST)
    d = parse_digest(html)
    if not d["blocks"]:
        return None
    return {
        "id": sent.strftime("%Y-%m-%d"),
        "subject": _hdr(msg, "Subject"),
        "sent": sent.strftime("%Y-%m-%dT%H:%M:%S"),
        "message_id": (msg.get("Message-ID") or "").strip(),
        "fetched": datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S"),
        **d,
    }


def save_issue(issue):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, issue["id"] + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)             # 쓰는 도중에 웹이 읽어도 깨진 파일을 보지 않게
    return path


def fetch_new(days=DEFAULT_DAYS, user=None, password=None):
    """Gmail 에서 최근 N일 디그 메일을 받아 캐시. 반환: (저장한 날짜 목록, 건너뛴 개수)."""
    user = user or os.getenv("DIG_GMAIL_USER", "")
    password = (password or os.getenv("DIG_GMAIL_APP_PASSWORD", "")).replace(" ", "")
    if not user or not password:
        raise RuntimeError("DIG_GMAIL_USER / DIG_GMAIL_APP_PASSWORD 가 .env 에 없습니다")
    since = (datetime.now(KST) - timedelta(days=days)).strftime("%d-%b-%Y")
    saved, skipped = [], 0
    with imaplib.IMAP4_SSL("imap.gmail.com", timeout=30) as im:
        im.login(user, password)
        im.select("INBOX", readonly=True)              # 읽기 전용 — 메일을 '읽음' 처리하지 않는다
        typ, data = im.search(None, "FROM", '"%s"' % DIG_SENDER, "SINCE", since)
        if typ != "OK":
            raise RuntimeError("IMAP 검색 실패: %s" % typ)
        for num in data[0].split():
            typ, parts = im.fetch(num, "(BODY.PEEK[])")
            if typ != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            issue = issue_from_message(parts[0][1])
            if not issue:
                skipped += 1
                continue
            if os.path.isfile(os.path.join(CACHE_DIR, issue["id"] + ".json")):
                try:                                    # 같은 메일이면 다시 안 쓴다
                    with open(os.path.join(CACHE_DIR, issue["id"] + ".json"), encoding="utf-8") as f:
                        if json.load(f).get("message_id") == issue["message_id"]:
                            continue
                except Exception:
                    pass
            save_issue(issue)
            saved.append(issue["id"])
    return saved, skipped


# ───────────────────────── 웹이 쓰는 읽기 함수 ─────────────────────────
_ID_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def list_issues():
    """최신순 [{id,title,tags,date_text}]."""
    out = []
    try:
        names = sorted(os.listdir(CACHE_DIR), reverse=True)
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json") or not _ID_RE.fullmatch(n[:-5]):
            continue
        try:
            with open(os.path.join(CACHE_DIR, n), encoding="utf-8") as f:
                d = json.load(f)
            out.append({"id": d["id"], "title": d.get("title", ""), "tags": d.get("tags", ""),
                        "date_text": d.get("date_text", "")})
        except Exception:
            continue
    return out


def get_issue(issue_id):
    if not _ID_RE.fullmatch(issue_id or ""):            # 경로 조작 방지: 날짜 모양만 허용
        return None
    try:
        with open(os.path.join(CACHE_DIR, issue_id + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_env():
    """~/.openclaw/.env 의 KEY=VALUE 를 환경변수로(이미 있는 값은 덮지 않음).
    시스템 python3 에는 python-dotenv 가 없을 수 있어 직접 읽는다."""
    path = os.path.expanduser(os.getenv("OPENCLAW_ENV", "~/.openclaw/.env"))
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.replace("export ", "").strip()
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))
    except OSError:
        pass


def main(argv):
    if "--from-html" in argv:
        with open(argv[argv.index("--from-html") + 1], encoding="utf-8") as f:
            print(json.dumps(parse_digest(f.read()), ensure_ascii=False, indent=1))
        return 0
    if "--list" in argv:
        for i in list_issues():
            print(i["id"], i["title"], i["tags"])
        return 0
    _load_env()
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else DEFAULT_DAYS
    try:
        saved, skipped = fetch_new(days)
    except Exception as e:
        print("[dig] 실패: %s" % e, file=sys.stderr)
        return 1
    print("[dig] 새로 저장 %d개 %s, 건너뜀 %d" % (len(saved), saved, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
