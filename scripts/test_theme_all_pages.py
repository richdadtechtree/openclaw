"""화이트/다크 모드가 메뉴의 모든 화면(신문 요약·시장 지수·경제 공부·AI 소식·챌린지)에 같은 계정 값으로 적용되는지 검사 (2026-11-09 사용자 요청).
실제 gate 쿠키/임시 SQLite 로 계정별 저장을 쓰고, 각 화면 HTML 은 gate.fill_page 를 거쳐 내준다(app.py 가 하는 그대로). 외부 호출 없음.
실행: python3 scripts/test_theme_all_pages.py   (fastapi + httpx 필요)"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="theme_pages_", ignore_cleanup_errors=True)
os.environ.update(GATE_DIR=TMP.name, OPENCLAW_ENV="/nonexistent", GATE_BASE_URL="https://example.test", GATE_APPROVAL="auto",
                  GATE_GOOGLE_CLIENT_ID="test", GATE_GOOGLE_CLIENT_SECRET="test", PRIVACY_OPERATOR="test",
                  PRIVACY_CONTACT="test@example.test", GATE_IP_ADMIN_PASSWORD="test-password-long-enough")
STOCK = Path(__file__).resolve().parents[1] / "stock"
sys.path.insert(0, str(STOCK))
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
import gate

# 맨 위 메뉴에 있는 화면들(주소 → HTML 파일). 서버 app.py 의 실제 대응과 같다.
PAGES = {"/economy": "slack_digest_live.html", "/market": "templates/index.html",
         "/dig": "dig_view.html", "/ai": "ai_view.html", "/challenge": "challenge_view.html"}


def make_app():
    a = FastAPI()
    gate.install(a)
    for path, fn in PAGES.items():
        def view(request: Request, _fn=fn):
            return HTMLResponse(gate.fill_page((STOCK / _fn).read_text(encoding="utf-8"), request))
        a.add_api_route(path, view, methods=["GET"], response_class=HTMLResponse)
    return a


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = make_app()
        cls.cl = {}
        for name in ("a", "b"):
            u = gate.upsert_login("google", name)
            gate.record_consent(u["id"], ["privacy"], name)
            gate.set_admin(u["id"], True)                  # 관리자는 모든 메뉴 화면을 본다(찰스 제한과 무관하게 검사)
            c = TestClient(cls.app, base_url="https://example.test")
            c.cookies.set("gate_sess", gate._session_token(u["id"]))
            cls.cl[name] = c

    def save(self, c, theme):
        r = c.post("/gate/theme", content='{"theme":"%s"}' % theme, headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 200)

    def test_every_page_has_the_account_theme_slot(self):
        """모든 화면 파일이 <head> 에 계정 화면 모드 자리표를 갖고 있다(없으면 그 화면만 계정 값을 못 받음)."""
        for path, fn in PAGES.items():
            html = (STOCK / fn).read_text(encoding="utf-8")
            head = html[: html.index("</head>")]
            self.assertIn("<!--GATE_THEME-->", head, "%s (%s) 에 자리표 없음" % (path, fn))

    def test_same_saved_value_reaches_every_page(self):
        for t in ("dark", "light", "auto"):
            self.save(self.cl["a"], t)
            for path in PAGES:
                r = self.cl["a"].get(path)
                self.assertEqual(r.status_code, 200, path)
                self.assertIn('window.__GATE_THEME="%s"' % t, r.text, "%s 에 %s 가 안 들어감" % (path, t))

    def test_accounts_are_independent(self):
        self.save(self.cl["a"], "dark")
        self.save(self.cl["b"], "light")
        for path in PAGES:
            self.assertIn('__GATE_THEME="dark"', self.cl["a"].get(path).text, path)
            self.assertIn('__GATE_THEME="light"', self.cl["b"].get(path).text, path)

    def test_market_resolves_auto_from_device(self):
        """시장 지수 화면은 data-theme 가 꼭 있어야 해서, 'auto' 일 땐 기기 설정을 읽어 정하는 코드가 자리표 바로 뒤에 있다."""
        html = (STOCK / "templates/index.html").read_text(encoding="utf-8")
        head = html[: html.index("</head>")]
        i, j = head.index("<!--GATE_THEME-->"), head.index("prefers-color-scheme")
        self.assertLess(i, j)
        self.assertLess(head.index('charset="UTF-8"'), i)             # charset 은 앞 1024바이트 안에 두고
        self.assertLess(head.index('charset="UTF-8"'), 1024)

    def test_market_toggle_saves_only_in_market(self):
        html = (STOCK / "templates/index.html").read_text(encoding="utf-8")
        self.assertIn("function saveThemeToAccount", html)
        self.assertIn("classList.contains('in-market')", html.split("function saveThemeToAccount")[1][:200])

    def test_dashboard_copies_are_identical(self):
        self.assertEqual((STOCK / "index.html").read_text(encoding="utf-8"), (STOCK / "templates/index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
