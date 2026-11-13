#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
newspaper_auto_pull.py — 서버의 신문 수집기(~/newspaper)를 GitHub 최신 코드로 자동으로 맞춘다.

[왜]
  openclaw 는 git-auto-pull.sh 가 1분마다 받아 오지만, 수집기 저장소
  (richdadtechtree/newspaper, 서버 ~/newspaper)는 자동으로 받는 장치가 없어서
  코드를 고쳐 올려도 서버에 들어가지 않았다(2026-11-13: 웹 버튼이
  "수집기가 예전 버전" 경고를 띄움). 사용자는 서버에 직접 들어가기 어렵다.
  → git-auto-pull.sh 가 매 tick 이 스크립트를 부른다.

[안전 규칙]  애매하면 아무것도 바꾸지 않고 로그만 남긴다.
  1. ~/newspaper 가 git 폴더이고 origin 이 richdadtechtree/newspaper 일 때만.
  2. 수집기가 돌고 있으면(app/main.py · run_daily.sh 실행 중) 이번엔 건너뜀
     — 실행 중인 bash 스크립트 파일을 바꾸면 이상하게 동작할 수 있다.
  3. '앞으로 감기(fast-forward)'만 한다. 서버에만 있는 커밋이 있거나 갈라졌으면 안 함.
  4. 서버에서 손으로 고친 파일(openclaw 패치 등)은 보존한다.
     - 새 코드가 그 파일을 안 바꾸면 그대로 둔 채 받는다
       (예: drive_uploader.py '오늘치 보관' 패치, run_daily.sh 마감 08:00).
     - 예외: app/naver_cafe.py 의 예전 '제목 필터' 패치는 새 코드에 같은 기능이
       들어 있으므로, 백업(.bak-autopull-시각)을 남기고 지운 뒤 받는다.
     - 그 밖에 새 코드와 겹치는 수정이 있으면 받지 않는다(로그에 파일 이름).
  5. 받은 뒤 파이썬 문법 검사(py_compile) + bash -n. 실패하면 예전 커밋으로 되돌리고
     지웠던 패치 파일도 복구한다.
  6. GitHub 확인은 5분에 한 번(NEWSPAPER_PULL_EVERY 초). 같은 경고는 1시간에 한 번만 로그.

[환경변수]
  NEWSPAPER_DIR            수집기 폴더 (기본 ~/newspaper)
  NEWSPAPER_GIT_BRANCH     받을 브랜치 (기본: 서버가 지금 쓰는 브랜치)
  NEWSPAPER_PULL_EVERY     GitHub 확인 간격 초 (기본 300)
  NEWSPAPER_AUTO_PULL=off  이 기능 끄기

[사용]
  python3 newspaper_auto_pull.py            # 평소(git-auto-pull.sh 가 부름)
  python3 newspaper_auto_pull.py --now      # 간격 무시하고 지금 확인
  python3 newspaper_auto_pull.py --status   # 지금 상태만 보기(아무것도 안 바꿈)
