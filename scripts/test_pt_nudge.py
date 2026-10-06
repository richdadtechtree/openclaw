#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pt_nudge.py — 종국이 '보고 독촉' 톡(pt_nudge.py) 점검 (2026-10-06)

진짜 슬랙·진짜 DB 는 건드리지 않는다. 임시 HOME 에 PT DB 를 만들고, 내 컴퓨터 안에 가짜 슬랙
서버를 띄워 ①형준이 채널 메시지(conversations.history)를 흉내 내고 ②보낸 독촉(chat.postMessage)을 센다.

실행:  python3 scripts/test_pt_nudge.py      (표준 라이브러리만)
"""
import os
import sys
import json
import sqlite3
import tempfile
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "pt_nudge.py"
KST = ZoneInfo("Asia/Seoul")
USER = "UFAKEUSER"

STATE = {"msgs": [], "sent": [], "post_ok": True, "read_ok": True}


class FakeSlack(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, obj):
        out = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):   # conversations.history
        qs = parse_qs(urlparse(self.path).query)
        if not STATE["read_ok"]:
            return self._reply({"ok": False, "error": "missing_scope"})
        oldest = float(qs.get("oldest", ["0"])[0])
        msgs = [m for m in STATE["msgs"] if float(m["ts"]) >= oldest]
        self._reply({"ok": True, "messages": list(reversed(msgs))})

    def do_POST(self):  # chat.postMessage
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if STATE["post_ok"]:
            STATE["sent"].append(body.get("text", ""))
        self._reply({"ok": STATE["post_ok"]})


def ts(day, hhmm):
    return f"{datetime.fromisoformat(f'{day}T{hhmm}').replace(tzinfo=KST).timestamp():.6f}"


def say(day, hhmm, text, user=USER, bot=False):
    m = {"ts": ts(day, hhmm), "user": user, "text": text}
    if bot:
        m["bot_id"] = "BFAKE"
    STATE["msgs"].append(m)


passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}\n     {extra}")


def main():
    srv = HTTPServer(("127.0.0.1", 0), FakeSlack)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        home = tmp / "home"
        (home / "pt_data").mkdir(parents=True)
        db = home / "pt_data" / "pt.db"
        con = sqlite3.connect(db)
        con.executescript("""
          CREATE TABLE workouts (id INTEGER PRIMARY KEY, date TEXT, exercise TEXT, sets INT,
                                 reps INT, weight_kg REAL, raw TEXT, created_at TEXT);
          CREATE TABLE diet (id INTEGER PRIMARY KEY, date TEXT, meal TEXT, items TEXT,
                             protein_g REAL, raw TEXT, created_at TEXT);
          CREATE TABLE vitals (id INTEGER PRIMARY KEY, date TEXT UNIQUE, weight_kg REAL,
                               sleep_hours REAL, condition TEXT, alcohol INT DEFAULT 0, created_at TEXT);
        """)
        con.commit()

        def db_add(sql, *p):
            con.execute(sql, p)
            con.commit()

        env = {k: v for k, v in os.environ.items() if not k.startswith(("SLACK_", "PT_"))}
        env.update({"HOME": str(home),
                    "PT_SLACK_API": f"http://127.0.0.1:{srv.server_port}/api",
                    "SLACK_BOT_TOKEN_KEEPGOING": "xoxb-fake",
                    "SLACK_KEEPGOING_CHANNEL": "CFAKE",
                    "PT_SLACK_USER": USER})

        def run(slot, now, *extra, **kw):
            before = len(STATE["sent"])
            e = dict(env, **kw)
            r = subprocess.run([sys.executable, str(SCRIPT), slot, "--now", now, *extra],
                               cwd=tmp, env=e, capture_output=True, text=True, timeout=60)
            new = STATE["sent"][before:]
            return r.returncode, r.stdout + r.stderr, new

        # 기준일 앞에 '기록 있는 날'을 하나 넣어 둔다(잠수 일수 계산이 다른 검사에 끼지 않게).
        def seed_prev(day):
            db_add("INSERT INTO vitals (date, sleep_hours) VALUES (?, 7)", day)

        print("1) 아침: 아무것도 없으면 독촉 + 수면·체중도 물음 + 멘션")
        seed_prev("2026-10-09")
        code, out, new = run("morning", "2026-10-10T10:00")
        check("1건 보냄", len(new) == 1, out)
        check("형준 멘션(폰 알림)", new and new[0].startswith(f"<@{USER}>"), new)
        check("아침 얘기", new and "아침" in new[0], new)
        check("수면·체중도 물음", new and "잤어" in new[0], new)

        print("2) 같은 시간대 두 번 실행 → 한 번만")
        code, out, new = run("morning", "2026-10-10T10:05")
        check("두 번째는 안 보냄", len(new) == 0, out)

        print("3) 형준이 이미 '아침 …'·'수면 …' 올렸으면 → 조용")
        seed_prev("2026-10-10")
        say("2026-10-11", "07:30", "아침 계란 3개 그릭요거트")
        say("2026-10-11", "07:31", "수면 7시간, 체중 74.5kg")
        code, out, new = run("morning", "2026-10-11T10:00")
        check("안 보냄", len(new) == 0, out)

        print("4) 아침은 DB 에만 있고(채널엔 없음) 수면 없음 → 수면만 물음")
        seed_prev("2026-10-11")
        db_add("INSERT INTO diet (date, meal, items) VALUES ('2026-10-12','아침','오트밀')")
        code, out, new = run("morning", "2026-10-12T10:00")
        check("수면·체중만 물음", len(new) == 1 and "아침 먹었" not in new[0] and "잤어" in new[0], new)

        print("5) 점심: 아침도 점심도 없으면 바로 센 말투")
        seed_prev("2026-10-12")
        code, out, new = run("lunch", "2026-10-13T13:30")
        check("1건 보냄", len(new) == 1, out)
        check("아침·점심 둘 다 짚음", new and "아침" in new[0] and "점심" in new[0], new)

        print("6) 운동: DB 에 운동 있으면 조용 / 채널에 '레그프레스 160×10' 도 운동으로 인정")
        seed_prev("2026-10-13")
        db_add("INSERT INTO workouts (date, exercise) VALUES ('2026-10-14','스쿼트')")
        code, out, new = run("workout", "2026-10-14T18:30")
        check("DB 운동 → 안 보냄", len(new) == 0, out)
        seed_prev("2026-10-14")
        say("2026-10-15", "13:06", "레그 프레스 160×11 / 200×12")
        code, out, new = run("workout", "2026-10-15T18:30")
        check("채널 운동 → 안 보냄", len(new) == 0, out)

        print("7) '체중 74.7kg' 은 운동으로 안 침 → 운동 독촉 나감")
        seed_prev("2026-10-15")
        say("2026-10-16", "06:15", "수면 8시간 , 체중 74.7kg")
        code, out, new = run("workout", "2026-10-16T18:30")
        check("운동 독촉 1건", len(new) == 1, out)

        print("8) 오전 독촉을 씹으면(그 뒤 답 없음) 저녁 독촉은 한 단계 세게")
        seed_prev("2026-10-16")
        say("2026-10-17", "07:00", "수면 7시간")
        run("morning", "2026-10-17T10:00")
        code, out, new = run("workout", "2026-10-17T18:30")
        strong = ("퇴근했으면", "스쿼트 20개", "신발부터")
        check("센 문장", len(new) == 1 and any(k in new[0] for k in strong), new)
        # 대조: 독촉 뒤에 답했으면 첫 단계 문장
        seed_prev("2026-10-17")
        say("2026-10-18", "07:00", "수면 7시간")
        run("morning", "2026-10-18T10:00")
        say("2026-10-18", "10:20", "아침 바나나")
        code, out, new = run("workout", "2026-10-18T18:30")
        check("답했으면 첫 단계", len(new) == 1 and not any(k in new[0] for k in strong), new)

        print("9) 아프다고 했으면 운동 독촉 안 함, 마지막 경고에서도 운동은 뺌")
        seed_prev("2026-10-18")
        say("2026-10-19", "12:00", "점심 비빔밥. 허리가 찌릿하게 아파")
        code, out, new = run("workout", "2026-10-19T18:30")
        check("운동 독촉 없음", len(new) == 0, out)
        code, out, new = run("final", "2026-10-19T20:30")
        check("마지막 경고에 '운동' 없음 + 쉬라는 말",
              len(new) == 1 and "운동 ·" not in new[0] and "쉬어" in new[0], new)

        print("10) 하루 종일 무소식 → 마지막 경고 최강")
        seed_prev("2026-10-19")
        code, out, new = run("final", "2026-10-20T20:30")
        check("하루 종일 무소식 문장", len(new) == 1 and ("0건" in new[0] or "하루 종일" in new[0]), new)

        print("11) 운동·저녁 다 올렸으면 마지막 경고 없음")
        seed_prev("2026-10-20")
        say("2026-10-21", "19:40", "운동 테니스 2게임")
        say("2026-10-21", "20:10", "저녁 제육볶음 현미밥")
        code, out, new = run("final", "2026-10-21T20:30")
        check("안 보냄", len(new) == 0, out)

        print("12) '잔소리 쉬어' 라고 하면 그날은 조용")
        seed_prev("2026-10-21")
        say("2026-10-22", "08:00", "종국아 오늘 캠핑이라 잔소리 쉬어")
        code, out, new = run("lunch", "2026-10-22T13:30")
        check("안 보냄", len(new) == 0, out)

        print("13) 며칠째 기록이 없으면 'N일째' 를 붙임 (채널에만 올린 날도 '기록 있음')")
        # 10/22 은 DB 엔 없고 채널 메시지만 있음 → 기록 있는 날. 10/23·10/24 은 아무것도 없음.
        code, out, new = run("lunch", "2026-10-25T13:30")
        check("'2일째' 붙음", len(new) == 1 and "2일째" in new[0], new)

        print("14) 채널을 못 읽어도(권한 없음) 죽지 않고 DB 로만 판단")
        seed_prev("2026-10-25")
        STATE["read_ok"] = False
        code, out, new = run("lunch", "2026-10-26T13:30")
        STATE["read_ok"] = True
        check("종료코드 0 + 1건", code == 0 and len(new) == 1, out)

        print("15) 전송 실패 → 기록 반납 → 다음 실행 때 보냄")
        seed_prev("2026-10-26")
        STATE["post_ok"] = False
        run("workout", "2026-10-27T18:30")
        STATE["post_ok"] = True
        code, out, new = run("workout", "2026-10-27T18:40")
        check("재시도 때 1건", len(new) == 1, out)

        print("16) --dry-run 은 보내지도 기록하지도 않음 / PT_NUDGE=off 면 꺼짐")
        seed_prev("2026-10-27")
        code, out, new = run("workout", "2026-10-28T18:30", "--dry-run")
        check("dry-run 0건 + 내용 출력", len(new) == 0 and "보낼 내용" in out, out)
        code, out, new = run("workout", "2026-10-28T18:31")
        check("dry-run 뒤 실제 실행은 보냄", len(new) == 1, out)
        code, out, new = run("final", "2026-10-28T20:30", PT_NUDGE="off")
        check("PT_NUDGE=off → 0건", len(new) == 0 and "꺼짐" in out, out)

        print("17) 봇(종국이)이 쓴 메시지는 형준이 기록으로 안 침")
        seed_prev("2026-10-28")
        say("2026-10-29", "12:00", "점심 뭐 먹었어?", user="UBOT", bot=True)
        code, out, new = run("lunch", "2026-10-29T13:30")
        check("독촉 나감", len(new) == 1, out)

        con.close()
    srv.shutdown()
    print(f"\n결과: {passed} 통과 / {failed} 실패")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
