#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retention_cleanup.py — 날짜별로 쌓이는 자료의 **보관 기간을 한 곳에서** 관리한다.

[왜 만들었나]
신문 관련 자료가 서버 여러 곳에 날짜별로 쌓이는데, 지우는 규칙이 제각각이었다.

    ~/.openclaw/news_cache/<날짜>/        사진·PDF   → news_sync.py 가 '최근 N개 폴더'만 남김
    ~/.openclaw/slack_logs/<날짜>.jsonl   요약 텍스트 → 지우는 규칙이 아예 없음(무한 증가)
    ~/.openclaw/news_marks/<날짜>...      형광펜 잔재 → 2026-09-17 이후 아무도 안 쓰는데 남아 있음

'최근 N개 폴더' 방식은 신문이 평일에만 올라와서 **달력으로는 9~10일 전까지** 남는 등
예측이 어려웠다. 그래서 전부 **달력 날짜 기준**으로 통일하고 규칙을 이 파일에 모았다.

[기본 정책]  (2026-09-19 사용자 결정)
    news_cache  14일  — 용량의 99% 를 차지한다(하루 15~35MB). 2주만 남긴다.
    slack_logs   0일  — 0 = 무제한. 텍스트라 하루 수십~수백 KB 뿐이고,
                        지우면 지난 브리핑을 웹(:8000 /slack)에서 다시 못 본다.
    news_marks  14일  — 이제 안 쓰는 잔재라 정리 대상.

[안전장치]
  · 삭제 대상은 **이름이 정확히 YYYY-MM-DD 인 것만**. 그 외 파일·폴더는 절대 손대지 않는다.
  · 각 폴더의 **가장 최근 날짜 1개는 무조건 남긴다**(--no-keep-latest 로 해제).
    신문이 며칠 안 올라온 뒤 청소가 돌아도 웹의 '가장 최근 보기' 가 빈손이 되지 않게.
  · 경로가 홈 디렉터리 밑이 아니면 거부한다(설정 실수로 엉뚱한 곳을 지우는 사고 방지).
  · `--dry-run` 으로 "지울 목록"만 먼저 볼 수 있다.

[사용법]
    python3 ~/.openclaw/scripts/retention_cleanup.py --status      # 현황만 보기(안 지움)
    python3 ~/.openclaw/scripts/retention_cleanup.py --dry-run     # 지울 것 미리보기
    python3 ~/.openclaw/scripts/retention_cleanup.py               # 실제 정리
    python3 ~/.openclaw/scripts/retention_cleanup.py --only news_cache --days 7

외부 라이브러리 없음 → 시스템 python3 로 그냥 돌아간다(requests 함정 없음).
cron 에 따로 등록할 필요도 없다. `news_sync.py` 가 30분마다 돌면서 이 파일을 불러 쓴다.

[종료 코드]  0 정상 / 1 오류
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 이름이 딱 이 모양인 것만 건드린다. (2026-09-02 / 2026-09-02.jsonl)
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class Target(object):
    """정리 대상 한 종류를 설명하는 값 꾸러미."""

    def __init__(self, key, default_dir, dir_env, days_env, default_days, label, note=""):
        self.key = key                    # --only 에서 쓰는 이름
        self.default_dir = default_dir    # 기본 경로
        self.dir_env = dir_env            # 경로를 바꾸는 환경변수 이름
        self.days_env = days_env          # 보관일수를 바꾸는 환경변수 이름
        self.default_days = default_days  # 기본 보관일수 (0 = 무제한)
        self.label = label                # 사람이 읽을 설명
        self.note = note

    def path(self):
        return os.path.expanduser(os.getenv(self.dir_env, self.default_dir))

    def days(self):
        """보관일수. 환경변수가 이상하면 기본값으로 되돌린다(청소가 멈추지 않게)."""
        raw = os.getenv(self.days_env)
        if raw is None or raw.strip() == "":
            return self.default_days
        try:
            n = int(raw)
        except ValueError:
            print("[retention] %s 값이 숫자가 아닙니다(%r) → 기본 %d일 사용"
                  % (self.days_env, raw, self.default_days), file=sys.stderr)
            return self.default_days
        return max(0, n)


