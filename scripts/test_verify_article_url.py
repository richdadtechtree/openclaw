#!/usr/bin/env python3
"""
test_verify_article_url.py — verify_article_url.py 자가 점검 (네트워크 불필요)

진짜 언론사 사이트에 접속하지 않고도 판정 논리를 확인할 수 있게,
**내 컴퓨터 안에 가짜 기사 페이지를 띄워** 놓고 검사한다.

실행:  python3 scripts/test_verify_article_url.py
"""
import http.server
import os
import socketserver
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_article_url as V  # noqa: E402


def page(title, canonical="", h1=""):
    """가짜 기사 페이지 HTML 한 장."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta property="og:title" content="{title}">
{f'<link rel="canonical" href="{canonical}">' if canonical else ''}
<title>{title} - 매일경제</title></head>
<body><h1>{h1 or title}</h1><p>본문</p></body></html>""".encode("utf-8")


class Handler(http.server.BaseHTTPRequestHandler):
    """가짜 언론사 서버. 주소마다 다른 상황을 흉내 낸다."""
    PAGES = {}          # 아래 setUpModule 에서 채운다

    def do_GET(self):                                   # noqa: N802
        if self.path == "/moved":                       # 다른 기사로 튕기는 주소
            self.send_response(302)
            self.send_header("Location", "/news/stock/99999999")
            self.end_headers()
            return
        body = self.PAGES.get(self.path)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):                          # 테스트 출력 조용히
        pass


SERVER = None
BASE = ""


def setUpModule():
    global SERVER, BASE
    Handler.PAGES = {
        # 제목이 정확히 같은 정상 기사
        "/news/stock/12345678": page("삼성전자, 3조원 규모 반도체 투자 결정",
                                     canonical="/news/stock/12345678"),
        # 페이지 제목이 RSS 제목보다 긴 경우(뒤에 설명이 붙음)
        "/news/realestate/12345679": page(
            "전세대출 규제 강화…실수요자 숨통 트이나 [부동산 돋보기]",
            canonical="/news/realestate/12345679"),
        # 완전히 다른 기사 (링크만 잘못 붙은 상황)
        "/news/culture/12345680": page("가을 전시회 추천 10선",
                                       canonical="/news/culture/12345680"),
        # 리다이렉트 도착지 — 기사 번호가 다르다
        "/news/stock/99999999": page("엉뚱한 다른 기사입니다",
                                     canonical="/news/stock/99999999"),
        # canonical 이 다른 기사 번호를 가리키는 위험한 페이지
        "/news/stock/11111111": page("제목은 같아 보이는 기사",
                                     canonical="/news/stock/22222222"),
    }
    SERVER = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    BASE = f"http://127.0.0.1:{SERVER.server_address[1]}"


def tearDownModule():
    if SERVER:
        SERVER.shutdown()


class TestNormalize(unittest.TestCase):
    """제목 다듬기 — 네트워크 없이 순수 계산만 확인."""

    def test_언론사_꼬리표와_괄호를_지운다(self):
        a = V.norm_title("[단독] 삼성전자, 3조 투자 - 매일경제")
        b = V.norm_title("삼성전자 3조 투자")
        self.assertIn("삼성전자", a)
        self.assertNotIn("매일경제", a)
        self.assertGreater(V.title_score("[단독] 삼성전자, 3조 투자 - 매일경제",
                                         "[단독] 삼성전자 3조 투자"), 0.9)

    def test_다른_기사는_점수가_낮다(self):
        self.assertLess(V.title_score("삼성전자 3조 투자", "가을 전시회 추천 10선"), 0.4)

    def test_기사번호_추출(self):
        self.assertEqual(V.article_id("https://www.mk.co.kr/news/stock/12129186"), "12129186")
        self.assertEqual(V.article_id("https://www.hankyung.com/article/2026091612345"),
                         "2026091612345")
        self.assertEqual(V.article_id("https://www.mk.co.kr/news/stock/"), "")


class TestRelay(unittest.TestCase):
    """구글뉴스 중계 주소 = 과거에 엉뚱한 기사를 띄운 주범. 열어보지도 않고 탈락."""

    def test_구글뉴스_링크는_무조건_탈락(self):
        r = V.verify("https://news.google.com/rss/articles/CBMiWkFVX3lxTE43",
                     "부부 공동명의 1주택자 종부세")
        self.assertFalse(r["verified"])
        self.assertEqual(r["reason"], "relay_link")

    def test_단축주소도_탈락(self):
        self.assertEqual(V.verify("https://bit.ly/abc", "제목")["reason"], "relay_link")


class TestLive(unittest.TestCase):
    """가짜 기사 서버를 실제로 열어 보고 판정."""

    def test_같은_기사면_통과(self):
        r = V.verify(f"{BASE}/news/stock/12345678", "삼성전자, 3조원 규모 반도체 투자 결정")
        self.assertTrue(r["verified"], r)
        self.assertIn(r["reason"], ("id_match", "title_match"))

    def test_제목이_조금_달라도_통과(self):
        r = V.verify(f"{BASE}/news/realestate/12345679", "전세대출 규제 강화")
        self.assertTrue(r["verified"], r)

    def test_엉뚱한_기사면_탈락(self):
        r = V.verify(f"{BASE}/news/culture/12345680", "삼성전자, 3조원 규모 반도체 투자 결정")
        self.assertFalse(r["verified"], r)
        self.assertEqual(r["reason"], "title_mismatch")
        self.assertEqual(r["page_title"], "가을 전시회 추천 10선")   # 왜 틀렸는지 보인다

    def test_다른_기사로_튕기면_탈락(self):
        r = V.verify(f"{BASE}/moved", "삼성전자, 3조원 규모 반도체 투자 결정")
        self.assertFalse(r["verified"], r)

    def test_canonical_이_다른_기사를_가리키면_탈락(self):
        r = V.verify(f"{BASE}/news/stock/11111111", "제목은 같아 보이는 기사")
        self.assertFalse(r["verified"], r)
        self.assertTrue(r["reason"].startswith("article_id_mismatch"), r)

    def test_없는_페이지는_탈락(self):
        r = V.verify(f"{BASE}/news/stock/00000000", "아무 제목")
        self.assertFalse(r["verified"])
        self.assertTrue(r["reason"].startswith("fetch_failed"), r)

    def test_언론사_도메인이_다르면_탈락(self):
        r = V.verify(f"{BASE}/news/stock/12345678",
                     "삼성전자, 3조원 규모 반도체 투자 결정", outlet="매일경제")
        self.assertFalse(r["verified"], r)
        self.assertTrue(r["reason"].startswith("host_mismatch"), r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
