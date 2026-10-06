#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pt_briefing_dedupe.py — 종국이 브리핑 '하루 한 번만 발송' 점검 (2026-10-06)

21:00 crontab 과 openclaw cron 이 pt_briefing.py 를 둘 다 불러 같은 브리핑이 슬랙에
두 번 올라오던 문제를 막았는지 확인한다. 진짜 슬랙·진짜 DB 는 건드리지 않는다
(임시 HOME 에 빈 DB, 내 컴퓨터 안의 가짜 슬랙 서버로 '보낸 횟수'만 센다).

실행:  python3 scripts/test_pt_briefing_dedupe.py      (표준 라이브러리만)
"""
import os
import sys
import json
import sqlite3
import tempfile
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "pt_briefing.py"

# 가짜 슬랙 서버: chat.postMessage 를 받으면 보낸 내용을 파일에 한 줄씩 적는다.
# FAKE_SLACK_OK 파일이 있으면 실패로 응답(전송 실패 흉내). 진짜 slack.com 은 절대 안 부른다.
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def start_fake_slack(log, fail_flag):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            ok = not fail_flag.exists()
            if ok and self.path.endswith("chat.postMessage"):
                text = json.loads(body or b"{}").get("text", "")
                with open(log, "a", encoding="utf-8") as f:
                    f.write(text[:40].replace("\n", " ") + "\n")
            out = json.dumps({"ok": ok, "error": None if ok else "fake_fail"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {extra}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        home = tmp / "home"
        (home / "pt_data").mkdir(parents=True)
        sqlite3.connect(home / "pt_data" / "pt.db").close()   # 빈 DB(기록 없음 브리핑)
        log = tmp / "slack.log"
        fail_flag = tmp / "FAIL"
        srv = start_fake_slack(log, fail_flag)

        # 스크립트가 cwd 의 .env 도 읽으므로 cwd 를 빈 임시 폴더로 둔다.
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("SLACK_", "PT_"))}
        env.update({"HOME": str(home),
                    "PT_SLACK_API": f"http://127.0.0.1:{srv.server_port}/api",
                    "SLACK_BOT_TOKEN_KEEPGOING": "xoxb-fake",
                    "SLACK_KEEPGOING_CHANNEL": "CFAKE"})

        def run(*args, ok=True):
            if ok:
                fail_flag.unlink(missing_ok=True)
            else:
                fail_flag.touch()
            r = subprocess.run([sys.executable, str(SCRIPT), *args],
                               cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout + r.stderr

        def sent():
            return log.read_text(encoding="utf-8").count("\n") if log.exists() else 0

        def rows(btype="daily"):
            con = sqlite3.connect(home / "pt_data" / "pt.db")
            n = con.execute("SELECT COUNT(*) FROM briefings WHERE type=?", (btype,)).fetchone()[0]
            con.close()
            return n

        D = ["--date", "2026-10-05"]

        print("1) 첫 실행은 정상 발송")
        code, out = run("daily", *D)
        check("종료코드 0", code == 0, out)
        check("슬랙 1건", sent() == 1, out)
        check("웹(DB) 1줄", rows() == 1)

        print("2) 같은 날 두 번째 실행(다른 cron)은 건너뜀")
        code, out = run("daily", *D)
        check("종료코드 0", code == 0, out)
        check("슬랙 여전히 1건", sent() == 1, out)
        check("웹(DB) 여전히 1줄(두 줄 안 생김)", rows() == 1)
        check("건너뜀 안내 출력", "[Skip]" in out, out)

        print("3) --force 면 다시 보냄(수동 재발송)")
        code, out = run("daily", *D, "--force")
        check("슬랙 2건", sent() == 2, out)

        print("4) 날짜·종류가 다르면 각각 보냄")
        run("daily", "--date", "2026-10-06")
        check("다음 날 데일리 발송", sent() == 3)
        run("weekly", "--date", "2026-10-04")
        check("주간 브리핑은 데일리와 별개로 발송", sent() == 4)

        print("5) 슬랙 전송 실패 → 자리표 반납 → 다음 실행이 보냄")
        code, out = run("daily", "--date", "2026-10-07", ok=False)
        check("실패 시 슬랙 0건 추가", sent() == 4, out)
        code, out = run("daily", "--date", "2026-10-07")
        check("재시도 때 발송됨", sent() == 5, out)
        check("재시도는 건너뛰지 않음", "[Skip]" not in out, out)

        print("6) --no-slack 미리보기는 발송 기록을 남기지 않음")
        run("daily", "--date", "2026-10-08", "--no-slack", "--no-db", "--print")
        code, out = run("daily", "--date", "2026-10-08")
        check("미리보기 뒤 실제 발송 정상", sent() == 6, out)
        srv.shutdown()

    print(f"\n결과: {passed} 통과 / {failed} 실패")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
