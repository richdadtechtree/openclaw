"""시장 관심종목 API 권한·영속 저장·시세 실패 검사 (외부 API/실제 회원 DB 사용 안 함)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock"))
import market_watch as watch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


class FakeGate:
    @staticmethod
    def _check(request):
        if request.headers.get("x-role") not in ("admin", "reader", "ip"):
            return JSONResponse({"ok": False}, status_code=401)
        return None

    @staticmethod
    def is_ip_host(request):
        return request.headers.get("x-role") == "ip"

    @staticmethod
    def ip_admin_ok(request):
        return request.headers.get("x-role") == "ip"

    @staticmethod
    def ip_pseudo_admin():
        return {"id": 0, "is_admin": True}

    @staticmethod
    def session_user(request):
        return {"id": 1, "is_admin": request.headers.get("x-role") == "admin"}

    @staticmethod
    def is_admin(user):
        return bool(user and user["is_admin"])

    @staticmethod
    def _csrf(uid):
        return "csrf-%s" % uid


class MarketWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"MARKET_WATCH_DB": str(Path(self.tmp.name) / "watch.sqlite")})
        self.env.start()
        watch._cache.clear()
        self.quote = patch.object(watch, "quote", return_value={
            "current": 102.0, "change_rate": 2.0, "source": "TEST",
            "currency": "USD", "market_date": "2026-11-03", "observed_at": watch.time.time()})
        self.quote.start()
        app = FastAPI()
        watch.install(app, FakeGate)
        self.client = TestClient(app)
        self.admin = {"x-role": "admin", "x-csrf-token": "csrf-1"}

    def tearDown(self):
        self.client.close()
        self.quote.stop()
        self.env.stop()
        self.tmp.cleanup()

    def post(self, data, headers=None):
        return self.client.post("/market/api/watchlist", json=data, headers=headers or self.admin)

    def test_auth_required(self):
        for path in ("/market/api/watchlist", "/market/api/watchlist/quotes"):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.post({"action": "add", "symbol": "AAPL", "name": "애플"},
                                   headers={"x-role": "reader", "x-csrf-token": "csrf-1"}).status_code, 403)
        self.assertEqual(watch.items(), [])

    def test_reader_cannot_mutate_even_with_admin_csrf(self):
        self.assertEqual(self.post({"action": "add", "symbol": "AAPL", "name": "애플"}).status_code, 200)
        row = watch.items()[0]
        r = self.post({"action": "remove", "id": row["id"]},
                      headers={"x-role": "reader", "x-csrf-token": "csrf-1"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(len(watch.items()), 1)

    def test_csrf_required(self):
        r = self.post({"action": "add", "symbol": "AAPL", "name": "애플"}, headers={"x-role": "admin"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(watch.items(), [])

    def test_admin_add_normalize_and_persist(self):
        r = self.post({"action": "add", "symbol": " aapl ", "name": " 애플 "})
        self.assertEqual(r.status_code, 200)
        row = watch.items()[0]
        self.assertEqual((row["symbol"], row["name"]), ("AAPL", "애플"))
        with watch._db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM market_watch").fetchone()[0], 1)
        self.assertEqual(self.client.get("/market/api/watchlist", headers={"x-role": "reader"}).json()["csrf"], "")
        self.assertFalse(self.client.get("/market/api/watchlist", headers={"x-role": "reader"}).json()["can_manage"])
        self.assertTrue(self.client.get("/market/api/watchlist", headers={"x-role": "admin"}).json()["can_manage"])

    def test_ip_admin(self):
        self.assertEqual(self.post({"action": "add", "symbol": "005930", "name": "삼성전자"},
                                   headers={"x-role": "ip", "x-csrf-token": "csrf-0"}).status_code, 200)

    def test_invalid_and_duplicate(self):
        for symbol in ("../../env", "12345", "AAPL?x", "", "A" * 50):
            self.assertEqual(self.post({"action": "add", "symbol": symbol, "name": "종목"}).status_code, 400)
        self.assertEqual(self.post({"action": "add", "symbol": "AAPL", "name": ""}).status_code, 400)
        self.assertEqual(self.post({"action": "add", "symbol": "AAPL", "name": "애플"}).status_code, 200)
        self.assertEqual(self.post({"action": "add", "symbol": "AAPL", "name": "중복"}).status_code, 400)

    def test_failed_quote_not_saved(self):
        with patch.object(watch, "quote", return_value=None):
            self.assertEqual(self.post({"action": "add", "symbol": "BAD", "name": "오류"}).status_code, 400)
        self.assertEqual(watch.items(), [])

    def test_limit_and_remove(self):
        with patch.object(watch, "MAX_STOCKS", 1):
            self.assertEqual(self.post({"action": "add", "symbol": "AAPL", "name": "애플"}).status_code, 200)
            self.assertEqual(self.post({"action": "add", "symbol": "TSLA", "name": "테슬라"}).status_code, 400)
        old = watch.items()[0]["id"]
        self.assertEqual(self.post({"action": "remove", "id": old}).status_code, 200)
        self.assertEqual(watch.items(), [])
        self.assertEqual(self.post({"action": "add", "symbol": "AAPL", "name": "애플"}).status_code, 200)
        self.assertGreater(watch.items()[0]["id"], old)

    def test_snapshot_and_no_store(self):
        watch.add("AAPL", "애플")
        r = self.client.get("/market/api/watchlist/quotes", headers={"x-role": "reader"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(r.json()["items"][0]["quote"]["change_rate"], 2)
        self.assertEqual(r.json()["step"], 2)

    def test_quote_failure_clears_old_quote(self):
        watch.add("AAPL", "애플")
        with patch.object(watch, "quote", return_value=None):
            watch._refresh(watch.items())
        self.assertIsNone(watch.snapshot()[0]["quote"])

    def test_fail_closed_without_gate(self):
        app = FastAPI()
        watch.install(app, None)
        with TestClient(app) as c:
            self.assertEqual(c.get("/market/api/watchlist").status_code, 503)
            self.assertEqual(c.post("/market/api/watchlist", json={}).status_code, 503)

    def test_bad_json(self):
        self.assertEqual(self.client.post("/market/api/watchlist", content="{", headers=self.admin).status_code, 400)
        self.assertEqual(self.post([]).status_code, 400)
        self.assertEqual(self.post({"action": "remove", "id": "../"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
