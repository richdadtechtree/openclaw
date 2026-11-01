#!/usr/bin/env python3
"""
test_mk_editorial.py — stock/mk_editorial.py(매일경제 사설 모으기) 오프라인 검사 (2026-10-20)

가짜 매경 서버를 띄워 확인한다(실제 사이트는 개발 환경에서 막혀 있음):
  ① 목록에서 'news/editorial/숫자' 링크 찾기(절대·상대 주소 모두)
  ② 글 모양 3가지 — og 메타+본문 상자 / JSON-LD 만 / 긴 <p> 만 — 모두 제목·시각·본문을 읽음
  ③ '그날 신문 사설' = 전날 낮 12시 ~ 당일 낮 12시 글만(이틀 전 글·다른 날 글 제외)
  ④ 저작권·기자 메일·광고 줄은 본문에서 뺀다
  ⑤ 캐시: 찾으면 파일에 저장, 다음엔 서버에 다시 안 감
  ⑥ 서버가 죽어 있어도 예외 없이 ok:false
실행: python3 scripts/test_mk_editorial.py
"""
import importlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "stock"))

BODY = "정부가 내놓은 부동산 대책은 공급 확대보다 수요 억제에 치우쳐 있다. " * 6
PAGES = {
    "/opinion/editorial/": '<a href="/news/editorial/12180001">a</a> <a href="https://www.mk.co.kr/news/editorial/12180002">b</a>'
                           ' <a href="//www.mk.co.kr/news/editorial/12179000">old</a> <a href="/news/economy/1">x</a>',
    # ① og 메타 + 본문 상자(news_cnt_detail_wrap) — 전날 저녁
    "/news/editorial/12180001": '''<html><head><meta property="og:title" content="[사설] 공급 없는 대책은 집값을 못 잡는다 - 매일경제">
      <meta property="article:published_time" content="2026-10-19T17:31:00+09:00"></head><body>
      <h2 class="news_ttl">공급 없는 대책</h2><div class="news_cnt_detail_wrap" itemprop="articleBody">
      <p>%s</p><p>둘째 문단입니다. 공급을 늘려야 한다.</p><figure><figcaption>사진설명 빼기</figcaption></figure>
      <p>ⓒ 매일경제 &amp; mk.co.kr, 무단 전재 및 재배포 금지</p></div></body></html>''' % BODY,
    # ② JSON-LD 만 — 당일 새벽
    "/news/editorial/12180002": '''<html><head><title>노동개혁 미룰 시간 없다 - 매일경제</title>
      <script type="application/ld+json">{"@type":"NewsArticle","headline":"노동개혁 미룰 시간 없다",
      "datePublished":"2026-10-20T05:00:00+09:00","articleBody":"%s\\n\\n노동시장 유연성을 높여야 한다."}</script></head><body></body></html>''' % BODY,
    # ③ 이틀 전 글(그날 사설이 아님) — 긴 <p> 만, '입력' 글자로 시각
    "/news/editorial/12179000": '''<html><head><title>지난 사설 - 매일경제</title></head><body><span>입력 : 2026-10-18 17:00</span>
      <p>%s</p><p>홍길동 기자 hong@mk.co.kr</p></body></html>''' % BODY,
}
# ── 한국경제(2026-11-01): RSS(사설만 [사설] 제목) + 글 화면(article-body/articletxt) + 403 으로 막힌 글 ──
HK_BODY = "반도체 보조금 경쟁에서 뒤처지면 산업 기반이 무너진다. " * 6
HK_RSS = """<?xml version="1.0" encoding="UTF-8"?><rss><channel>
  <item><title><![CDATA[[사설] 반도체 지원, 속도가 생명이다]]></title><link>https://www.hankyung.com/article/2026103171231</link>
    <pubDate>Fri, 30 Oct 2026 17:40:00 +0900</pubDate></item>
  <item><title><![CDATA[[사설] 막힌 글: 본문은 원문에서]]></title><link>https://www.hankyung.com/article/2026103171232</link>
    <pubDate>Fri, 30 Oct 2026 17:45:00 +0900</pubDate></item>
  <item><title><![CDATA[[천자칼럼] 사설 아님]]></title><link>https://www.hankyung.com/article/2026103171299</link>
    <pubDate>Fri, 30 Oct 2026 18:00:00 +0900</pubDate></item>
  <item><title><![CDATA[[사설] 지난 사설]]></title><link>https://www.hankyung.com/article/2026102871000</link>
    <pubDate>Wed, 28 Oct 2026 17:40:00 +0900</pubDate></item>
</channel></rss>"""
HK_ART = ('<html><head><meta property="og:title" content="[사설] 반도체 지원, 속도가 생명이다 | 한국경제">'
          '<meta property="article:published_time" content="2026-10-30T17:40:00+09:00"></head><body>'
          '<div class="article-body" id="articletxt">' + HK_BODY + '<br><br>지원 속도를 높여야 한다.<br>'
          'ⓒ 한국경제, 무단전재 및 재배포 금지</div></body></html>')
PAGES.update({"/feed/opinion": HK_RSS, "/article/2026103171231": HK_ART})
FORBID = {"/article/2026103171232"}                       # 한경이 봇을 403 으로 막는 경우
HITS = []


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        HITS.append(self.path)
        b = PAGES.get(self.path)
        if self.path in FORBID:
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200 if b else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write((b or "").encode("utf-8"))

    def log_message(self, *a):
        pass