종료 코드: 0 = 정상(받음·최신·건너뜀) / 1 = 문제가 있어 안 받음(로그 확인)
표준 라이브러리만 사용 → 시스템 python3 로 실행 가능.
"""
import os
import re
import shutil
import subprocess
import sys
import time

REPO_RE = re.compile(r"github\.com[:/]richdadtechtree/newspaper(\.git)?/?$", re.I)
TITLE_FILE = "app/naver_cafe.py"
PATCHED_LINE = re.compile(r"is_match = bool\(date_pattern\.search\(title\)\) and _oc_title_ok\(title\)[^\n]*")


def only_title_patch(server_src, head_src):
    """서버 파일이 '받아 둔 원본 + openclaw 제목 필터 패치' 그대로인지(다른 손질은 없는지).

    patch-newspaper-title-filter.sh 는 ①is_match 줄 끝에 'and _oc_title_ok(title)' 를 붙이고
    ②파일 끝에 '# [openclaw 패치] …' 로 시작하는 함수를 붙인다. 둘을 걷어냈을 때 원본과
    똑같아야만 True — 그 밖에 서버에서 고친 게 있으면 지우지 않으려고.
    """
    idx = server_src.find("# [openclaw 패치]")
    if idx < 0 or "_oc_title_ok(title)" not in server_src:
        return False
    start = server_src.rfind("\n# ─", 0, idx)
    body = server_src[:start if start >= 0 else idx]
    body = PATCHED_LINE.sub("is_match = bool(date_pattern.search(title))", body, count=1)
    return body.rstrip() == head_src.rstrip()


RESULT = {"msg": "", "head": "", "branch": ""}       # 이번 실행 결과(이유) — --now 때 출력, 웹 버튼이 보여 줌


def note(msg, **kw):
    RESULT["msg"] = msg
    RESULT.update(kw)


def log(msg):
    print("[newspaper-pull] %s %s" % (time.strftime("%F %T"), msg), flush=True)


def git(d, *args, check=True):
    p = subprocess.run(["git", "-C", d] + list(args), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError("git %s 실패: %s" % (" ".join(args), (p.stderr or p.stdout).strip()[:300]))
    return p.stdout.strip()


def state_file(d, name):
    return os.path.join(d, ".git", "openclaw-autopull." + name)


def throttled(path, seconds):
    """path 의 기록 시각이 seconds 안이면 True. 아니면 지금 시각을 적고 False."""
    try:
        if time.time() - os.path.getmtime(path) < seconds:
            return True
    except OSError:
        pass
    try:
        with open(path, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass
    return False


def warn_once(d, key, msg):
    """같은 경고는 1시간에 한 번만(매분 로그가 쌓이지 않게)."""
    note(msg)
    if not throttled(state_file(d, "warn-" + key), 3600):
        log(msg)


def collector_running():
    """수집기(app/main.py 를 실행 중인 파이썬, 또는 run_daily.sh 를 실행 중인 bash)가 있으면 True.

    명령줄 '글자'를 통째로 찾으면(pgrep -f) 그 글자가 들어 있는 아무 셸 명령에도 걸린다
    → 프로세스의 실제 인자(/proc/<pid>/cmdline)를 하나씩 보고 판단한다.
    """
    me = os.getpid()
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == me:
            continue
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                args = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if len(args) < 2:
            continue
        prog = os.path.basename(args[0])
        for a in args[1:4]:                      # 실행 파일 바로 뒤 몇 개만(옵션 -u 등 고려)
            if a.startswith("-"):
                continue
            if prog.startswith("python") and a.replace("\\", "/").endswith("app/main.py"):
                return True
            if prog in ("bash", "sh") and a.endswith("scripts/run_daily.sh"):
                return True
            break
    return False


def syntax_ok(d):
    py = os.path.join(d, ".venv", "bin", "python")
    if not os.path.isfile(py):
        py = sys.executable
    files = []
    for root, _dirs, names in os.walk(os.path.join(d, "app")):
        files += [os.path.join(root, n) for n in names if n.endswith(".py")]
    if files:
        p = subprocess.run([py, "-m", "py_compile"] + files, capture_output=True, text=True)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout).strip()[:300]
    for sh in ("scripts/run_daily.sh",):
        path = os.path.join(d, sh)
        if os.path.isfile(path):
            p = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
            if p.returncode != 0:
                return False, (p.stderr or p.stdout).strip()[:300]
    return True, ""


def default_branch(d):
    m = re.search(r"ref: refs/heads/(\S+)\s+HEAD", git(d, "ls-remote", "--symref", "origin", "HEAD", check=False))
    return m.group(1) if m else ""


def run(d, branch=None, force_now=False, status_only=False, every=300):
    if not os.path.isdir(os.path.join(d, ".git")):
        note("서버의 %s 가 git 폴더가 아니라서 자동으로 받을 수 없어요 (GitHub 에서 받은 폴더가 아님)" % d)
        if status_only:
            log(RESULT["msg"])
        return 1
    url = git(d, "config", "--get", "remote.origin.url", check=False)
    if not REPO_RE.search(url or ""):
        warn_once(d, "origin", "수집기 폴더의 GitHub 주소가 richdadtechtree/newspaper 가 아님(%s) — 자동 받기 안 함"
                  % re.sub(r"//[^@/]+@", "//***@", url or "없음"))
        return 1
    current = git(d, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    head = git(d, "rev-parse", "HEAD")
    RESULT.update(head=head[:7], branch=current)
    if status_only:
        log("폴더 %s · 브랜치 %s · 지금 %s" % (d, current, head[:7]))
        dirty = git(d, "diff", "--name-only", "HEAD", check=False).split()
        log("서버에서 고친 파일: %s" % (", ".join(dirty) or "없음"))
        note("브랜치 %s · 커밋 %s" % (current, head[:7]))
        return 0

    if not force_now and throttled(state_file(d, "fetch"), every):
        note("")                                    # 5분 안 → 확인 안 함(기록도 안 바꿈)
        return 0
    if collector_running():
        note("수집기가 실행 중이라 끝난 뒤 받을게요")
        log(RESULT["msg"])
        try:
            os.remove(state_file(d, "fetch"))      # 끝나면 바로 다시 확인하도록
        except OSError:
            pass
        return 0

    def is_ancestor(a, b):
        return subprocess.run(["git", "-C", d, "merge-base", "--is-ancestor", a, b],
                              capture_output=True).returncode == 0

    # 어느 브랜치를 따라갈지: 지정값 > 서버가 쓰는 브랜치 > 저장소 기본 브랜치.
    # 서버 브랜치에 새 커밋이 없어도, 기본 브랜치가 '앞으로 감기'로 이어지면 기본 브랜치를 받는다.
    candidates = [branch] if branch else [b for b in (current if current != "HEAD" else "", default_branch(d)) if b]
    seen, remote, picked = set(), "", ""
    for b in candidates:
        if b in seen:
            continue
        seen.add(b)
        if subprocess.run(["git", "-C", d, "fetch", "--quiet", "origin", b], capture_output=True).returncode != 0:
            continue
        r = git(d, "rev-parse", "FETCH_HEAD")
        if r != head and is_ancestor(head, r):
            remote, picked = r, b
            break
        if not picked or (remote == head and r != head):
            remote, picked = r, b                   # 앞으로 감기는 안 되지만 이유를 알려 주려고 기억
                                                    # (서버 브랜치는 그대로인데 기본 브랜치가 다르면 그쪽 이유가 중요)
    if not picked:
        warn_once(d, "fetch", "GitHub 에서 %s 브랜치를 받아 오지 못했어요" % "/".join(candidates))
        return 1
    if remote == head:
        note("이미 최신이에요 (브랜치 %s · 커밋 %s)" % (current, head[:7]))
        return 0                                    # 이미 최신
    if is_ancestor(remote, head):
        warn_once(d, "ahead", "서버 쪽 커밋(%s)이 GitHub %s 보다 앞서 있어 자동 받기 안 함" % (head[:7], picked))
        return 1
    if not is_ancestor(head, remote):
        warn_once(d, "diverged", "서버는 '%s' 브랜치(%s)인데 GitHub 새 코드(%s %s)와 기록이 갈라져서 자동 받기 안 함"
                  % (current, head[:7], picked, remote[:7]))
        return 1
    if picked != current and current not in ("", "HEAD"):
        log("서버 브랜치 %s 에는 새 커밋이 없어 기본 브랜치 %s 를 받음" % (current, picked))

    changed_upstream = set(git(d, "diff", "--name-only", head, remote).splitlines())
    dirty = git(d, "diff", "--name-only", "HEAD").splitlines()     # 서버에서 고친(추적 중인) 파일
    backups = {}
    for f in dirty:
        if f not in changed_upstream:
            continue                                # 새 코드가 안 건드리는 파일 → 그대로 보존
        path = os.path.join(d, f)
        new_src = git(d, "show", "%s:%s" % (remote, f), check=False)
        with open(path, encoding="utf-8") as fh:
            server_src = fh.read()
        if f == TITLE_FILE and "_oc_title_ok" in new_src and \
                only_title_patch(server_src, git(d, "show", "%s:%s" % (head, f), check=False)):
            bak = "%s.bak-autopull-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
            shutil.copy2(path, bak)
            backups[f] = bak
            continue
        warn_once(d, "conflict", "서버에서 고친 %s 를 새 코드도 바꿈 — 겹쳐서 자동 받기 안 함" % f)
        return 1

    for f in backups:                               # 예전 제목 필터 패치 → 새 코드에 포함돼 있으니 지움
        git(d, "checkout", "--", f)
    try:
        git(d, "merge", "--ff-only", "--quiet", remote)
    except RuntimeError as e:
        for f, bak in backups.items():
            shutil.copy2(bak, os.path.join(d, f))
        warn_once(d, "merge", "받기 실패 — 그대로 둠: %s" % e)
        return 1

    ok, why = syntax_ok(d)
    if not ok:
        git(d, "reset", "--keep", head, check=False)    # 서버에서 고친 다른 파일은 보존하며 되돌림
        for f, bak in backups.items():
            shutil.copy2(bak, os.path.join(d, f))
        warn_once(d, "syntax", "새 코드 문법 검사 실패 → 예전(%s)으로 되돌림: %s" % (head[:7], why))
        return 1

    msg = "수집기 코드 받음: %s → %s (%s)" % (head[:7], remote[:7], ", ".join(sorted(changed_upstream))[:200])
    if backups:
        msg += " · 예전 제목 필터 패치는 새 코드에 포함돼 지움(백업 %s)" % ", ".join(
            os.path.basename(b) for b in backups.values())
    log(msg)
    note(msg, head=remote[:7])
    return 0


def status_path():
    default = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "newspaper-pull.json")
    return os.path.expanduser(os.getenv("NEWSPAPER_PULL_STATUS", default))


def save_status(code):
    """웹(🔁 버튼)이 읽을 수 있게 마지막 결과를 파일로 남긴다(5분 안이라 확인 안 한 tick 은 안 씀)."""
    if not RESULT["msg"]:
        return
    try:
        import json
        path = status_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(RESULT, code=code, at=time.strftime("%F %T")), f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def main(argv):
    if os.getenv("NEWSPAPER_AUTO_PULL", "").strip().lower() in ("off", "0", "false", "no"):
        return 0
    d = os.path.expanduser(os.getenv("NEWSPAPER_DIR", "~/newspaper"))
    try:
        every = int(os.getenv("NEWSPAPER_PULL_EVERY", "300"))
    except ValueError:
        every = 300
    try:
        code = run(d, os.getenv("NEWSPAPER_GIT_BRANCH") or None,
                   force_now="--now" in argv, status_only="--status" in argv, every=every)
    except Exception as e:                          # 어떤 오류도 openclaw 자동 받기를 막지 않게
        note("오류(아무것도 안 바꿈): %s" % e)
        try:
            warn_once(d, "error", RESULT["msg"])
        except Exception:
            log(RESULT["msg"])
        code = 1
    if "--status" not in argv:
        save_status(code)
    if "--now" in argv or "--status" in argv:
        print("결과: " + (RESULT["msg"] or "확인 안 함"), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
