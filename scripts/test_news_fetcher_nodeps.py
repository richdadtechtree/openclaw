#!/usr/bin/env python3
"""
test_news_fetcher_nodeps.py — 수집기가 **외부 라이브러리 없이도** 도는지 확인한다.

왜 이 테스트가 있나
-------------------
서버엔 파이썬이 여러 개다(시스템 python3, `.venv`, `newspaper/.venv` …).
어떤 것엔 `requests`·`bs4`·`feedparser` 가 있고 어떤 것엔 없다.
실제로 `.venv` 가 켜진 상태에서 돌렸다가 `ModuleNotFoundError: No module named 'bs4'`
로 멈춘 적이 있다. 그래서 세 라이브러리를 **일부러 없는 것처럼 만들고** 전체 흐름을 돌려본다.

가짜 신문사 서버를 내 컴퓨터에 띄우므로 **인터넷 없이** 실행된다.

실행:  python3 scripts/test_news_fetcher_nodeps.py
"""
import builtins
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 가짜 신문사 콘텐츠 ────────────────────────────────────────────────────
RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>삼성전자, 3조원 반도체 투자 결정</title>
<link>http://HOST/news/stock/12345678</link>
<pubDate>Wed, 17 Sep 2026 06:00:00 +0900</pubDate></item>
<item><title>오늘의 운세 2026년 9월 18일 金</title>
<link>http://HOST/news/culture/99999999</link>
<pubDate>Wed, 17 Sep 2026 05:00:00 +0900</pubDate></item>
<item><title>정부, 부동산 대책 발표</title>
<link>http://HOST/news/realestate/12345680</link>
<pubDate>Wed, 17 Sep 2026 04:00:00 +0900</pubDate></item>
</channel></rss>"""

# 정상 기사 — 본문 옆에 메뉴·관련기사가 붙어 있다(실제 신문사 페이지 구조)
ARTICLE_OK = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="삼성전자, 3조원 반도체 투자 결정">
<link rel="canonical" href="/news/stock/12345678"><title>x</title></head><body>
<nav class="gnb">메뉴 글자</nav>
<div class="news_cnt_detail_wrap"><p>삼성전자가 3조원 규모 투자를 결정했다.</p>
<p>내년부터 집행된다.</p></div>
<aside class="related_news">엉뚱한 관련기사 제목</aside></body></html>"""

# 링크는 멀쩡해 보이지만 열어 보면 다른 기사 — 반드시 걸러져야 한다
ARTICLE_WRONG = """<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="전혀 다른 기사입니다">
<link rel="canonical" href="/news/realestate/12345680"></head>
<body><p>다른 내용</p></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    hostport = ""

    def do_GET(self):                                    # noqa: N802
        if self.path.startswith("/rss"):
            body = RSS.replace("HOST", self.hostport).encode()
        elif self.path == "/news/stock/12345678":
            body = ARTICLE_OK.encode()
        elif self.path == "/news/realestate/12345680":
            body = ARTICLE_WRONG.encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestNoDeps(unittest.TestCase):
    """requests·bs4·feedparser 를 모두 없앤 채 수집기를 끝까지 돌린다."""

    @classmethod
    def setUpClass(cls):
        # 세 라이브러리를 '없는 것'으로 만든다 (import 가 실패하도록)
        cls._real_import = builtins.__import__

        def blocked(name, *a, **k):
            if name.split(".")[0] in ("requests", "bs4", "feedparser"):
                raise ImportError(f"No module named '{name}'")
            return cls._real_import(name, *a, **k)

        builtins.__import__ = blocked

        cls.srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        _Handler.hostport = f"127.0.0.1:{cls.srv.server_address[1]}"

        sys.path.insert(0, os.path.join(REPO, "workspace"))
        import news_fetcher as NF                                    # noqa: E402
        cls.NF = NF
        # 매체명을 '테스트신문' 으로 두면 mk/hankyung 도메인 검사를 타지 않는다
        NF.FEEDS = {"테스트신문": [f"http://{_Handler.hostport}/rss"]}
        NF.time.sleep = lambda *_: None                              # 테스트는 안 기다린다

        cls.outdir = tempfile.mkdtemp()
        orig_dirname = NF.os.path.dirname
        NF.os.path.dirname = (lambda p: cls.outdir
                              if str(p).endswith("news_fetcher.py") else orig_dirname(p))
        try:
            NF.main()
        except SystemExit:
            pass
        with open(os.path.join(cls.outdir, "news_data.json"), encoding="utf-8") as f:
            cls.data = json.load(f)

    @classmethod
    def tearDownClass(cls):
        builtins.__import__ = cls._real_import
        cls.srv.shutdown()

    def test_정상_기사는_통과한다(self):
        self.assertEqual(len(self.data["articles"]), 1, self.data)
        self.assertIn("삼성전자", self.data["articles"][0]["title"])

    def test_링크가_다른_기사면_버린다(self):
        reasons = [r["verify_reason"] for r in self.data["rejected"]]
        self.assertIn("title_mismatch", reasons, self.data["rejected"])

    def test_운세는_후보에도_안_오른다(self):
        self.assertNotIn("운세", json.dumps(self.data, ensure_ascii=False))

    def test_본문에_관련기사나_메뉴가_안_섞인다(self):
        content = self.data["articles"][0]["content"]
        self.assertIn("삼성전자가 3조원", content)
        self.assertIn("내년부터 집행", content)
        self.assertNotIn("엉뚱한 관련기사", content)   # ← 이게 섞이면 AI 가 딴 기사를 요약한다
        self.assertNotIn("메뉴 글자", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
