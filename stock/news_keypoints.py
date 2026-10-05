"""
신문 요약에서 '🔍 오늘 신문에서 반드시 연결해서 봐야 할 5가지' 묶음만 뽑아내는 도구 (2026-10-06).

왜 필요한가
  GPT 가 슬랙(#gpt)에 올리는 신문 요약의 마지막에는 그날 핵심을 묶은 'N가지' 목록이 온다.
  주가 대시보드(첫 화면)에도 이 부분만 보여주려고, 긴 요약 글에서 그 묶음만 골라낸다.

어떻게 고르나
  1) 줄 하나에 "…N가지"(5가지·다섯 가지 등)가 있고, 그 뒤(같은 줄이나 다음 줄)에 번호 "1." 이 와야 머리말로 본다.
     → "3가지 이유로 올랐다" 같은 평범한 문장은 번호 1 이 안 따라와서 걸리지 않는다.
  2) 번호는 1→2→3… **순서대로** 이어질 때만 새 항목으로 자른다. "3.5%" "1. 5배" 같은 숫자는 오인하지 않는다.
  3) 번호가 없는 줄은 바로 위 항목의 '설명'으로 붙인다.
  4) 불릿(•)·JSON·코드블록·안내문(검증:/※) 이 나오면 목록이 끝난 것으로 본다.

외부 라이브러리 없음(표준 라이브러리만). 확인: python3 scripts/test_news_keypoints.py
"""
import re

# 슬랙 :emoji_code: 중 머리말에 자주 오는 것만 실제 이모지로. 나머지 코드는 지운다(화면에 ':xxx:' 가 남지 않게).
_EMOJI = {
    "mag": "🔍", "mag_right": "🔎", "pushpin": "📌", "newspaper": "📰", "bulb": "💡",
    "white_check_mark": "✅", "red_circle": "🔴", "dart": "🎯", "link": "🔗", "memo": "📝",
}

_NUM_WORD = r"(?:\d{1,2}|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)"
# "…5가지" 로 끝나는 머리말 + (같은 줄에 이어 붙은) 나머지
_HEAD_RE = re.compile(r"^(?P<head>.{2,80}?" + _NUM_WORD + r"\s*가지)\s*[:：]?\s*(?P<rest>.*)$")
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
# 목록이 끝났다고 볼 줄: 불릿, JSON/코드블록, 안내문
_END_RE = re.compile(r"^(?:[•·▪◦]|-\s|```|\{|검증\s*[:：]|※|＊|⚠)")


def _slack_decode(s):
    # 슬랙은 & < > 를 &amp; &lt; &gt; 로 보낸다. &amp; 는 마지막에 풀어야 '&lt;' 글자를 보존한다.
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _clean_line(s):
    s = _slack_decode(s)
    s = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", s)          # <링크|글자> → 글자
    s = re.sub(r"<(https?://[^>]+)>", r"\1", s)
    s = re.sub(r":([a-z0-9_+-]{2,30}):", lambda m: _EMOJI.get(m.group(1), ""), s)
    s = s.replace("*", "")                                          # 슬랙 굵게 표시
    s = re.sub(r"(^|\s)_(\S[^_]*?)_(?=\s|$)", r"\1\2", s)            # 슬랙 기울임 표시
    return s.strip()


def _circled_to_num(s):
    # "① 주택…" → "1. 주택…" (번호 판정을 하나로 통일)
    return re.sub("(^|\\s)([" + _CIRCLED + "])\\s*",
                  lambda m: "%s%d. " % (m.group(1), _CIRCLED.index(m.group(2)) + 1), s)


def _split_numbered(text, start):
    """'1. 가 2. 나 3. 다' 를 순서 번호(start, start+1, …)가 나올 때만 잘라 [(번호, 글)] 로.
    맨 앞이 start 번호가 아니면 ([], 원문) 을 돌려준다."""
    parts, pos, n = [], 0, start
    m = re.match(r"^%d\s*[.)]\s+" % n, text)
    if not m:
        return [], text
    pos = m.end()
    while True:
        nxt = re.compile(r"(?:^|\s)%d\s*[.)]\s+" % (n + 1)).search(text, pos)
        if not nxt:
            parts.append((n, text[pos:].strip()))
            return parts, ""
        parts.append((n, text[pos:nxt.start()].strip()))
        pos, n = nxt.end(), n + 1


def extract_keypoints(text):
    """요약 글 하나 → {"title": 머리말, "items": [{"n":1, "text":…, "notes":[…]}, …]} / 없으면 None."""
    if not text:
        return None
    lines = [_circled_to_num(_clean_line(l)) for l in text.replace("\r", "").split("\n")]

    for i, line in enumerate(lines):
        m = _HEAD_RE.match(line)
        if not m:
            continue
        head, rest = m.group("head").strip(), m.group("rest").strip()
        # 머리말 바로 뒤(같은 줄 or 다음 내용 줄)가 "1." 로 시작해야 진짜 목록 머리말
        follow = rest or next((l for l in lines[i + 1:] if l), "")
        if not re.match(r"^1\s*[.)]\s+", follow):
            continue

        items = []
        todo = ([rest] if rest else []) + lines[i + 1:]
        for raw in todo:
            if not raw:
                continue
            if _END_RE.match(raw):
                break
            parts, leftover = _split_numbered(raw, len(items) + 1)
            if parts:
                for n, t in parts:
                    items.append({"n": n, "text": t, "notes": []})
            elif items:
                items[-1]["notes"].append(leftover)               # 번호 없는 줄 = 위 항목 설명
            else:
                break
        if items:
            return {"title": head, "items": items}
    return None


def latest_keypoints(messages):
    """메시지 목록(오래된→새 순) 중 **가장 나중에 올라온** 'N가지' 묶음을 고른다(GPT 재전송 대비)."""
    for msg in sorted(messages or [], key=lambda m: m.get("ts") or "", reverse=True):
        kp = extract_keypoints(msg.get("text") or "")
        if kp:
            kp["ts"] = msg.get("ts") or ""
            return kp
    return None