TARGETS = [
    Target("news_cache", "~/.openclaw/news_cache", "NEWS_CACHE_DIR",
           "NEWS_CACHE_KEEP_DAYS", 14, "신문 사진·PDF 캐시",
           "하루 15~35MB — 용량의 대부분"),
    Target("slack_logs", "~/.openclaw/slack_logs", "SLACK_LOG_DIR",
           "SLACK_LOG_KEEP_DAYS", 0, "브리핑·알림 텍스트 로그",
           "0 = 무제한. 지우면 지난 브리핑을 웹에서 못 본다"),
    Target("news_marks", "~/.openclaw/news_marks", "NEWS_MARKS_DIR",
           "NEWS_MARKS_KEEP_DAYS", 14, "형광펜 잔재(지금은 안 씀)",
           "2026-09-17 이후 서버 저장을 하지 않는다"),
]
BY_KEY = dict((t.key, t) for t in TARGETS)


# ────────────────────────────────────────────────────────────────── 날짜 계산

def today_kst():
    return datetime.now(KST).date()


def cutoff_for(days, today=None):
    """이 날짜부터는 남긴다. days=14 → 오늘 포함 14일치 보관."""
    today = today or today_kst()
    return today - timedelta(days=days - 1)


def parse_date_name(name):
    """'2026-09-02' 또는 '2026-09-02.jsonl' 에서 날짜를 꺼낸다. 아니면 None."""
    stem = name
    # 확장자가 여러 개 붙어도(.json.bak) 첫 10글자만 날짜면 인정하지 않는다 — 엄격하게 간다.
    if "." in name:
        stem = name.split(".", 1)[0]
    m = DATE_RE.match(stem)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    except ValueError:      # 2026-02-31 같은 없는 날짜
        return None


# ────────────────────────────────────────────────────────── 크기 재기 / 지우기

def measure(path):
    """
    (실제 바이트, 심볼릭 링크 개수) 를 돌려준다.

    ⚠️ news_cache 안의 사진은 수집기 원본을 가리키는 **심볼릭 링크**일 수 있다.
       링크를 지워도 원본은 그대로라 디스크가 비지 않는다 → 링크는 0바이트로 세고
       개수만 따로 알려서 "절약했다"고 착각하지 않게 한다.
    """
    total, links = 0, 0
    if os.path.islink(path):
        return 0, 1
    if os.path.isfile(path):
        try:
            return os.lstat(path).st_size, 0
        except OSError:
            return 0, 0
    for root, dirs, files in os.walk(path):
        # 링크로 된 하위 폴더를 따라 들어가면 엉뚱한 곳 크기를 센다 → 막는다.
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for name in files:
            p = os.path.join(root, name)
            if os.path.islink(p):
                links += 1
                continue
            try:
                total += os.lstat(p).st_size
            except OSError:
                pass
    return total, links


def remove(path):
    """파일·폴더·심볼릭 링크를 상황에 맞게 지운다. 실패하면 사유를 돌려준다."""
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)               # 링크는 링크만 지워진다(원본 안전)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        return None
    except OSError as e:
        return str(e)


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f%s" % (n, unit) if unit == "B" else "%.1f%s" % (n, unit)
        n /= 1024


# ─────────────────────────────────────────────────────────────────── 본체

def scan(target):
    """대상 폴더에서 '날짜 이름' 항목만 골라 [(날짜, 경로)] 로 돌려준다(오름차순)."""
    root = target.path()
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        d = parse_date_name(name)
        if d is not None:
            found.append((d, os.path.join(root, name)))
    found.sort()
    return found


def _under_home(path):
    """홈 밑인지 확인. 설정 실수로 '/' 나 '/etc' 를 지우는 사고를 원천 차단한다."""
    home = os.path.realpath(os.path.expanduser("~"))
    real = os.path.realpath(path)
    return real != home and (real + os.sep).startswith(home + os.sep)


def sweep(target, days=None, dry_run=False, verbose=True, keep_latest=True, today=None):
    """
    대상 하나를 정리한다. 반환: dict(삭제개수, 절약바이트, 링크개수, 남은개수)
    days=0 이면 '무제한 보관' 이라 아무것도 지우지 않는다.
    """
    days = target.days() if days is None else days
    entries = scan(target)
    result = {"key": target.key, "days": days, "removed": 0, "freed": 0,
              "links": 0, "kept": len(entries), "errors": []}
    if not entries:
        return result
    if days <= 0:
        if verbose:
            print("  · %-11s 무제한 보관 — %d개 그대로" % (target.key, len(entries)))
        return result

    root = target.path()
    if not _under_home(root):
        result["errors"].append("홈 밖 경로라 건너뜀: %s" % root)
        print("[retention] ⚠️ %s" % result["errors"][-1], file=sys.stderr)
        return result

    cutoff = cutoff_for(days, today)
    latest = entries[-1][0] if keep_latest else None

    for d, path in entries:
        if d >= cutoff:
            continue
        if latest is not None and d == latest:
            if verbose:
                print("  · %-11s %s 는 가장 최근이라 남김" % (target.key, d))
            continue
        size, links = measure(path)
        if dry_run:
            print("  [미리보기] 지울 것: %s (%s%s)"
                  % (path, human(size), "" if not links else ", 링크 %d개" % links))
        else:
            err = remove(path)
            if err:
                result["errors"].append("%s: %s" % (path, err))
                print("[retention] ⚠️ 삭제 실패 %s: %s" % (path, err), file=sys.stderr)
                continue
            if verbose:
                print("  🗑 %-11s %s 삭제 (%s)" % (target.key, d, human(size)))
        result["removed"] += 1
        result["freed"] += size
        result["links"] += links

    result["kept"] = len(entries) - result["removed"]
    return result