def main():
    ok_all = True

    def check(ok, msg, extra=""):
        nonlocal ok_all
        ok_all &= bool(ok)
        print(("  ✅ " if ok else "  ❌ ") + msg + (("  " + str(extra)) if extra else ""))

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cache = tempfile.mkdtemp(prefix="mked-")
    os.environ["MK_BASE"] = "http://127.0.0.1:%d" % srv.server_port
    os.environ["MK_EDITORIAL_DIR"] = cache
    import mk_editorial as mk
    importlib.reload(mk)

    print("\n[① 링크 찾기]")
    ids = mk.find_links()
    check(ids[:3] == ["12180002", "12180001", "12179000"], "절대·상대·// 주소 모두 찾고 새 글 먼저, 다른 기사(economy)는 뺀다", ids)

    print("\n[② 글 모양 3가지]")
    a1, a2, a3 = mk.fetch_article("12180001"), mk.fetch_article("12180002"), mk.fetch_article("12179000")
    check(a1["title"] == "공급 없는 대책은 집값을 못 잡는다" and a1["published"].startswith("2026-10-19T17:31")
          and len(a1["paras"]) == 2, "og 메타 + 본문 상자: '[사설]'·'- 매일경제' 떼고 제목, 시각, 문단 2개", a1["title"])
    check(not any("사진설명" in p or "무단" in p for p in a1["paras"]), "사진 설명·저작권 줄은 본문에서 뺀다")
    check(a2["title"] == "노동개혁 미룰 시간 없다" and a2["published"].startswith("2026-10-20T05:00")
          and a2["paras"][-1] == "노동시장 유연성을 높여야 한다.", "JSON-LD 만 있는 글도 읽는다")
    check(a3["published"].startswith("2026-10-18T17:00") and not any("@" in p for p in a3["paras"]) and a3["chars"] > 150,
          "메타 없이 '입력 :' 글자·긴 <p> 만 있어도 읽고, 기자 메일 줄은 뺀다")

    print("\n[③ 그날 사설 고르기]")
    r = mk.get_editorials("2026-10-20")
    check(r["ok"] and [a["id"] for a in r["items"]] == ["12180001", "12180002"] and not r["stale"],
          "10-20 신문 사설 = 10-19 17:31 · 10-20 05:00 두 편(이틀 전 글 제외), 올라온 순서", [a["title"] for a in r["items"]])
    check(os.path.exists(os.path.join(cache, "2026-10-20.json")), "찾으면 캐시 파일에 저장")
    n = len(HITS)
    r2 = mk.get_editorials("2026-10-20")
    check(r2["items"] == r["items"] and len(HITS) == n, "두 번째는 서버에 다시 안 가고 캐시로", "요청 %d건 추가" % (len(HITS) - n))
    r3 = mk.get_editorials("2026-10-25")
    check(not r3["ok"] and r3["items"] == [] and not os.path.exists(os.path.join(cache, "2026-10-25.json")),
          "그날 사설이 없으면 지어내지 않고 빈 목록(캐시도 안 남김)", r3.get("error"))
    check(mk.get_editorials("10/20")["ok"] is False, "이상한 날짜는 거절")

    print("\n[⑦ 한국경제 사설 (2026-11-01)]")
    hkc = tempfile.mkdtemp(prefix="hked-")
    os.environ["HK_BASE"] = os.environ["MK_BASE"]
    os.environ["HK_EDITORIAL_DIR"] = hkc
    importlib.reload(mk)
    ids, meta = mk.hk_find_links()
    check(set(ids) == {"2026103171231", "2026103171232", "2026102871000"} and "2026103171299" not in ids,
          "RSS 에서 제목이 [사설] 인 글만(칼럼은 뺌)", ids)
    r = mk.get_editorials("2026-10-31", src="hk")
    got = {a["id"]: a for a in r["items"]}
    a = got.get("2026103171231") or {}
    check(r["ok"] and a.get("title") == "반도체 지원, 속도가 생명이다" and a.get("press") == "한국경제" and len(a.get("paras") or []) == 2
          and not any("무단" in p for p in a["paras"]), "한경 글: '[사설]'·'| 한국경제' 떼고 제목, 본문 상자(articletxt) 문단, press=한국경제", a)
    b = got.get("2026103171232") or {}
    check(b.get("no_body") and b.get("title") == "막힌 글: 본문은 원문에서" and b.get("paras") == [] and b.get("url", "").endswith("/article/2026103171232"),
          "403 으로 막힌 글은 RSS 제목·시각·링크만(본문 없음, 지어내지 않음)", b)
    check("2026102871000" not in got, "그날(10-30 낮 12시~10-31 낮 12시)이 아닌 지난 사설은 뺀다", list(got))
    check(os.path.exists(os.path.join(hkc, "2026-10-31.json")) and not os.path.exists(os.path.join(cache, "2026-10-31.json")),
          "한경 캐시는 따로(.hk_editorial)")
    allr = mk.get_all("2026-10-20")
    presses = [x["press"] for x in allr["items"]]
    check(allr["ok"] and presses[:2] == ["매일경제", "매일경제"] and allr["sources"]["hk"]["ok"] is False and allr["sources"]["mk"]["ok"],
          "두 신문 합치기: 한경이 없는 날도 매경은 보이고, 신문별 상태를 알려 줌", (presses, allr["sources"]["hk"].get("error")))
    allr2 = mk.get_all("2026-10-31")
    check(allr2["ok"] and set(x["press"] for x in allr2["items"]) == {"한국경제"}, "매경이 없는 날도 한경은 보임")

    print("\n[⑥ 서버가 죽었을 때]")
    srv.shutdown()
    os.environ["MK_BASE"] = "http://127.0.0.1:9"          # 아무도 없는 포트
    importlib.reload(mk)
    r4 = mk.get_editorials("2026-10-21", log=[])
    check(r4["ok"] is False and r4["items"] == [] and "링크" in r4["error"], "예외 없이 ok:false · '링크를 못 찾음'", r4["error"])

    print("\n총평: " + ("✅ 전부 통과" if ok_all else "❌ 실패 있음"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
