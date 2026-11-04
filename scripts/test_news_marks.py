"""지면 표시 저장 API: 실제 gate 쿠키/임시 SQLite로 검사, 외부 호출 없음."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TMP = tempfile.TemporaryDirectory(prefix="news_marks_", ignore_cleanup_errors=True)
os.environ.update(GATE_DIR=TMP.name, OPENCLAW_ENV="/nonexistent",
                  GATE_BASE_URL="https://example.test", GATE_APPROVAL="auto",
                  GATE_GOOGLE_CLIENT_ID="test", GATE_GOOGLE_CLIENT_SECRET="test",
                  PRIVACY_OPERATOR="test", PRIVACY_CONTACT="test@example.test",
                  GATE_IP_ADMIN_PASSWORD="test-password-long-enough")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock"))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import gate
import news_marks


def app():
    a = FastAPI()
    gate.install(a)
    news_marks.install(a)
    return a


class MarksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()
        cls.clients = {}
        for name, admin in (("admin", True), ("guest", False), ("other", True)):
            u = gate.upsert_login("google", name)
            gate.record_consent(u["id"], ["privacy"], name)
            if admin:
                gate.set_admin(u["id"], True)
            c = TestClient(cls.app, base_url="https://example.test")
            c.cookies.set("gate_sess", gate._session_token(u["id"]))
            cls.clients[name] = c

    def setUp(self):
        self.admin = self.clients["admin"]
        self.guest = self.clients["guest"]
        with news_marks.db() as con:
            con.execute("DELETE FROM news_marks")
        self.body = {"date": "2026-11-03", "page": "01.jpg", "revision": 0, "strokes": [
            {"t": "line", "c": "#ff5b5b", "w": .018, "pts": [[.1, .2], [.7, .2]]}]}

    def get(self, client=None, day="2026-11-03"):
        return (client or self.admin).get("/api/news/marks", params={"date": day})

    def post(self, body=None, client=None):
        return (client or self.admin).post("/api/news/marks", json=body or self.body)

    def test_admin_save_and_new_app_restore(self):
        self.assertEqual(self.post().json()["revision"], 1)
        fresh = TestClient(app(), base_url="https://example.test")
        fresh.cookies.update(self.admin.cookies)
        r = self.get(fresh)
        self.assertEqual(r.json()["pages"]["01.jpg"]["strokes"], self.body["strokes"])
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_guest_cannot_read_or_write(self):
        self.post()
        self.assertEqual(self.get(self.guest).status_code, 403)
        self.assertEqual(self.post(client=self.guest).status_code, 403)
        self.assertEqual(self.get().json()["pages"]["01.jpg"]["revision"], 1)

    def test_anonymous_cannot_read_or_write(self):
        c = TestClient(self.app, base_url="https://example.test")
        self.assertEqual(self.get(c).status_code, 401)
        self.assertEqual(self.post(client=c).status_code, 401)

    def test_date_page_and_admin_are_isolated(self):
        self.post()
        b = dict(self.body, page="02.jpg")
        self.assertEqual(self.post(b).status_code, 200)
        self.assertEqual(len(self.get().json()["pages"]), 2)
        self.assertEqual(self.get(day="2026-11-02").json()["pages"], {})
        self.assertEqual(self.get(self.clients["other"]).json()["pages"], {})

    def test_ip_admin_uses_first_admin_marks(self):
        self.post()
        c = TestClient(self.app, base_url="https://127.0.0.1")
        c.cookies.set(gate.COOKIE_IPADM, gate._sign({"k": "ipadm", "v": gate._ipadm_ver()}, 3600))
        self.assertEqual(self.get(c).json()["pages"]["01.jpg"]["strokes"], self.body["strokes"])
        b = dict(self.body, revision=1, strokes=[])
        self.assertEqual(self.post(b, c).status_code, 200)
        self.assertEqual(self.get().json()["pages"]["01.jpg"]["strokes"], [])

    def test_clear_stays_empty_after_reload(self):
        self.post()
        self.assertEqual(self.post(dict(self.body, revision=1, strokes=[])).status_code, 200)
        self.assertEqual(self.get().json()["pages"]["01.jpg"], {"strokes": [], "revision": 2})

    def test_stale_tab_cannot_overwrite(self):
        self.post()
        self.assertEqual(self.post(dict(self.body, strokes=[])).status_code, 409)
        self.assertEqual(len(self.get().json()["pages"]["01.jpg"]["strokes"]), 1)

    def test_bad_date_page_and_revision(self):
        for k, v in (("date", "2026-02-30"), ("date", "../x"), ("page", "../01.jpg"),
                     ("revision", True), ("revision", -1)):
            with self.subTest(k=k, v=v):
                self.assertEqual(self.post(dict(self.body, **{k: v})).status_code, 400)

    def test_bad_strokes(self):
        for k, v in (("pts", [[-1, 0], [1, 1]]), ("pts", [[True, 0], [1, 1]]),
                     ("c", "url(evil)"), ("t", "script"), ("w", 0)):
            b = copy.deepcopy(self.body)
            b["strokes"][0][k] = v
            with self.subTest(k=k):
                self.assertEqual(self.post(b).status_code, 400)
        self.assertEqual(self.get().json()["pages"], {})

    def test_free_and_oval(self):
        for i, kind in enumerate(("free", "oval")):
            b = copy.deepcopy(self.body)
            b["revision"] = i
            b["strokes"][0]["t"] = kind
            self.assertEqual(self.post(b).status_code, 200)

    def test_csrf_content_type_and_size(self):
        r = self.admin.post("/api/news/marks", content=json.dumps(self.body), headers={"content-type": "text/plain"})
        self.assertEqual(r.status_code, 403)
        r = self.admin.post("/api/news/marks", json=self.body, headers={"sec-fetch-site": "cross-site"})
        self.assertEqual(r.status_code, 403)
        r = self.admin.post("/api/news/marks", content=" " * (news_marks.MAX_BODY + 1), headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_gate_disabled_does_not_allow_anonymous_storage(self):
        with mock.patch.dict(os.environ, {"GATE_ENABLED": "0"}):
            c = TestClient(self.app, base_url="https://example.test")
            self.assertEqual(self.post(client=c).status_code, 403)


    def test_stickers_are_saved_with_safe_labels_and_rectangles(self):
        for i, label in enumerate(("WHAT", "WHY", "HOW", "CHECK")):
            body = dict(self.body, revision=i, strokes=[{
                "t": "sticker", "label": label, "c": "untrusted", "w": 999,
                "pts": [[.1, .2], [.25, .24]]}])
            self.assertEqual(self.post(body).status_code, 200)
            sticker = self.get().json()["pages"]["01.jpg"]["strokes"][0]
            self.assertEqual(sticker["label"], label)
            self.assertEqual(sticker["t"], "sticker")
            self.assertEqual(sticker["w"], .01)
            self.assertEqual(sticker["c"], {"WHAT": "#1d4ed8", "WHY": "#7c3aed", "HOW": "#047857", "CHECK": "#b45309"}[label])

    def test_check_article_survives_save_and_reload(self):
        sticker = {"t": "sticker", "label": "CHECK", "article": "1테스트기사", "pts": [[.1, .2], [.25, .24]]}
        self.assertEqual(self.post(dict(self.body, strokes=[sticker])).status_code, 200)
        self.assertEqual(self.get().json()["pages"]["01.jpg"]["strokes"][0]["article"], "1테스트기사")

    def test_check_article_validation(self):
        sticker = {"t": "sticker", "label": "CHECK", "pts": [[.1, .2], [.25, .24]]}
        for value in ("", "<img>", "x" * 61, None, [], 123):
            with self.subTest(value=value):
                self.assertEqual(self.post(dict(self.body, strokes=[dict(sticker, article=value)])).status_code, 400)

    def test_sticker_validation(self):
        base = {"t": "sticker", "label": "WHAT", "pts": [[.1, .2], [.25, .24]]}
        for key, value in (("label", "<img src=x>"), ("label", "OTHER"), ("pts", [[-1, 0], [.2, .2]]),
                           ("pts", [[.1, .2]]), ("pts", [[.3, .2], [.1, .3]]),
                           ("pts", [[0, 0], [1, 1]]), ("pts", [[True, .1], [.2, .2]])):
            body = dict(self.body, strokes=[dict(base, **{key: value})])
            self.assertEqual(self.post(body).status_code, 400)

    def test_sticker_and_line_coexist_and_guest_cannot_save(self):
        sticker = {"t": "sticker", "label": "HOW", "pts": [[.2, .4], [.4, .45]]}
        body = dict(self.body, strokes=self.body["strokes"] + [sticker])
        self.assertEqual(self.post(body).status_code, 200)
        self.assertEqual(len(self.get().json()["pages"]["01.jpg"]["strokes"]), 2)
        self.assertEqual(self.post(body, self.guest).status_code, 403)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        TMP.cleanup()
