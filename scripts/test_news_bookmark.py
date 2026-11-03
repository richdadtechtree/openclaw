"""책갈피: 실제 로그인 쿠키·임시 SQLite로 계정 분리·최신 한 개 저장 검증."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="news_bookmark_", ignore_cleanup_errors=True)
os.environ.update(GATE_DIR=TMP.name, OPENCLAW_ENV="/nonexistent", GATE_BASE_URL="https://example.test",
                  GATE_APPROVAL="auto", GATE_GOOGLE_CLIENT_ID="test", GATE_GOOGLE_CLIENT_SECRET="test",
                  PRIVACY_OPERATOR="test", PRIVACY_CONTACT="test@example.test",
                  GATE_IP_ADMIN_PASSWORD="test-password-long-enough")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock"))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import gate
import news_bookmark as bm


def make_app():
    app = FastAPI()
    gate.install(app)
    bm.install(app)
    return app


class BookmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = make_app()
        cls.clients, cls.ids = {}, {}
        for name in ("reader", "other"):
            user = gate.upsert_login("google", name)
            gate.record_consent(user["id"], ["privacy"], name)
            c = TestClient(cls.app, base_url="https://example.test")
            c.cookies.set("gate_sess", gate._session_token(user["id"]))
            cls.clients[name], cls.ids[name] = c, user["id"]

    def setUp(self):
        with gate._db() as con:
            con.execute("DELETE FROM news_bookmarks")
        for uid in self.ids.values():
            gate.set_access(uid, "approved", None)
        self.c = self.clients["reader"]
        self.value = {"date": "2026-11-03", "edition": "paper", "view": "summary", "section": "feed",
                      "article": "신문 기사", "index": 2, "fraction": 0.3, "y": 1200, "page": ""}

    def get(self, c=None):
        return (c or self.c).get("/api/news/bookmark")

    def put(self, value=None, c=None, **extra):
        c = c or self.c
        csrf = self.get(c).json()["csrf"]
        return c.post("/api/news/bookmark", json={"bookmark": value or self.value, **extra},
                      headers={"x-csrf-token": csrf})

    def test_normal_reader_can_save(self):
        self.assertEqual(self.put().status_code, 200)
        self.assertEqual(self.get().json()["bookmark"], self.value)
        self.assertEqual(self.get().headers["cache-control"], "no-store")

    def test_latest_only_across_dates_and_editions(self):
        self.put()
        latest = dict(self.value, date="2026-11-02", edition="online", index=7)
        self.put(latest)
        with gate._db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM news_bookmarks WHERE owner=?", (self.ids["reader"],)).fetchone()[0], 1)
        self.assertEqual(self.get().json()["bookmark"], latest)

    def test_account_isolation_and_ignore_claimed_owner(self):
        self.put(owner=self.ids["other"])
        self.assertIsNone(self.get(self.clients["other"]).json()["bookmark"])
        other = dict(self.value, article="다른 계정")
        self.put(other, self.clients["other"])
        self.assertEqual(self.get().json()["bookmark"]["article"], "신문 기사")
        self.assertEqual(self.get(self.clients["other"]).json()["bookmark"]["article"], "다른 계정")

    def test_persists_in_fresh_client(self):
        self.put()
        with TestClient(make_app(), base_url="https://example.test") as c:
            c.cookies.update(self.c.cookies)
            self.assertEqual(self.get(c).json()["bookmark"], self.value)

    def test_clear_only_my_latest(self):
        self.put()
        self.put(c=self.clients["other"])
        r = self.c.post("/api/news/bookmark", json={"action": "clear"},
                        headers={"x-csrf-token": self.get().json()["csrf"]})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.get().json()["bookmark"])
        self.assertIsNotNone(self.get(self.clients["other"]).json()["bookmark"])

    def test_anonymous_and_blocked(self):
        with TestClient(self.app, base_url="https://example.test") as c:
            self.assertEqual(c.get("/api/news/bookmark").status_code, 401)
            self.assertEqual(c.post("/api/news/bookmark", json={}).status_code, 401)
        gate.set_status(self.ids["reader"], "blocked")
        self.assertEqual(self.get().status_code, 403)

    def test_expired(self):
        gate.set_access(self.ids["reader"], "approved", "2020-01-01")
        self.assertEqual(self.get().status_code, 403)

    def test_csrf_and_cross_site(self):
        self.assertEqual(self.c.post("/api/news/bookmark", json={"bookmark": self.value}).status_code, 403)
        self.assertEqual(self.c.post("/api/news/bookmark", json={"bookmark": self.value},
                                    headers={"x-csrf-token": self.get().json()["csrf"], "sec-fetch-site": "cross-site"}).status_code, 403)
        self.assertIsNone(self.get().json()["bookmark"])

    def test_invalid_body_preserves_previous(self):
        self.put()
        for k, v in (("date", "2026-02-30"), ("edition", "bad"), ("view", "bad"), ("section", "elsewhere"),
                     ("index", True), ("fraction", 2), ("fraction", float("inf")), ("y", -1),
                     ("article", "x" * 301)):
            if k == "fraction" and v == float("inf"):
                continue  # HTTP JSON encoders reject infinity; validate directly below.
            self.assertEqual(self.put(dict(self.value, **{k: v})).status_code, 400)
        with self.assertRaises(ValueError):
            bm.validate(dict(self.value, fraction=float("nan")))
        self.assertEqual(self.get().json()["bookmark"], self.value)

    def test_page_bookmark_and_path_validation(self):
        page = dict(self.value, view="page", page="03.jpg")
        self.assertEqual(self.put(page).status_code, 200)
        self.assertEqual(self.get().json()["bookmark"]["page"], "03.jpg")
        self.assertEqual(self.put(dict(page, page="../03.jpg")).status_code, 400)
        self.assertEqual(self.put(dict(page, edition="online")).status_code, 400)

    def test_size_limit(self):
        self.assertEqual(self.c.post("/api/news/bookmark", content="x" * 5000,
                        headers={"content-type": "application/json", "x-csrf-token": self.get().json()["csrf"]}).status_code, 413)

    def test_deleting_account_removes_bookmark(self):
        user = gate.upsert_login("google", "temporary")
        gate.record_consent(user["id"], ["privacy"], "temporary")
        with TestClient(self.app, base_url="https://example.test") as c:
            c.cookies.set("gate_sess", gate._session_token(user["id"]))
            self.put(c=c)
            gate.delete_user(user["id"])
        with gate._db() as con:
            self.assertIsNone(con.execute("SELECT 1 FROM news_bookmarks WHERE owner=?", (user["id"],)).fetchone())

    def test_ip_admin_has_separate_bookmark(self):
        self.put()
        with TestClient(self.app, base_url="https://127.0.0.1") as c:
            c.cookies.set(gate.COOKIE_IPADM, gate._sign({"k": "ipadm", "v": gate._ipadm_ver()}, 3600))
            self.assertIsNone(self.get(c).json()["bookmark"])
            self.assertEqual(self.put(dict(self.value, article="IP 관리자"), c).status_code, 200)
        self.assertEqual(self.get().json()["bookmark"]["article"], "신문 기사")


if __name__ == "__main__":
    unittest.main()
