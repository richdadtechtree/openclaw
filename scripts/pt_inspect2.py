#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pt_inspect2.py — 기존 PT 시스템(/home/ubuntu/pt_system) 소스 덤프 (읽기 전용, 마스킹)

DB 구조는 이미 파악됨. 이번엔 '소스 코드'가 목표:
  - 텔레그램 → raw_messages 수집/파싱 로직 (슬랙 입력으로 바꿀 지점)
  - dashboard/app.py 의 DB 경로 (빈 dashboard/pt_data.db 버그 확인)
  - 실행 구조(bot/scheduler/main), 의존성

안전: 읽기만. 토큰/키 자동 마스킹. venv/backups/__pycache__/*.db 는 건너뜀.

사용:  python3 ~/.openclaw/scripts/pt_inspect2.py
       (출력 전체를 복사해서 Claude 에게 붙여넣기)
"""
import os
import re

ROOT = os.path.expanduser("~/pt_system")

SECRET_PATTERNS = [
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"), "<TELEGRAM_TOKEN>"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "<SLACK_TOKEN>"),
    (re.compile(r"\bxapp-[A-Za-z0-9-]{10,}\b"), "<SLACK_APP_TOKEN>"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"), "<GEMINI_KEY>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "<OPENAI_KEY>"),
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "<HEX_SECRET>"),
    (re.compile(r'((?:token|secret|key|password|authorization)\s*[=:]\s*["\']?)[^"\'\s]{12,}', re.I),
        r"\1<REDACTED>"),
]


def mask(t):
    if not t:
        return t
    for pat, repl in SECRET_PATTERNS:
        t = pat.sub(repl, t)
    return t


SKIP_DIRS = {"venv", ".venv", "node_modules", "__pycache__", ".git", "backups", ".mypy_cache"}
SHOW_EXT = (".py", ".txt", ".service", ".html", ".sh", ".cfg", ".ini", ".toml", ".md")
MAX_FILE = 6000


def tree():
    print("=" * 70)
    print("### 파일 트리 (venv/backups/*.db 제외)")
    print("=" * 70)
    if not os.path.isdir(ROOT):
        print("경로 없음:", ROOT)
        return []
    files = []
    for dp, dirs, fs in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        depth = dp[len(ROOT):].count(os.sep)
        indent = "  " * depth
        print(f"{indent}{os.path.basename(dp) or ROOT}/")
        for f in sorted(fs):
            p = os.path.join(dp, f)
            try:
                sz = os.path.getsize(p)
            except Exception:
                sz = "?"
            print(f"{indent}  {f}  ({sz}B)")
            if f.endswith(SHOW_EXT) and not f.endswith(".db"):
                files.append(p)
    return files


def dump(files):
    # 우선순위: dashboard/app.py, DB 경로/텔레그램 관련 먼저
    def score(p):
        b = p.lower()
        s = 0
        if "dashboard" in b and b.endswith("app.py"):
            s -= 100
        if any(k in b for k in ("bot", "telegram", "ingest", "parse", "main", "scheduler", "db", "record")):
            s -= 50
        if b.endswith(".py"):
            s -= 10
        return s
    for p in sorted(files, key=score):
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                data = fh.read(MAX_FILE)
        except Exception as e:
            print(f"\n[읽기 실패] {p}: {e}")
            continue
        rel = os.path.relpath(p, ROOT)
        print("\n" + "=" * 70)
        print(f"### FILE: pt_system/{rel}  ({os.path.getsize(p)}B)")
        print("=" * 70)
        print(mask(data))
        if os.path.getsize(p) > MAX_FILE:
            print(f"...[{os.path.getsize(p) - MAX_FILE}B 더 있음, 생략]")


def db_path_hints():
    print("\n" + "=" * 70)
    print("### DB 경로/슬랙/텔레그램 참조 grep")
    print("=" * 70)
    pat = re.compile(r"(pt_data\.db|sqlite3\.connect|\.db['\"]|SLACK|TELEGRAM|chat_id|bot|raw_messages)", re.I)
    for dp, dirs, fs in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            if not f.endswith((".py", ".sh", ".txt", ".service")):
                continue
            p = os.path.join(dp, f)
            try:
                for i, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                    if pat.search(line):
                        rel = os.path.relpath(p, ROOT)
                        print(f"  pt_system/{rel}:{i}: {mask(line.rstrip())[:160]}")
            except Exception:
                pass


def env_keys():
    print("\n" + "=" * 70)
    print("### .env 키 이름만 (값 제외)")
    print("=" * 70)
    for name in (".env", ".env.local"):
        p = os.path.join(ROOT, name)
        if os.path.isfile(p):
            print(f"  [{name}]")
            for line in open(p, encoding="utf-8", errors="replace"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    print("   ", line.split("=", 1)[0])


def main():
    print("PT INSPECT 2 — 기존 pt_system 소스 덤프 (읽기 전용, 마스킹)")
    print("ROOT =", ROOT)
    files = tree()
    env_keys()
    db_path_hints()
    dump(files)
    print("\n" + "=" * 70)
    print("완료. 위 출력 전체를 복사해서 Claude 에게 붙여주세요.")
    print("=" * 70)


if __name__ == "__main__":
    main()
