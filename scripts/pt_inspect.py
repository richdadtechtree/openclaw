#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_inspect.py — PT 트레이너 시스템 서버 현황 진단 (읽기 전용)

목적: claude.ai 세션에서는 서버 파일(텔레그램 폴더/DB/대시보드 앱)을 볼 수 없으므로,
      서버에서 이 스크립트를 실행해 구조를 뽑아 붙여주면 정확히 구현할 수 있다.

안전: 읽기만 한다. 아무것도 쓰거나 지우지 않는다. 토큰/키/비밀은 자동 마스킹한다.

사용:  python3 ~/.openclaw/scripts/pt_inspect.py
       (출력 전체를 복사해서 Claude 에게 붙여넣기)
"""
import os
import re
import sys
import glob
import json
import sqlite3
import subprocess
from pathlib import Path

HOME = os.path.expanduser("~")
OPENCLAW = os.path.expanduser("~/.openclaw")

# ── 비밀 마스킹 ──────────────────────────────────────────────
SECRET_PATTERNS = [
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"), "<TELEGRAM_TOKEN>"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "<SLACK_TOKEN>"),
    (re.compile(r"\bxapp-[A-Za-z0-9-]{10,}\b"), "<SLACK_APP_TOKEN>"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"), "<GEMINI_KEY>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "<OPENAI_KEY>"),
    (re.compile(r"\bBSA[A-Za-z0-9_-]{10,}\b"), "<BRAVE_KEY>"),
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "<HEX_SECRET>"),
    (re.compile(r'("(?:api_?key|token|secret|password|authorization)"\s*:\s*")[^"]+(")', re.I),
        r"\1<REDACTED>\2"),
]


def mask(text: str) -> str:
    if text is None:
        return ""
    for pat, repl in SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


def h(title):
    print("\n" + "=" * 70)
    print("### " + title)
    print("=" * 70)


def safe(fn):
    try:
        fn()
    except Exception as e:
        print(f"  [!] 오류: {e!r}")


# ── 1. 텔레그램 폴더 ─────────────────────────────────────────
def inspect_telegram():
    h("1) 텔레그램 폴더 구조 및 포맷  (/.openclaw/telegram/)")
    candidates = [
        os.path.join(OPENCLAW, "telegram"),
        os.path.join(OPENCLAW, "channels", "telegram"),
        "/.openclaw/telegram",
    ]
    found = None
    for c in candidates:
        if os.path.isdir(c):
            found = c
            break
    if not found:
        print("  텔레그램 폴더를 표준 위치에서 못 찾음. 전체 검색:")
        for root, dirs, files in os.walk(OPENCLAW):
            if os.path.basename(root).lower() == "telegram":
                print("   후보:", root)
                found = found or root
        if not found:
            print("  없음.")
            return
    print(f"  경로: {found}")
    # 트리 (최대 200개)
    print("\n  -- 파일 목록 (경로 / 크기bytes / 수정시각) --")
    count = 0
    entries = []
    for root, dirs, files in os.walk(found):
        for f in sorted(files):
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
                entries.append((p, st.st_size, int(st.st_mtime)))
            except Exception:
                pass
    entries.sort(key=lambda x: x[2], reverse=True)
    for p, size, mt in entries[:200]:
        rel = os.path.relpath(p, found)
        print(f"   {rel}  |  {size}B")
        count += 1
    print(f"  (총 {len(entries)}개 파일, {count}개 표시)")

    # 파일 확장자 분포
    exts = {}
    for p, _, _ in entries:
        e = os.path.splitext(p)[1].lower() or "(noext)"
        exts[e] = exts.get(e, 0) + 1
    print("\n  -- 확장자 분포 --")
    for e, n in sorted(exts.items(), key=lambda x: -x[1]):
        print(f"   {e}: {n}")

    # 가장 최근 파일 몇 개 샘플 (텍스트/JSON/JSONL 위주)
    print("\n  -- 최근 파일 내용 샘플 (마스킹, 각 파일 앞부분만) --")
    shown = 0
    for p, size, mt in entries:
        if shown >= 4:
            break
        ext = os.path.splitext(p)[1].lower()
        if ext not in (".json", ".jsonl", ".txt", ".md", ".log", ".ndjson", ""):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                data = fh.read(2500)
        except Exception as e:
            print(f"   [{p}] 읽기 실패: {e}")
            continue
        print(f"\n   ── FILE: {os.path.relpath(p, found)}  ({size}B) ──")
        print("   " + mask(data)[:2500].replace("\n", "\n   "))
        shown += 1


# ── 2. DB 탐색 ───────────────────────────────────────────────
def inspect_db():
    h("2) DB 탐색 (sqlite/*.db) + 스키마 + 행수 + 샘플")
    roots = [OPENCLAW, os.path.join(HOME, "pt"), os.path.join(HOME, "pt_system"),
             os.path.join(HOME, "mystatus")]
    patterns = ["*.db", "*.sqlite", "*.sqlite3"]
    dbs = set()
    for r in roots:
        if not os.path.isdir(r):
            continue
        for dirpath, dirs, files in os.walk(r):
            # venv/node_modules 스킵
            dirs[:] = [d for d in dirs if d not in ("venv", ".venv", "node_modules", "__pycache__")]
            for f in files:
                for pat in patterns:
                    if glob.fnmatch.fnmatch(f, pat):
                        dbs.add(os.path.join(dirpath, f))
    # 홈 최상위도 빠르게
    for pat in patterns:
        for p in glob.glob(os.path.join(HOME, pat)):
            dbs.add(p)

    if not dbs:
        print("  sqlite DB 파일을 못 찾음 (~/.openclaw, ~/pt, ~/mystatus, ~ 최상위 기준).")
        print("  → 기록이 파일(md/json)로만 남거나, DB 경로가 다른 곳일 수 있음.")
    for db in sorted(dbs):
        print(f"\n  ── DB: {db}  ({os.path.getsize(db)}B) ──")
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            cur = con.cursor()
            cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            if not tables:
                print("     (테이블 없음)")
            for name, sql in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM '{name}'")
                    n = cur.fetchone()[0]
                except Exception as e:
                    n = f"?({e})"
                print(f"     • 테이블 {name}: {n} 행")
                print("       스키마: " + mask((sql or "").replace("\n", " ")))
                # 최근 샘플 3행
                try:
                    cur.execute(f"SELECT * FROM '{name}' LIMIT 3")
                    cols = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                    print("       컬럼: " + ", ".join(cols))
                    for row in rows:
                        s = mask(str(tuple(str(x)[:80] for x in row)))
                        print("       샘플: " + s)
                except Exception as e:
                    print(f"       샘플 읽기 실패: {e}")
            con.close()
        except Exception as e:
            print(f"     [!] 열기 실패: {e}")


# ── 3. PT 기록 파일 (비-DB) 탐색 ─────────────────────────────
def inspect_record_files():
    h("3) PT 기록 파일 후보 (json/md/csv) + pt_system 스크립트")
    kw = re.compile(r"(pt_system|workout|운동|식단|meal|diet|weight|체중|vital|바이탈|record|기록)", re.I)
    hits = []
    scan_roots = [OPENCLAW, os.path.join(HOME, "pt"), os.path.join(HOME, "pt_system")]
    for r in scan_roots:
        if not os.path.isdir(r):
            continue
        for dirpath, dirs, files in os.walk(r):
            dirs[:] = [d for d in dirs if d not in ("venv", ".venv", "node_modules", "__pycache__", ".git", "sessions")]
            for f in files:
                if kw.search(f) and f.endswith((".py", ".json", ".md", ".csv", ".sh")):
                    hits.append(os.path.join(dirpath, f))
    for p in sorted(set(hits))[:60]:
        try:
            size = os.path.getsize(p)
        except Exception:
            size = "?"
        print(f"   {p}  ({size}B)")
    if not hits:
        print("   해당 키워드 파일 없음.")
    # pt_system 스크립트가 있으면 앞부분 보여주기
    for p in sorted(set(hits)):
        if p.endswith(".py") and re.search(r"(record|기록|pt_system|save|insert)", os.path.basename(p), re.I):
            print(f"\n   ── SCRIPT HEAD: {p} ──")
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    print("   " + mask(fh.read(1800)).replace("\n", "\n   "))
            except Exception as e:
                print("   읽기 실패:", e)
            break


# ── 4. 대시보드 웹앱 위치 ────────────────────────────────────
def inspect_dashboard():
    h("4) 대시보드 웹앱 (mystatus-btr.duckdns.org) 위치 및 데이터 소스")
    # nginx / caddy 설정에서 mystatus 매핑
    print("  -- 리버스 프록시 설정에서 'mystatus' 검색 --")
    for conf in ["/etc/nginx", "/etc/caddy", os.path.join(HOME, ".config", "caddy")]:
        if os.path.isdir(conf):
            try:
                out = subprocess.run(
                    ["grep", "-rni", "mystatus", conf],
                    capture_output=True, text=True, timeout=15)
                if out.stdout.strip():
                    print(mask(out.stdout.strip()))
            except Exception as e:
                print("   grep 실패:", e)
    # systemd user/시스템 서비스
    print("\n  -- systemd 서비스 (mystatus/pt/dashboard/uvicorn/gunicorn) --")
    for scope in [["systemctl", "--user", "list-units", "--type=service", "--all", "--no-pager"],
                  ["systemctl", "list-units", "--type=service", "--all", "--no-pager"]]:
        try:
            out = subprocess.run(scope, capture_output=True, text=True, timeout=15)
            for line in out.stdout.splitlines():
                if re.search(r"(mystatus|pt|dashboard|uvicorn|gunicorn|fastapi|flask)", line, re.I):
                    print("   " + line.strip())
        except Exception:
            pass
    # 실행 중 프로세스
    print("\n  -- 실행 중 관련 프로세스 (포트/uvicorn/flask) --")
    try:
        out = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=15)
        for line in out.stdout.splitlines():
            if re.search(r"(mystatus|uvicorn|gunicorn|flask|fastapi|:80\b|duckdns)", line, re.I) \
               and "grep" not in line:
                print("   " + mask(line.strip())[:200])
    except Exception as e:
        print("   ps 실패:", e)
    # 리슨 포트
    print("\n  -- LISTEN 포트 (ss) --")
    try:
        out = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=15)
        print(mask(out.stdout.strip())[:1500])
    except Exception:
        try:
            out = subprocess.run(["netstat", "-tlnp"], capture_output=True, text=True, timeout=15)
            print(mask(out.stdout.strip())[:1500])
        except Exception as e:
            print("   실패:", e)
    # 홈에서 app.py/main.py 후보
    print("\n  -- 웹앱 소스 후보 (app.py/main.py/server.py, ~ 및 ~/mystatus 등) --")
    for r in [HOME, os.path.join(HOME, "mystatus"), os.path.join(HOME, "pt"), OPENCLAW]:
        if not os.path.isdir(r):
            continue
        for dirpath, dirs, files in os.walk(r):
            dirs[:] = [d for d in dirs if d not in ("venv", ".venv", "node_modules", "__pycache__", ".git", "sessions", "stock")]
            depth = dirpath[len(r):].count(os.sep)
            if depth > 3:
                dirs[:] = []
                continue
            for f in files:
                if f in ("app.py", "main.py", "server.py", "index.html", "dashboard.py"):
                    print(f"   {os.path.join(dirpath, f)}")


# ── 5. openclaw.json 에이전트/채널 설정 (마스킹) ─────────────
def inspect_config():
    h("5) openclaw.json — pt-trainer 에이전트 / 채널 설정 (마스킹)")
    cfg = os.path.join(OPENCLAW, "openclaw.json")
    if not os.path.isfile(cfg):
        print("  openclaw.json 없음:", cfg)
        return
    try:
        with open(cfg, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        print("  파싱 실패:", e)
        return

    # 채널 종류
    ch = data.get("channels", {})
    print("  -- channels 키 --")
    for k in ch.keys():
        print(f"   {k}")
    # 에이전트 목록 + pt 관련
    agents = data.get("agents", {})
    lst = agents.get("list", [])
    print("\n  -- agents.list (id/name/model 요약) --")
    for a in lst:
        aid = a.get("id") or a.get("name")
        model = a.get("model")
        print(f"   id={aid}  model={mask(json.dumps(model, ensure_ascii=False)) if model else '(default)'}")
    print("\n  -- agents.defaults.model --")
    print("   " + mask(json.dumps(agents.get("defaults", {}).get("model", {}), ensure_ascii=False))[:400])

    # pt-trainer 관련 라우팅/채널 매핑 있으면 통째로 (마스킹)
    print("\n  -- 'pt' 문자열 포함 설정 블록 (마스킹) --")
    raw = json.dumps(data, ensure_ascii=False, indent=1)
    for m in re.finditer(r'.{0,80}pt[-_]?trainer.{0,200}', raw, re.I):
        print("   ..." + mask(m.group(0)).replace("\n", " ") + "...")


def main():
    print("PT INSPECT — 서버 현황 진단 (읽기 전용, 비밀 마스킹)")
    print("HOME =", HOME, "| OPENCLAW =", OPENCLAW)
    safe(inspect_telegram)
    safe(inspect_db)
    safe(inspect_record_files)
    safe(inspect_dashboard)
    safe(inspect_config)
    print("\n" + "=" * 70)
    print("완료. 위 출력 전체를 복사해서 Claude 에게 붙여주세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()
