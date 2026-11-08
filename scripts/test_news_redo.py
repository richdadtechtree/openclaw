"""🔁 신문 '다시 가져와 요약' 버튼 서버 쪽 검사 (2026-11-09). 실제 gate 쿠키/임시 SQLite, 수집기·동기화·슬랙은 전부 가짜.
실행: python3 scripts/test_news_redo.py   (fastapi + httpx 필요)"""
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TMP = tempfile.TemporaryDirectory(prefix="news_redo_", ignore_cleanup_errors=True)
os.environ.update(GATE_DIR=TMP.name, OPENCLAW_ENV="/nonexistent",
                  GATE_BASE_URL="https://example.test", GATE_APPROVAL="auto",
                  GATE_GOOGLE_CLIENT_ID="test", GATE_GOOGLE_CLIENT_SECRET="test",
                  PRIVACY_OPERATOR="test", PRIVACY_CONTACT="test@example.test",
                  GATE_IP_ADMIN_PASSWORD="test-password-long-enough")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stock"))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import gate
import news_redo

# 가짜 수집기 폴더: app/main.py 가 MODE 파일에 적힌 대로 성공(0)/실패(1)한다. 실제 카페·브라우저는 안 쓴다.
NPDIR = Path(TMP.name) / "newspaper"
(NPDIR / "app").mkdir(parents=True)
(NPDIR / "app" / "main.py").write_text(
    "import sys,pathlib\nm=pathlib.Path(__file__).with_name('mode').read_text().strip()\nprint('수집 시도 mode='+m)\nsys.exit(0 if m=='ok' else 1)\n")
SYNC = Path(TMP.name) / "fake_sync.py"
SYNC.write_text("import sys,pathlib\nrc=int(pathlib.Path(__file__).with_name('sync_rc').read_text())\nopen(__file__+'.args','w').write(' '.join(sys.argv[1:]))\nsys.exit(rc)\n")
os.environ.update(NEWSPAPER_DIR=str(NPDIR), NEWS_SYNC_SCRIPT=str(SYNC))


def mode(m, sync_rc=0):
    (NPDIR / "app" / "mode").write_text(m)
    (Path(TMP.name) / "sync_rc").write_text(str(sync_rc))


def app():
    a = FastAPI()
    gate.install(a)
    news_redo.install(a)
    return a


