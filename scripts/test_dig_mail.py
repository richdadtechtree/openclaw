#!/usr/bin/env python3
"""디그 뉴스레터 파서·캐시 검사 (오프라인, 표준 라이브러리만).

실제 메일 대신 **같은 구조의 가짜 HTML**(스티비 메일 모양)을 쓴다 → 저작권 있는 본문을 리포에 안 넣는다.
실행: python3 scripts/test_dig_mail.py
"""
import base64
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["DIG_CACHE_DIR"] = tempfile.mkdtemp(prefix="digtest_")
sys.path.insert(0, os.path.join(ROOT, "stock"))
import dig_mail as d  # noqa: E402

fails = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        fails.append(name)


def click(url):
    """스티비 추적 링크 흉내: .../v2/click/<id>/<base64url(실제주소)>"""
    b = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return "https://event.stibee.com/v2/click/AAA/" + b


BIG = 'style="font-size: 18px; font-weight: bold; color: #348ce4;"'
HTML = f"""<html><head><style>.x{{color:red}}</style></head><body>
<div style="display:none;max-height:0">#금리 #환율</div>
<img src="https://event.stibee.com/v2/open/XYZ" width=0 height=0>
<img src="https://img2.stibee.com/logo.png">
<div><a href="{click('https://example.com/share')}">크게보기</a> 공유하기 구독하기</div>
<div>2026.10.23(금)</div>
<div><span {BIG}>오늘의 디깅</span></div><div><span {BIG}>┃</span></div>
<div><span {BIG}>금리가 오르면</span></div><div><span {BIG}>무슨 일이?</span></div>
<div>첫 문단이에요. <span style="font-weight: bold;">굵은 부분</span> 뒤 글.</div>
<div><br></div>
<div><span {BIG}>소제목 하나</span><br>소제목 아래 문단.</div>
<img src="https://img2.stibee.com/pic.jpg">
<p><span style="font-size: 12px; color: #515151;">사진 설명. /사진=연합</span></p>
<div><span style="font-size:14px;font-weight:bold">3줄 요약</span></div>
<div>첫째 요약 문장입니다.</div><div>둘째 요약 문장입니다.</div>
<div><span {BIG}>뉴스픽</span></div><div><span {BIG}>┃</span></div>
<div><span {BIG}>환율 1400원 돌파</span></div>
<div>뉴스픽 본문이에요. <a href="{click('https://n.news.naver.com/mnews/article/009/1')}">원문 보기</a></div>
<div><a href="{click('https://www.facebook.com/sharer')}">게시하기</a></div>
<div>웹에서 보기</div>
<img src="https://img2.stibee.com/ad.png"><div>서울시 중구 주소</div><div>수신거부 Unsubscribe</div>
</body></html>"""

p = d.parse_digest(HTML)
b = p["blocks"]
kinds = [x["k"] for x in b]
text = lambda x: x.get("text") or "".join(s["t"] for s in x.get("parts", []))  # noqa: E731

print("[파서]")
check("해시태그(숨은 머리글)", p["tags"] == "#금리 #환율")
check("날짜 줄", p["date_text"] == "2026.10.23(금)")
check("제목은 ┃ 뒤 큰 글씨 줄을 합침", p["title"] == "금리가 오르면 무슨 일이?")
check("로고 이미지(첫 구역 앞)는 버림", b[0] == {"k": "sec", "text": "오늘의 디깅"})
check("구독·공유 줄 없음", not any("공유하기" in text(x) for x in b))
check("본문 굵은 글씨 보존", any(s.get("b") and s["t"] == "굵은 부분"
                       for x in b if x["k"] == "p" for s in x["parts"]))
check("소제목(h) 인식", {"k": "h", "text": "소제목 하나"} in b)
check("소제목 뒤 같은 칸 문단도 살림", any(x["k"] == "p" and "소제목 아래 문단" in text(x) for x in b))
check("사진 설명(cap) 인식", {"k": "cap", "text": "사진 설명. /사진=연합"} in b)
check("추적 픽셀(0x0) 이미지 제외", not any(x.get("src", "").endswith("/v2/open/XYZ") for x in b))
check("3줄 요약 2줄", kinds.count("sum") == 2)
check("뉴스픽 본문은 요약이 아니라 문단(p)", any(x["k"] == "p" and "뉴스픽 본문" in text(x) for x in b))
check("뉴스픽 제목", {"k": "title", "text": "환율 1400원 돌파"} in b)
check("스티비 추적 링크 → 실제 주소", any(s.get("a") == "https://n.news.naver.com/mnews/article/009/1"
                                 for x in b if x["k"] == "p" for s in x["parts"]))
check("'웹에서 보기' 아래 푸터·광고 제거", "수신거부" not in "".join(text(x) for x in b)
      and not any(x.get("src", "").endswith("ad.png") for x in b))
check("'게시하기' 공유 글자 제거", not any(text(x) == "게시하기" for x in b))

print("[링크 판정]")
check("공유 사이트는 링크로 안 살림", d._good_link("https://www.facebook.com/x", "게시") == "")
check("스티비 아닌 주소는 그대로", d._decode_stibee("https://example.com/a") == "https://example.com/a")
check("깨진 추적 주소는 빈 값", d._decode_stibee("https://event.stibee.com/v2/click/A/%%%") == "")

print("[캐시]")
d.save_issue({"id": "2026-10-23", "title": "t1", "tags": "#a", "date_text": "x", "blocks": []})
d.save_issue({"id": "2026-10-21", "title": "t0", "tags": "", "date_text": "y", "blocks": []})
check("목록은 최신순", [i["id"] for i in d.list_issues()] == ["2026-10-23", "2026-10-21"])
check("한 호 읽기", d.get_issue("2026-10-21")["title"] == "t0")
check("경로 조작 거부(../)", d.get_issue("../../etc/passwd") is None)
check("없는 날짜는 None", d.get_issue("1999-01-01") is None)

print("[메일 → 호]")
raw = ("From: dig@mk.co.kr\r\nTo: me@example.com\r\nSubject: =?utf-8?q?=ED=85=8C=EC=8A=A4=ED=8A=B8?=\r\n"
       "Date: Thu, 22 Oct 2026 21:07:34 +0000\r\nMessage-ID: <abc@x>\r\nMIME-Version: 1.0\r\n"
       "Content-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
       + base64.b64encode(HTML.encode()).decode() + "\r\n").encode()
iss = d.issue_from_message(raw)
check("보낸 시각(UTC 21:07) → 한국 날짜 10-23 로 저장", iss and iss["id"] == "2026-10-23")
check("제목 디코딩", iss and iss["subject"] == "테스트")
check("HTML 없는 메일은 None", d.issue_from_message(b"From: a@b\r\nSubject: x\r\n\r\nplain") is None)

print("\n결과:", "전부 통과" if not fails else "실패 %d개: %s" % (len(fails), fails))
sys.exit(1 if fails else 0)
