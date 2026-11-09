"""경제 공부(디그) 형광펜 저장 API 검사 (2026-11-09): 실제 gate 쿠키·임시 SQLite, 외부 호출 없음.
실행: python3 -I scripts/test_dig_marks.py   (fastapi + httpx 필요)"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="dig_marks_", ignore_cleanup_errors=True)
os.environ.update(GATE_DIR=TMP.name, OPENCLAW_ENV="/nonexistent", GATE_BASE_URL="https://example.test", GATE_APPROVAL="auto",
                  GATE_GOOGLE_CLIENT_ID="test", GATE_GOOGLE_CLIENT_SECRET="test", PRIVACY_OPERATOR="test",
                  PRIVACY_CONTACT="test@example.test", GATE_IP_ADMIN_PASSWORD="test-password-long-enough")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock"))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import gate
import dig_marks


def app():
    a = FastAPI()
    gate.install(a)
    dig_marks.install(a)
    return a


def mark(u=1, s=0, e=5, c="y", q="파랗게 물든"):
    return {"u": u, "s": s, "e": e, "c": c, "q": q}


class DigMarksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()
        cls.cl = {}
        for name, admin in (("admin", True), ("guest", False), ("other", True)):
            u = gate.upsert_login("google", name)
            gate.record_consent(u["id"], ["privacy"], name)
            if admin:
                gate.set_admin(u["id"], True)
            c = TestClient(cls.app, base_url="https://example.test")
            c.cookies.set("gate_sess", gate._session_token(u["id"]))
            cls.cl[name] = c

    def setUp(self):
        self.admin, self.guest = self.cl["admin"], self.cl["guest"]
        with dig_marks.db() as con:
            con.execute("DELETE FROM dig_marks")

    def get(self, c=None, day="2026-11-09"):
        return (c or self.admin).get("/api/dig/marks", params={"id": day})

    def post(self, marks=None, rev=0, day="2026-11-09", c=None, **kw):
        body = {"id": day, "revision": rev, "marks": [mark()] if marks is None else marks}
        body.update(kw)
        return (c or self.admin).post("/api/dig/marks", json=body)

    # ① 권한
    def test_guest_and_anonymous_denied(self):
        self.post()
        self.assertEqual(self.get(self.guest).status_code, 403)
        self.assertEqual(self.post(c=self.guest).status_code, 403)
        anon = TestClient(self.app, base_url="https://example.test")
        self.assertIn(self.get(anon).status_code, (401, 403))
        self.assertIn(self.post(c=anon).status_code, (401, 403))
        self.assertEqual(self.get().json()["marks"][0]["c"], "y")       # 거절된 요청은 아무것도 바꾸지 않음

    def test_ip_admin_uses_first_admin_marks(self):
        self.post()
        c = TestClient(self.app, base_url="https://127.0.0.1")
        c.cookies.set(gate.COOKIE_IPADM, gate._sign({"k": "ipadm", "v": gate._ipadm_ver()}, 3600))
        self.assertEqual(self.get(c).json()["marks"], [mark()])          # 같은 관리자 = 같은 표시
        self.assertEqual(self.post([mark(c="r")], rev=1, c=c).json()["revision"], 2)

    # ② 저장·읽기
    def test_save_and_restore_with_new_app(self):
        r = self.post([mark(), mark(u=2, s=3, e=9, c="b", q="글")])
        self.assertEqual(r.json(), {"ok": True, "revision": 1, "count": 2})
        fresh = TestClient(app(), base_url="https://example.test")       # 서버를 다시 켠 것처럼
        fresh.cookies.update(self.admin.cookies)
        j = self.get(fresh).json()
        self.assertEqual((j["revision"], len(j["marks"])), (1, 2))
        self.assertEqual(self.get().headers["cache-control"], "no-store")

    def test_empty_list_clears(self):
        self.post()
        self.assertEqual(self.post([], rev=1).json()["revision"], 2)
        self.assertEqual(self.get().json()["marks"], [])

    def test_never_saved_returns_empty(self):
        self.assertEqual(self.get().json(), {"ok": True, "marks": [], "revision": 0})

    # ③ 격리: 호별·관리자별
    def test_isolated_by_issue_and_owner(self):
        self.post()
        self.assertEqual(self.get(day="2026-11-08").json()["marks"], [])
        self.assertEqual(self.get(self.cl["other"]).json()["marks"], [])
        self.post([mark(c="r")], rev=0, c=self.cl["other"])
        self.assertEqual(self.get().json()["marks"][0]["c"], "y")        # 다른 관리자 표시가 내 것을 안 덮음

    # ④ 버전: 다른 창이 먼저 저장했으면 덮어쓰지 않고 최신을 알려 줌
    def test_revision_conflict(self):
        self.assertEqual(self.post().status_code, 200)                    # 창 A: rev 0 → 1
        r = self.post([mark(c="r")], rev=0)                              # 창 B 도 rev 0 으로 저장 시도
        self.assertEqual(r.status_code, 409)
        j = r.json()
        self.assertTrue(j["conflict"])
        self.assertEqual((j["revision"], j["marks"][0]["c"]), (1, "y"))   # 최신(창 A 의 것)을 돌려줌
        self.assertEqual(self.get().json()["marks"][0]["c"], "y")         # 덮어쓰지 않음
        self.assertEqual(self.post([mark(c="r")], rev=1).status_code, 200)

    # ⑤ 입력 검사
    def test_validation(self):
        bad = [
            dict(day="../etc/passwd"), dict(day="2026-1-9"), dict(day=""),
            dict(rev=-1), dict(rev="0"), dict(rev=True),
            dict(marks=[mark(c="g")]), dict(marks=[mark(s=5, e=5)]), dict(marks=[mark(s=-1)]), dict(marks=[mark(e=20001)]),
            dict(marks=[mark(u=5001)]), dict(marks=[mark(u="1")]), dict(marks=[mark(q="x" * 61)]), dict(marks=[mark(q=1)]),
            dict(marks=[{"u": 1, "s": 0, "e": 3}]), dict(marks=["x"]), dict(marks="x"),
            dict(marks=[mark() for _ in range(dig_marks.MAX_MARKS + 1)]),
        ]
        for kw in bad:
            r = self.post(**kw) if "marks" in kw or "rev" in kw or "day" in kw else None
            self.assertEqual(r.status_code, 400, kw)
        self.assertEqual(self.get().json()["marks"], [])                  # 잘못된 요청은 아무것도 저장 안 함

    def test_get_with_bad_id(self):
        for day in ("", "x", "2026-11-9", "../x"):
            self.assertEqual(self.get(day=day).status_code, 400, day)

    def test_max_marks_allowed(self):
        self.assertEqual(self.post([mark(u=i % 50) for i in range(dig_marks.MAX_MARKS)]).status_code, 200)

    def test_body_too_large(self):
        r = self.admin.post("/api/dig/marks", content=b"x" * (dig_marks.MAX_BODY + 10), headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 413)

    def test_cross_site_and_wrong_content_type(self):
        self.assertEqual(self.admin.post("/api/dig/marks", json={"id": "2026-11-09", "revision": 0, "marks": []},
                                         headers={"sec-fetch-site": "cross-site"}).status_code, 403)
        self.assertEqual(self.admin.post("/api/dig/marks", content="id=2026-11-09", headers={"content-type": "text/plain"}).status_code, 403)

    def test_not_json(self):
        r = self.admin.post("/api/dig/marks", content=b"not json", headers={"content-type": "application/json"})
        self.assertEqual(r.status_code, 400)

    def test_stored_text_is_never_html_interpreted(self):
        """q 에 HTML 이 들어와도 그대로 문자열로만 저장·반환(화면은 textContent 비교에만 씀)."""
        self.post([mark(q="<img src=x onerror=1>")])
        self.assertEqual(self.get().json()["marks"][0]["q"], "<img src=x onerror=1>")

    # ⑥ 사설(신문 요약 화면 맨 아래) 표시: 같은 표·'ed-' 접두어로 따로 저장 (2026-11-09)
    def eget(self, c=None, day="2026-11-09"):
        return (c or self.admin).get("/api/news/edmarks", params={"date": day})

    def epost(self, marks=None, rev=0, day="2026-11-09", c=None):
        return (c or self.admin).post("/api/news/edmarks", json={"id": day, "revision": rev, "marks": [mark()] if marks is None else marks})

    def test_editorial_marks_admin_only(self):
        self.epost()
        self.assertEqual(self.eget(self.guest).status_code, 403)
        self.assertEqual(self.epost(c=self.guest).status_code, 403)
        anon = TestClient(self.app, base_url="https://example.test")
        self.assertIn(self.eget(anon).status_code, (401, 403))
        self.assertEqual(self.eget().json()["marks"], [mark()])

    def test_editorial_marks_separate_from_dig_marks(self):
        self.post([mark(c="y")])                                  # 같은 날짜(2026-11-09)의 디그 표시
        self.epost([mark(c="r"), mark(u=2, c="b", q="글")])         # 같은 날짜의 사설 표시
        self.assertEqual([m["c"] for m in self.get().json()["marks"]], ["y"])
        self.assertEqual([m["c"] for m in self.eget().json()["marks"]], ["r", "b"])
        self.assertEqual((self.get().json()["revision"], self.eget().json()["revision"]), (1, 1))

    def test_editorial_marks_revision_and_validation(self):
        self.assertEqual(self.epost().json()["revision"], 1)
        r = self.epost([mark(c="r")], rev=0)
        self.assertEqual((r.status_code, r.json()["conflict"], r.json()["marks"][0]["c"]), (409, True, "y"))
        self.assertEqual(self.epost([mark(c="g")], rev=1).status_code, 400)
        self.assertEqual(self.epost(rev=1, day="../x").status_code, 400)
        for day in ("", "x", "2026-11-9", "../x"):
            self.assertEqual(self.eget(day=day).status_code, 400, day)

    def test_editorial_marks_ip_admin_and_cross_site(self):
        self.epost()
        c = TestClient(self.app, base_url="https://127.0.0.1")
        c.cookies.set(gate.COOKIE_IPADM, gate._sign({"k": "ipadm", "v": gate._ipadm_ver()}, 3600))
        self.assertEqual(self.eget(c).json()["marks"], [mark()])
        self.assertEqual(self.admin.post("/api/news/edmarks", json={"id": "2026-11-09", "revision": 1, "marks": []},
                                         headers={"sec-fetch-site": "cross-site"}).status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