def wait_done(c, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        s = c.get("/api/news/redo").json()["state"]
        if not s["running"]:
            return s
        time.sleep(0.1)
    raise AssertionError("끝나지 않음")


class RedoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app()
        cls.clients = {}
        for name, admin in (("admin", True), ("guest", False)):
            u = gate.upsert_login("google", name)
            gate.record_consent(u["id"], ["privacy"], name)
            if admin:
                gate.set_admin(u["id"], True)
            c = TestClient(cls.app, base_url="https://example.test")
            c.cookies.set("gate_sess", gate._session_token(u["id"]))
            cls.clients[name] = c
        Path(TMP.name, "sync_rc").write_text("0")

    def setUp(self):
        self.admin, self.guest = self.clients["admin"], self.clients["guest"]
        news_redo._state.update(running=False, ok=None, step="", message="", date="", started=0.0, finished=0.0, steps={}, tail="")
        for k in ("NEWS_REDO_GPT_MENTION", "SLACK_BOT_TOKEN"):
            os.environ.pop(k, None)

    def post(self, body=None, client=None):
        return (client or self.admin).post("/api/news/redo", json=body if body is not None else {})

    # ① 권한
    def test_guest_and_anonymous_are_denied(self):
        mode("ok")
        self.assertEqual(self.guest.get("/api/news/redo").status_code, 403)
        self.assertEqual(self.post(client=self.guest).status_code, 403)
        anon = TestClient(self.app, base_url="https://example.test")
        self.assertIn(anon.get("/api/news/redo").status_code, (401, 403))
        self.assertIn(anon.post("/api/news/redo", json={}).status_code, (401, 403))
        self.assertFalse(news_redo._state["running"])         # 거절된 요청은 아무것도 시작하지 않음

    def test_ip_admin_allowed(self):
        mode("ok")
        c = TestClient(self.app, base_url="https://127.0.0.1")
        c.cookies.set(gate.COOKIE_IPADM, gate._sign({"k": "ipadm", "v": gate._ipadm_ver()}, 3600))
        self.assertEqual(c.get("/api/news/redo").status_code, 200)

    def test_cross_site_and_non_json_rejected(self):
        mode("ok")
        r = self.admin.post("/api/news/redo", json={}, headers={"sec-fetch-site": "cross-site"})
        self.assertEqual(r.status_code, 403)
        r = self.admin.post("/api/news/redo", content="x=1", headers={"content-type": "application/x-www-form-urlencoded"})
        self.assertEqual(r.status_code, 403)

    def test_only_today_allowed(self):
        mode("ok")
        r = self.post({"date": "2020-01-01"})
        self.assertEqual(r.status_code, 400)

    # ② 정상 흐름: 가져오기 → 연결 → (요약 설정 없음) 건너뜀
    def test_success_without_summary_config(self):
        mode("ok", 0)
        r = self.post()
        self.assertTrue(r.json()["started"])
        s = wait_done(self.admin)
        self.assertTrue(s["ok"])
        self.assertEqual([s["steps"][k]["status"] for k in ("collect", "sync", "summary")], ["ok", "ok", "skip"])
        self.assertIn("NEWS_REDO_GPT_MENTION", s["steps"]["summary"]["note"])
        args = Path(str(SYNC) + ".args").read_text()
        self.assertIn(news_redo.today_kst(), args)
        self.assertIn("--force", args)                          # 이미 캐시가 있어도 다시 연결

    # ③ 수집 실패 → 뒤 단계를 하지 않고 이유를 알려 준다(로그 끝부분 포함)
    def test_collect_failure_stops_pipeline(self):
        mode("fail", 0)
        self.post()
        s = wait_done(self.admin)
        self.assertFalse(s["ok"])
        self.assertEqual(s["steps"]["collect"]["status"], "fail")
        self.assertEqual(s["steps"]["sync"]["status"], "wait")
        self.assertEqual(s["steps"]["summary"]["status"], "wait")
        self.assertIn("수집 시도 mode=fail", s["tail"])

    def test_sync_not_found_message(self):
        mode("ok", 2)
        self.post()
        s = wait_done(self.admin)
        self.assertFalse(s["ok"])
        self.assertEqual(s["steps"]["sync"]["status"], "fail")
        self.assertEqual(s["steps"]["summary"]["status"], "wait")

    # ④ 요약 요청: 슬랙에 ChatGPT 멘션 글을 올린다
    def test_summary_request_posts_to_slack(self):
        mode("ok", 0)
        os.environ.update(NEWS_REDO_GPT_MENTION="<@U0ABC12345>", SLACK_BOT_TOKEN="xoxb-test", SLACK_GPT_CHANNEL="C123")
        seen = {}

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b'{"ok": true}'

        def fake_open(req, timeout=0):
            seen["url"], seen["auth"] = req.full_url, req.get_header("Authorization")
            seen["body"] = json.loads(req.data.decode("utf-8"))
            return R()

        with mock.patch.object(news_redo.urllib.request, "urlopen", fake_open):
            self.post()
            s = wait_done(self.admin)
        self.assertTrue(s["ok"], s)
        self.assertEqual(s["steps"]["summary"]["status"], "ok")
        self.assertEqual(seen["url"], "https://slack.com/api/chat.postMessage")
        self.assertEqual(seen["body"]["channel"], "C123")
        self.assertTrue(seen["body"]["text"].startswith("<@U0ABC12345>"))
        self.assertIn(news_redo.today_kst(), seen["body"]["text"])
        self.assertTrue(seen["auth"].startswith("Bearer "))

    def test_slack_error_reported_but_download_kept(self):
        mode("ok", 0)
        os.environ.update(NEWS_REDO_GPT_MENTION="<@U0ABC12345>", SLACK_BOT_TOKEN="xoxb-test")

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b'{"ok": false, "error": "not_in_channel"}'

        with mock.patch.object(news_redo.urllib.request, "urlopen", lambda *a, **k: R()):
            self.post()
            s = wait_done(self.admin)
        self.assertFalse(s["ok"])
        self.assertEqual(s["steps"]["sync"]["status"], "ok")      # 신문은 이미 받았다
        self.assertIn("not_in_channel", s["message"])

    def test_bad_mention_is_never_posted(self):
        """멘션 설정이 슬랙 멘션 모양이 아니면(예: @channel, 임의 글) 올리지 않는다."""
        for bad in ("<!channel>", "@here", "hello <@U123456>", ""):
            os.environ["NEWS_REDO_GPT_MENTION"] = bad
            self.assertEqual(news_redo.mention(), "", bad)

    # ⑤ 중복 실행 방지
    def test_second_click_while_running_is_ignored(self):
        mode("ok", 0)
        with mock.patch.object(news_redo, "run_collect", lambda: (time.sleep(0.6) or (True, ""))):
            self.assertTrue(self.post().json()["started"])
            self.assertFalse(self.post().json()["started"])
            s = wait_done(self.admin)
        self.assertTrue(s["ok"])

    def test_cooldown_after_finish(self):
        mode("ok", 0)
        self.post()
        wait_done(self.admin)
        self.assertFalse(self.post().json()["started"])          # 방금 끝났으면 연타 무시

    # ⑥ 예상 못 한 오류가 나도 '진행 중' 이 남지 않는다
    def test_unexpected_exception_clears_running(self):
        mode("ok", 0)
        with mock.patch.object(news_redo, "run_collect", side_effect=RuntimeError("boom")):
            self.post()
            s = wait_done(self.admin)
        self.assertFalse(s["running"])
        self.assertFalse(s["ok"])

    def test_missing_collector_dir(self):
        with mock.patch.dict(os.environ, {"NEWSPAPER_DIR": "/nonexistent/np"}):
            ok, note = news_redo.run_collect()
        self.assertFalse(ok)
        self.assertIn("/nonexistent/np", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
