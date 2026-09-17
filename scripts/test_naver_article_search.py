#!/usr/bin/env python3
"""
test_naver_article_search.py — 네이버 링크 찾기 자가 점검 (네트워크·키 불필요)

진짜 네이버에 접속하지 않고, **가짜 네이버 API 서버**를 내 컴퓨터에 띄워서
"제목 → 가장 비슷한 매경·한경 기사" 고르기가 제대로 되는지 확인한다.

실행:  python3 scripts/test_naver_article_search.py
"""
import http.server
import json
import os
import socketserver
import sys
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import naver_article_search as N  # noqa: E402
import verify_article_url as V    # noqa: E402

# 네이버가 돌려주는 모양 그대로(제목에 <b> 강조태그가 섞여 온다)
ITEMS = [
    {"title": "<b>삼성전자</b>, 3조원 반도체 투자 결정",
     "originallink": "https://www.mk.co.kr/news/stock/12345678",
     "link": "https://n.news.naver.com/mnews/article/009/0005"},
    {"title": "전세대출 규제 강화…실수요자 숨통",
     "originallink": "https://www.hankyung.com/article/2026091712345",
     "link": "https://n.news.naver.com/mnews/article/015/0004"},
    {"title": "가을 전시회 추천 10선",
     "originallink": "https://www.mk.co.kr/news/culture/99999999",
     "link": "https://n.news.naver.com/mnews/article/009/0003"},
    {"title": "삼성전자 투자 소식 종합",                       # 다른 신문사 → 후보에서 빠져야 함
     "originallink": "https://www.chosun.com/economy/1",
     "link": "https://n.news.naver.com/mnews/article/023/0001"},
]

OPENS = set()        # 여기 담긴 주소만 '열리는' 것으로 친다


class _Api(http.server.BaseHTTPRequestHandler):
    def do_GET(self):                                     # noqa: N802
        if self.path.startswith("/v1/search/news.json"):
            if self.headers.get("X-Naver-Client-Id") != "testid":
                self.send_error(401)
                return
            body = json.dumps({"items": ITEMS}, ensure_ascii=False).encode()
        elif self.path in OPENS:                          # 원문이 열리는 경우
            body = b"<html><head><title>ok</title></head><body>ok</body></html>"
        else:
            self.send_error(403)                          # 한경처럼 막힌 경우
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestNaverSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = socketserver.TCPServer(("127.0.0.1", 0), _Api)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        N.API = base + "/v1/search/news.json"
        os.environ["NAVER_CLIENT_ID"] = "testid"
        os.environ["NAVER_CLIENT_SECRET"] = "testsecret"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_가장_비슷한_기사를_고른다(self):
        r = N.search_best("삼성전자, 3조원 반도체 투자 결정", check_open=False)
        self.assertTrue(r["found"], r)
        self.assertEqual(r["outlet"], "매일경제")
        self.assertIn("mk.co.kr/news/stock/12345678", r["link"])
        self.assertGreater(r["score"], 0.9)

    def test_한국경제도_찾는다(self):
        r = N.search_best("전세대출 규제 강화", check_open=False)
        self.assertTrue(r["found"], r)
        self.assertEqual(r["outlet"], "한국경제")

    def test_매경한경이_아니면_후보에서_뺀다(self):
        r = N.search_best("삼성전자 투자 소식 종합", check_open=False)
        for c in r["candidates"]:
            self.assertIn(c["outlet"], ("매일경제", "한국경제"))
            self.assertNotIn("chosun", c["origin_url"])

    def test_비슷한_기사가_없으면_링크를_주지_않는다(self):
        r = N.search_best("국제 유가 급등 중동 정세 불안 확산", check_open=False)
        self.assertFalse(r["found"], r)
        self.assertEqual(r["link"], "")          # 지어내지 않는다
        self.assertIn("비슷하지 않", r["reason"])

    def test_한_매체로_한정할_수_있다(self):
        r = N.search_best("삼성전자, 3조원 반도체 투자 결정",
                          outlets=("한국경제",), check_open=False)
        self.assertFalse(r["found"], r)          # 매경 기사뿐이라 한경으론 못 찾는다

    def test_원문이_막히면_네이버_링크로_돌아간다(self):
        """한국경제 403 상황 — 원문이 안 열리면 네이버 링크를 쓴다."""
        r = N.search_best("전세대출 규제 강화", check_open=True)
        self.assertTrue(r["found"], r)
        self.assertIn("n.news.naver.com", r["link"])      # 우회로로 바뀌었다
        self.assertIn("hankyung.com", r["origin_url"])    # 원문 주소는 그대로 보관
        self.assertIn("원문이 안 열려", r["reason"])

    def test_키가_없으면_조용히_실패한다(self):
        cid = os.environ.pop("NAVER_CLIENT_ID")
        try:
            r = N.search_best("아무 제목", check_open=False)
            self.assertFalse(r["found"])
            self.assertIn("NAVER_CLIENT_ID", r["reason"])
        finally:
            os.environ["NAVER_CLIENT_ID"] = cid


if __name__ == "__main__":
    unittest.main(verbosity=2)