def sweep_all(days=None, only=None, dry_run=False, verbose=True, keep_latest=True, today=None):
    """모든 대상을 정리하고 요약을 돌려준다. news_sync.py 가 이 함수를 부른다."""
    picked = [t for t in TARGETS if not only or t.key in only]
    results = [sweep(t, days=days, dry_run=dry_run, verbose=verbose,
                     keep_latest=keep_latest, today=today) for t in picked]
    removed = sum(r["removed"] for r in results)
    freed = sum(r["freed"] for r in results)
    if verbose and removed:
        print("[retention] 정리 %d개 · 확보 %s%s"
              % (removed, human(freed), " (미리보기라 실제로는 안 지움)" if dry_run else ""))
    return results


def status(today=None):
    """지우지 않고 현황만 보여준다 — '지금 며칠치가 남아 있나' 확인용."""
    today = today or today_kst()
    print("오늘(KST): %s\n" % today)
    for t in TARGETS:
        entries = scan(t)
        days = t.days()
        print("■ %s — %s" % (t.key, t.label))
        print("   경로     : %s" % t.path())
        print("   보관정책 : %s   (환경변수 %s)"
              % ("무제한" if days <= 0 else "%d일" % days, t.days_env))
        if t.note:
            print("   메모     : %s" % t.note)
        if not entries:
            print("   남은 자료: 없음\n")
            continue
        total, links = 0, 0
        for _, path in entries:
            s, l = measure(path)
            total += s
            links += l
        oldest, newest = entries[0][0], entries[-1][0]
        print("   남은 자료: %d개 · %s ~ %s (가장 오래된 것 %d일 전) · %s%s"
              % (len(entries), oldest, newest, (today - oldest).days, human(total),
                 "" if not links else " + 링크 %d개(원본은 다른 곳)" % links))
        if days > 0:
            over = [d for d, _ in entries if d < cutoff_for(days, today)]
            if over:
                print("   ⏳ 다음 정리 때 지워질 것: %d개 (%s ~ %s)"
                      % (len(over), over[0], over[-1]))
        print("")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="날짜별로 쌓이는 자료를 보관 기간에 맞게 정리한다.")
    ap.add_argument("--days", type=int, default=None,
                    help="모든 대상에 이 보관일수를 강제 적용 (0=무제한)")
    ap.add_argument("--only", default="",
                    help="대상 지정(쉼표): %s" % ", ".join(BY_KEY))
    ap.add_argument("--dry-run", action="store_true", help="지우지 않고 목록만 보기")
    ap.add_argument("--status", action="store_true", help="현황만 보기(안 지움)")
    ap.add_argument("--quiet", action="store_true", help="조용히 (cron 용)")
    ap.add_argument("--no-keep-latest", action="store_true",
                    help="가장 최근 1개도 보호하지 않는다(기본은 보호)")
    args = ap.parse_args()

    load_env_file()

    if args.status:
        return status()

    only = set(x.strip() for x in args.only.split(",") if x.strip())
    unknown = only - set(BY_KEY)
    if unknown:
        print("모르는 대상: %s (가능: %s)" % (", ".join(sorted(unknown)), ", ".join(BY_KEY)),
              file=sys.stderr)
        return 1

    results = sweep_all(days=args.days, only=only, dry_run=args.dry_run,
                        verbose=not args.quiet, keep_latest=not args.no_keep_latest)
    return 1 if any(r["errors"] for r in results) else 0


def load_env_file():
    """~/.openclaw/.env 의 KEY=VALUE 를 (아직 없는 것만) 환경변수로 올린다.

    cron 은 환경이 거의 비어 있어서, .env 에 적어둔 NEWS_CACHE_KEEP_DAYS 같은
    설정이 그냥은 안 읽힌다. news_sync.py 와 같은 방식으로 직접 읽어 준다.
    """
    path = os.path.expanduser(os.getenv("OPENCLAW_ENV_FILE", "~/.openclaw/.env"))
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
