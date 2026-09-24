#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
news_sync.py — 구글 드라이브의 "그날 신문"(사진 + PDF)을 서버 로컬 캐시로 내려받는다.

[왜 필요한가]
매일 06:01(KST)에 구글 드라이브가 이렇게 채워진다.

    내 드라이브 / 신문스크랩 / 2026-09 / 2026-09-15 /
        2026-09-15.pdf      ← 그날 신문 전체 PDF
        01.jpg … 30.gif     ← 신문 페이지 사진
        metadata.json       ← 원문(네이버 카페) 주소·장수 등 기록

다이제스트 웹(포트 8000, /slack)에서 이 파일을 바로 받게 하려면,
웹 요청이 올 때마다 드라이브를 찌르는 것보다 **하루 한 번 미리 내려받아
로컬에 캐시**해 두는 편이 훨씬 빠르고 안전하다(인증·쿼터·지연 문제 없음).
이 스크립트가 그 "미리 받아두는" 역할이고, 웹 서버는 캐시만 읽는다.

[어떻게 가져오나]
서버에 이미 구글 인증이 끝난 `gog`(gogcli) CLI 를 그대로 재사용한다.
새 API 키를 발급할 필요가 없다. 다만 gog 의 drive 하위 명령 이름/플래그가
버전마다 다를 수 있어서, **여러 후보 명령을 순서대로 시도해 보고 처음
성공한 형태를 기억**한다(.gog_shape.json). 전부 실패하면 --probe 로
`gog drive --help` 를 찍어볼 수 있게 안내한다.

[사용법]
    python3 ~/.openclaw/scripts/news_sync.py              # 오늘(KST)
    python3 ~/.openclaw/scripts/news_sync.py 2026-09-14   # 특정 날짜
    python3 ~/.openclaw/scripts/news_sync.py --force      # 캐시 무시하고 다시 받기
    python3 ~/.openclaw/scripts/news_sync.py --probe      # gog 사용법 확인(진단)

시스템 python3 로 충분하다(외부 라이브러리 없음 → requests 함정 없음).

[종료 코드]  0 성공 / 2 아직 안 올라옴(정상적인 "없음") / 1 오류
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 드라이브 '신문스크랩' 최상위 폴더 ID. 폴더를 옮겼다면 NEWS_DRIVE_ROOT_ID 로 덮어쓴다.
DEFAULT_ROOT_ID = "1Alujf1JqgEl2C5OaEt1F7MOS9wkjUJsx"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}

# gog 가 쓰는 keyring(구글 토큰 금고) 암호는 게이트웨이 systemd 유닛에만 있다.
# cron 에서 돌 때를 대비해 아래 접두어로 시작하는 변수만 골라 가져온다(값은 절대 출력 안 함).
GOG_ENV_PREFIXES = ("GOG", "KEYRING", "PYTHON_KEYRING", "GOOGLE", "XDG_")


class GogError(RuntimeError):
    """gog 명령을 어떤 형태로도 성공시키지 못했을 때."""


# ───────────────────────────────────────────────────────────── 경로/환경 준비

def cache_root():
    """캐시 최상위 폴더. 기본 ~/.openclaw/news_cache (git 추적 제외)."""
    return os.path.expanduser(os.getenv("NEWS_CACHE_DIR", "~/.openclaw/news_cache"))


def day_dir(date):
    return os.path.join(cache_root(), date)


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def load_env_file():
    """~/.openclaw/.env 의 KEY=VALUE 를 (아직 없는 것만) 환경변수로 올린다."""
    path = os.path.expanduser(os.getenv("OPENCLAW_ENV_FILE", "~/.openclaw/.env"))
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


def load_gateway_env(unit=None):
    """
    systemd 유저 유닛(openclaw-gateway)의 Environment= 에서 gog 관련 변수를 빌려온다.
    cron 에는 그 변수가 없어서 gog 가 "keyring locked" 로 실패하는 것을 막는 장치.
    """
    unit = unit or os.getenv("OPENCLAW_GATEWAY_UNIT", "openclaw-gateway")
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", unit, "-p", "Environment", "--value"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return
    if not out:
        return
    try:
        tokens = shlex.split(out)
    except ValueError:
        tokens = out.split()
    for tok in tokens:
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        if k and k not in os.environ and k.startswith(GOG_ENV_PREFIXES):
            os.environ[k] = v


def gog_bin():
    """gog 실행파일 위치. 게이트웨이 PATH 에 linuxbrew 가 없어 절대경로가 안전하다."""
    for c in (os.getenv("GOG_BIN", ""),
              "/home/linuxbrew/.linuxbrew/bin/gog",
              shutil.which("gog") or ""):
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return ""


def run_gog(args, cwd=None, timeout=300, binary=False):
    """gog 를 한 번 실행하고 (종료코드, stdout, stderr) 를 돌려준다."""
    exe = gog_bin()
    if not exe:
        raise GogError("gog 실행파일을 찾지 못했습니다. GOG_BIN 환경변수로 경로를 지정하세요.")
    try:
        p = subprocess.run([exe] + list(args), cwd=cwd, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.TimeoutExpired:
        return 124, (b"" if binary else ""), "시간 초과(%ss)" % timeout
    out = p.stdout if binary else p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    return p.returncode, out, err


# ─────────────────────────────────────────── gog 명령 "형태" 자동 탐색 + 기억

# 폴더 안 목록 뽑기 후보들. {q}=검색식, {parent}=폴더ID 자리.
LIST_SHAPES = [
    # ✅ gog v0.34.1 `drive ls` 도움말로 확인된 정답:
    #      --parent=<폴더ID>   폴더 안 목록
    #      --max=20            ⚠️ 기본이 20 이라 하루치(32개)가 잘린다 → 크게 지정
    #      -j                  JSON 출력
    ["drive", "ls", "--parent", "{parent}", "--max", "1000", "-j"],
    ["drive", "ls", "--parent={parent}", "--max=1000", "-j"],          # = 로 붙이는 표기
    ["-j", "drive", "ls", "--parent", "{parent}", "--max", "1000"],    # 전역 플래그를 앞에
    ["drive", "ls", "--parent", "{parent}", "--max", "1000", "--results-only", "-j"],
    ["drive", "ls", "--query", "{q}", "--max", "1000", "-j"],
    # 플래그 이름이 다른 버전 대비(구버전/신버전 폴백)
    ["drive", "ls", "--parent", "{parent}", "-j"],
    ["drive", "ls", "--folder", "{parent}", "-j"],
    ["drive", "ls", "--id", "{parent}", "-j"],
    ["drive", "ls", "-q", "{q}", "-j"],
    ["drive", "list", "-q", "{q}", "-j"],
    ["drive", "list", "--query", "{q}", "-j"],
    ["drive", "files", "list", "-q", "{q}", "-j"],
    ["drive", "ls", "{parent}", "-j"],
]

# 한 번에 몇 개까지 돌려주는지가 버전마다 다르다(기본 20~100 인 경우가 흔하다).
# 하루치 폴더에 파일이 32개쯤 되므로, 결과 개수가 '딱 떨어지는 수'면 잘렸을 가능성을
# 의심하고 아래 플래그를 붙여 다시 시도한다.
SUSPICIOUS_COUNTS = {10, 20, 25, 30, 50, 100}
LIMIT_FLAGS = [
    ["--limit", "1000"],
    ["--page-size", "1000"],
    ["--max", "1000"],
    ["--max-results", "1000"],
    ["--all"],
]

# 파일 하나 내려받기 후보들. {id}=파일ID, {out}=저장 경로.
# stdout 으로 내용을 뱉는 형태는 따로 표시(마지막 원소가 ">" 이면 stdout 저장).
DOWNLOAD_SHAPES = [
    ["drive", "download", "{id}", "-o", "{out}"],
    ["drive", "download", "{id}", "--output", "{out}"],
    ["drive", "download", "{id}", "--dest", "{out}"],
    ["drive", "download", "{id}", "--path", "{out}"],
    ["drive", "download", "--id", "{id}", "--out", "{out}"],
    ["drive", "download", "{id}", "{out}"],
    ["drive", "download", "{id}"],
    ["drive", "get", "{id}", "-o", "{out}"],
    ["drive", "get", "{id}"],
    ["drive", "cat", "{id}", ">"],
]


def shape_store_path():
    return os.path.join(cache_root(), ".gog_shape.json")


def load_shapes():
    try:
        with open(shape_store_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_shape(kind, shape):
    """성공한 명령 형태를 기억해 다음 실행부터 곧바로 쓰게 한다."""
    data = load_shapes()
    data[kind] = shape
    os.makedirs(cache_root(), exist_ok=True)
    tmp = shape_store_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, shape_store_path())


def ordered_shapes(kind, all_shapes):
    """기억해 둔 형태를 맨 앞에 두고, 나머지를 뒤에 붙인 시도 순서."""
    saved = load_shapes().get(kind)
    if saved and saved in all_shapes:
        return [saved] + [s for s in all_shapes if s != saved]
    if saved:
        return [saved] + all_shapes
    return list(all_shapes)


def fill(shape, **kw):
    """템플릿의 {q}/{parent}/{id}/{out} 자리를 실제 값으로 바꾼다."""
    return [part.format(**kw) for part in shape if part != ">"]


# ─────────────────────────────────────────────────── gog 출력(JSON) 해석하기

def normalize_entry(e):
    """gog 버전마다 키 이름이 달라서(id/fileId, name/title …) 하나로 맞춘다."""
    if not isinstance(e, dict):
        return None
    fid = e.get("id") or e.get("fileId") or e.get("Id") or e.get("ID")
    name = e.get("name") or e.get("title") or e.get("Name") or e.get("Title")
    if not fid or not name:
        return None
    mime = e.get("mimeType") or e.get("mime_type") or e.get("MimeType") or e.get("mime") or ""
    size = e.get("size") or e.get("fileSize") or e.get("Size") or 0
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 0
    return {"id": str(fid), "name": str(name), "mime": str(mime), "size": size}


def _find_file_list(obj, depth=0):
    """
    응답이 {"result":{"files":[…]}} 처럼 몇 겹으로 싸여 있어도 '파일처럼 생긴 목록'을 찾아낸다.
    (gog 버전마다 봉투 모양이 달라서, 키 이름에 기대지 않는 마지막 안전장치.)
    """
    if depth > 4 or not isinstance(obj, dict):
        return None
    for v in obj.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and normalize_entry(v[0]):
            return v
    for v in obj.values():
        found = _find_file_list(v, depth + 1)
        if found:
            return found
    return None


def parse_listing(text):
    """
    gog 출력이 JSON 배열이든, {"files":[…]} 든, 한 줄에 하나씩(NDJSON)이든 받아낸다.
    반환: (해석 성공 여부, 파일 목록)  ← 빈 폴더와 '해석 실패'를 구분하기 위해 둘로 나눔
    """
    text = (text or "").strip()
    if not text:
        return False, []
    try:
        data = json.loads(text)
    except Exception:
        rows = []
        ok = False
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                row = normalize_entry(json.loads(line))
            except Exception:
                continue
            ok = True
            if row:
                rows.append(row)
        return ok, rows

    if isinstance(data, dict):
        # gog 는 {"files":[…], "nextPageToken":…} 처럼 '봉투'에 담아 주는데
        # 봉투 키 이름이 버전마다 다르다. 아는 이름을 먼저 보고, 없으면
        # 값들 중 '파일처럼 생긴 딕셔너리들의 리스트'를 찾아낸다.
        picked = None
        for key in ("files", "items", "data", "results", "entries", "value", "records"):
            if isinstance(data.get(key), list):
                picked = data[key]
                break
        if picked is None:
            picked = _find_file_list(data)
        if picked is None:
            one = normalize_entry(data)
            return True, ([one] if one else [])
        data = picked
    if not isinstance(data, list):
        return False, []
    return True, [r for r in (normalize_entry(e) for e in data) if r]


def short_err(err, limit=320):
    """긴 오류 메시지를 줄이되, 진짜 이유가 있는 '뒤쪽'을 반드시 남긴다."""
    e = " ".join((err or "").split())
    if not e:
        return "(메시지 없음)"
    if len(e) <= limit:
        return e
    # URL 쿼리스트링은 통째로 접어서 자리를 아낀다
    e = re.sub(r'(https?://[^\s"?]+)\?[^\s"]*', r'\1?…', e)
    if len(e) <= limit:
        return e
    return e[:140] + " …(중략)… " + e[-160:]


def _try_list(shape, q, parent_id):
    """명령 형태 하나로 목록을 시도. (성공여부, 파일목록, 오류메시지)"""
    rc, out, err = run_gog(fill(shape, q=q, parent=parent_id))
    if rc != 0:
        return False, [], short_err(err or out)
    ok, files = parse_listing(out)
    if not ok:
        return False, [], "출력을 JSON 으로 해석하지 못함: " + short_err(out, 200)
    return True, files, ""


def list_children(parent_id):
    """폴더 하나의 바로 아래 항목 목록."""
    q = "'%s' in parents and trashed = false" % parent_id
    errors = []          # (시도한 명령, 오류) — 전부 모아 두었다가 실패 시 함께 보여준다
    for shape in ordered_shapes("list", LIST_SHAPES):
        ok, files, err = _try_list(shape, q, parent_id)
        if not ok:
            errors.append((" ".join(fill(shape, q=q, parent=parent_id)), err))
            continue

        # 결과 개수가 '딱 떨어지는 수'(20·50·100…)면 페이지 제한에 걸려 잘렸을 수 있다.
        # 개수 제한 플래그를 붙여 다시 물어보고, 더 많이 나오면 그 형태를 쓴다.
        if len(files) in SUSPICIOUS_COUNTS:
            for extra in LIMIT_FLAGS:
                wider = shape + extra
                ok2, files2, _ = _try_list(wider, q, parent_id)
                if ok2 and len(files2) > len(files):
                    save_shape("list", wider)
                    return files2

        save_shape("list", shape)
        return files
    # 구글 인증이 끊긴 경우는 후보를 아무리 바꿔도 소용없다 → 바로 알려준다.
    joined = " ".join(e for _c, e in errors)
    if "invalid_grant" in joined or "cannot fetch token" in joined or "oauth2" in joined:
        raise GogError(
            "구글 인증이 만료됐습니다 (oauth2: invalid_grant).\n"
            "  명령 문법은 정상입니다 — 저장된 '자동 재로그인 열쇠(리프레시 토큰)'가 무효화된 상태라\n"
            "  드라이브·캘린더·Gmail 등 gog 를 쓰는 기능이 모두 같이 막힙니다.\n"
            "  해결: 서버에서 gog 재인증\n"
            "    %s auth doctor              # 원인 자가진단(토큰/키링/클라이언트)\n"
            "    %s auth add bbonoyo@gmail.com   # 다시 로그인해 리프레시 토큰 재발급\n"
            "  ⚠️ 구글 클라우드 콘솔의 OAuth 동의 화면이 '테스트' 상태면 리프레시 토큰이\n"
            "     7일마다 만료됩니다. 매주 재인증이 싫으면 앱을 '프로덕션'으로 게시하세요."
            % (gog_bin() or "gog", gog_bin() or "gog")
        )

    # 후보마다 실패 이유가 다를 수 있다(플래그 이름이 틀렸는지, 인증이 막혔는지 …).
    # 예전엔 '마지막 후보의 오류'만 보여줘서 진짜 원인이 가려졌다 → 전부 보여준다.
    lines = ["드라이브 목록 조회에 실패했습니다. 시도한 명령과 각각의 오류:"]
    seen = set()
    for cmd, err in errors:
        one = short_err(err)
        if one in seen and len(seen) > 2:
            continue                       # 똑같은 오류가 반복되면 생략
        seen.add(one)
        lines.append("  $ gog %s\n      → %s" % (cmd, one))
    lines.append("  → `python3 %s --probe` 로 gog 의 실제 사용법을 확인하세요."
                 % os.path.abspath(__file__))
    raise GogError("\n".join(lines))


def download_file(file_id, name, dest_path):
    """
    파일 하나를 dest_path 로 내려받는다.
    안전장치: 임시 폴더에서 실행한 뒤 '거기에 생긴 파일'을 옮긴다.
    (gog 가 -o 플래그를 무시하고 현재 폴더에 원래 이름으로 저장해도 대응된다.)
    """
    tmpdir = tempfile.mkdtemp(prefix="news-dl-")
    try:
        for shape in ordered_shapes("download", DOWNLOAD_SHAPES):
            to_stdout = shape and shape[-1] == ">"
            args = fill(shape, id=file_id, out=os.path.join(tmpdir, name))
            rc, out, err = run_gog(args, cwd=tmpdir, binary=to_stdout)
            if rc != 0:
                continue

            if to_stdout:
                if not out:
                    continue
                with open(dest_path + ".part", "wb") as f:
                    f.write(out)
                os.replace(dest_path + ".part", dest_path)
                save_shape("download", shape)
                return True

            # 임시 폴더에 생긴 파일 중 가장 큰 것을 결과물로 본다.
            got = []
            for root, _dirs, files in os.walk(tmpdir):
                for fn in files:
                    p = os.path.join(root, fn)
                    try:
                        sz = os.path.getsize(p)
                    except OSError:
                        continue
                    if sz > 0:
                        got.append((sz, p))
            if not got:
                continue
            got.sort(reverse=True)
            shutil.move(got[0][1], dest_path)
            save_shape("download", shape)
            return True
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─────────────────────────────────────────────────────── 드라이브에서 날짜 찾기

def is_folder(entry):
    return entry.get("mime", "").endswith("apps.folder")


def pick_folder(entries, wanted_names):
    """이름이 후보 중 하나와 같은 폴더 찾기(공백 차이는 무시)."""
    norm = lambda s: re.sub(r"\s+", "", s or "").lower()
    wanted = {norm(w) for w in wanted_names}
    for e in entries:
        if is_folder(e) and norm(e["name"]) in wanted:
            return e
    return None


def find_day_folder(date):
    """
    신문스크랩 / YYYY-MM / YYYY-MM-DD 를 찾는다.
    월 폴더가 없는 구조여도(날짜 폴더가 바로 최상위) 동작하도록 한 단계 폴백을 둔다.
    못 찾으면 None (= 아직 안 올라옴).
    """
    root_id = os.getenv("NEWS_DRIVE_ROOT_ID", DEFAULT_ROOT_ID)
    top = list_children(root_id)

    month = date[:7]                       # 2026-09
    month_alt = [month, month.replace("-", ""), month[5:7], "%s년 %s월" % (date[:4], date[5:7])]
    mf = pick_folder(top, month_alt)

    candidates = list_children(mf["id"]) if mf else top
    day_alt = [date, date.replace("-", ""), date[5:].replace("-", ""), date[2:].replace("-", "")]
    df = pick_folder(candidates, day_alt)
    if df:
        return df
    # 월 폴더를 거쳤는데 없었다면 최상위에서 한 번 더(구조가 바뀐 경우 대비)
    if mf:
        return pick_folder(top, day_alt)
    return None


# ───────────────────────────────────────────────────────────── 실제 동기화

def classify(entry):
    """PDF / 이미지 / metadata.json / 그 외 로 분류."""
    name = entry["name"]
    ext = os.path.splitext(name)[1].lower()
    mime = entry.get("mime", "")
    if name.lower() == "metadata.json":
        return "meta"
    if ext == ".pdf" or mime == "application/pdf":
        return "pdf"
    if ext in IMAGE_EXTS or mime.startswith("image/"):
        return "image"
    return "other"


def safe_name(name):
    """경로 탈출(../) 방지 — 파일명만 남긴다."""
    return os.path.basename(name).replace("\\", "_").strip() or "unnamed"


def read_meta(dest):
    """캐시에 받아둔 metadata.json 에서 제목·원문 주소 등을 읽는다(없으면 빈 값)."""
    try:
        with open(os.path.join(dest, "metadata.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def build_index(date, dest, pdf_name, image_names, meta, source, failed=None):
    """
    웹(app.py)이 읽을 index.json 을 만든다. 드라이브에서 받았든 로컬에서 연결했든
    결과물의 모양은 똑같아야 해서 이 함수 하나로 통일한다.
    """
    index = {
        "date": date,
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "source": source,                       # drive:<폴더ID> 또는 local:<경로>
        "title": meta.get("title") or "",
        "source_url": meta.get("post_url") or meta.get("url") or "",
        "expected_count": meta.get("image_count") or len(image_names),
        "pdf": None,
        "images": [],
        "failed": failed or [],
    }
    if pdf_name:
        p = os.path.join(dest, pdf_name)
        if os.path.isfile(p):
            index["pdf"] = {"name": pdf_name, "size": os.path.getsize(p),
                            "pages": meta.get("pdf_page_count") or 0}
    for name in image_names:
        p = os.path.join(dest, name)
        if os.path.isfile(p):
            index["images"].append({"name": name, "size": os.path.getsize(p)})

    write_json(os.path.join(dest, "index.json"), index)
    return index


def local_day_dir(date):
    """수집기가 그날 신문을 만들어 두는 서버 폴더."""
    root = os.path.expanduser(os.getenv("NEWSPAPER_LOCAL_ROOT", "~/newspaper/data/newspapers"))
    return os.path.join(root, date[:7], date)


def sync_from_local(date, verbose=True):
    """
    서버에 이미 있는 파일을 쓴다 (구글 인증·네트워크 전혀 필요 없음).

    수집기(~/newspaper)가 05:30 에 사진·PDF 를 만들어 두므로, 그 파일을 캐시 폴더에
    **심볼릭 링크**로 연결만 한다 → 복사 안 하니 디스크를 두 배로 먹지 않고 즉시 반영된다.
    (NEWS_LOCAL_MODE=copy 로 하면 실제 복사 — 수집기가 지운 뒤에도 웹에 남기고 싶을 때)

    반환: 0 성공 / None 로컬에 쓸 파일이 없음(→ 호출한 쪽이 드라이브로 넘어간다)
    """
    src = local_day_dir(date)
    if not os.path.isdir(src):
        return None

    pdf_name, image_names = None, []
    for name in sorted(os.listdir(src)):
        if name.startswith("."):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext == ".pdf" and pdf_name is None:
            pdf_name = name
        elif ext in IMAGE_EXTS:
            image_names.append(name)
    if not pdf_name and not image_names:
        return None                      # metadata.json 만 남은 지난 날짜 → 로컬엔 없는 셈

    dest = day_dir(date)
    os.makedirs(dest, exist_ok=True)
    mode = os.getenv("NEWS_LOCAL_MODE", "link").lower()

    wanted = ([pdf_name] if pdf_name else []) + image_names
    if os.path.isfile(os.path.join(src, "metadata.json")):
        wanted.append("metadata.json")

    linked = 0
    for name in wanted:
        s_path = os.path.join(src, name)
        d_path = os.path.join(dest, safe_name(name))
        try:
            if os.path.islink(d_path) or os.path.isfile(d_path):
                if mode == "link" and os.path.realpath(d_path) == os.path.realpath(s_path):
                    continue                 # 이미 같은 파일을 가리키고 있다
                os.remove(d_path)
            if mode == "copy":
                shutil.copy2(s_path, d_path)
            else:
                os.symlink(s_path, d_path)
            linked += 1
        except OSError as e:
            if verbose:
                print("  ⚠️ %s 연결 실패: %s" % (name, e))

    # 내용이 바뀌었는지 보려고 '이전 인덱스'를 먼저 읽어 둔다.
    before = None
    try:
        with open(os.path.join(dest, "index.json"), encoding="utf-8") as f:
            before = json.load(f)
    except Exception:
        pass

    meta = read_meta(dest)
    index = build_index(date, dest, safe_name(pdf_name) if pdf_name else None,
                        [safe_name(n) for n in image_names], meta, source="local:" + src)

    # ⚠️ 파일 내용이 바뀌었는데 예전에 만들어 둔 ZIP 을 그대로 주면 옛날 사진이 나간다.
    #    (2026-09-16: 수집기가 같은 이름 파일을 '이미 있음'으로 건너뛰어 앞 6장이 옛 사진으로
    #     남았던 일이 있었다. 이름이 같아도 내용은 다를 수 있다 → 크기/목록으로 비교한다.)
    def fingerprint(ix):
        if not ix:
            return None
        pdf = ix.get("pdf") or {}
        return (pdf.get("name"), pdf.get("size"),
                tuple((i["name"], i.get("size")) for i in ix.get("images") or []))

    if fingerprint(before) != fingerprint(index):
        for stale in ("photos.zip", "all.zip"):
            try:
                os.remove(os.path.join(dest, stale))
            except OSError:
                pass
        shutil.rmtree(os.path.join(dest, ".thumb"), ignore_errors=True)

    if verbose:
        print("[%s] 서버 로컬에서 가져옴(%s) · PDF %s · 사진 %d장\n  ← %s"
              % (date, "복사" if mode == "copy" else "링크",
                 "O" if index["pdf"] else "X", len(index["images"]), src))
    prune(verbose=verbose)
    return 0


def sync(date, force=False, verbose=True):
    def say(msg):
        if verbose:
            print(msg, flush=True)

    folder = find_day_folder(date)
    if not folder:
        say("[%s] 드라이브에 아직 폴더가 없습니다 (보통 06:01 KST 업로드)." % date)
        return 2

    entries = list_children(folder["id"])
    if not entries:
        say("[%s] 폴더는 있는데 안이 비어 있습니다." % date)
        return 2

    dest = day_dir(date)
    os.makedirs(dest, exist_ok=True)

    pdf_entry, image_entries, meta_entry = None, [], None
    for e in entries:
        kind = classify(e)
        if kind == "pdf" and pdf_entry is None:
            pdf_entry = e
        elif kind == "image":
            image_entries.append(e)
        elif kind == "meta":
            meta_entry = e
    image_entries.sort(key=lambda e: e["name"])

    wanted = ([pdf_entry] if pdf_entry else []) + image_entries + ([meta_entry] if meta_entry else [])
    fetched, skipped, failed = 0, 0, []

    for e in wanted:
        name = safe_name(e["name"])
        path = os.path.join(dest, name)
        # 이미 같은 크기로 받아둔 파일은 건너뛴다(드라이브가 크기를 안 주면 존재만 확인).
        if not force and os.path.isfile(path):
            local = os.path.getsize(path)
            if local > 0 and (e["size"] == 0 or local == e["size"]):
                skipped += 1
                continue
        say("  ↓ %s (%s)" % (name, human(e["size"])))
        if download_file(e["id"], name, path):
            fetched += 1
        else:
            failed.append(name)

    # metadata.json 에서 원문 주소·제목을 읽어 둔다(있으면 웹에 같이 보여준다).
    meta = {}
    meta_path = os.path.join(dest, "metadata.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f) or {}
        except Exception:
            meta = {}

    index = build_index(date, dest, safe_name(pdf_entry["name"]) if pdf_entry else None,
                        [safe_name(e["name"]) for e in image_entries], meta,
                        source="drive:" + folder["id"], failed=failed)

    # 사진이 바뀌었으면 예전에 만들어 둔 ZIP 은 버린다(다음 요청 때 새로 만든다).
    if fetched:
        for stale in ("photos.zip",):
            try:
                os.remove(os.path.join(dest, stale))
            except OSError:
                pass

    say("[%s] 새로 받음 %d · 그대로 %d · 실패 %d · PDF %s · 사진 %d장"
        % (date, fetched, skipped, len(failed),
           "O" if index["pdf"] else "X", len(index["images"])))
    prune(verbose=verbose)
    return 1 if failed and not index["images"] and not index["pdf"] else 0


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def human(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f%s" % (n, unit) if unit == "B" else "%.1f%s" % (n, unit)
        n /= 1024


def prune(verbose=False):
    """
    오래된 자료 정리(하루치가 15~35MB라 방치하면 디스크를 먹는다).

    실제 규칙은 `retention_cleanup.py` 한 곳에 모여 있다(2026-09-19).
    여기서 부르는 이유는 **cron 을 하나 더 만들지 않기 위해서**다. 이 스크립트는
    이미 30분마다 돌고 있으니, 동기화가 끝날 때마다 같이 청소하면 된다.

    ⚠️ 예전에는 '최근 N개 날짜 폴더' 를 남겼는데, 신문이 평일에만 올라와서
       달력으로는 9~10일 전 자료까지 남았다 → 이제 **달력 날짜 기준**이다.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import retention_cleanup
    except Exception as e:           # 파일이 없거나 깨져도 동기화는 계속돼야 한다
        if verbose:
            print("  ⚠️ 보관 정리 건너뜀(retention_cleanup 불러오기 실패): %r" % e)
        return
    try:
        retention_cleanup.sweep_all(verbose=verbose)
    except Exception as e:
        if verbose:
            print("  ⚠️ 보관 정리 중 오류(동기화 자체는 성공): %r" % e)


# ─────────────────────────────────────────────────────────────────── 진단용

def probe():
    """gog 가 실제로 어떤 drive 명령을 지원하는지 찍어 본다."""
    exe = gog_bin()
    print("gog 실행파일 : %s" % (exe or "(못 찾음)"))
    print("캐시 폴더    : %s" % cache_root())
    print("드라이브 루트: %s" % os.getenv("NEWS_DRIVE_ROOT_ID", DEFAULT_ROOT_ID))
    have = [k for k in os.environ if k.startswith(GOG_ENV_PREFIXES)]
    print("gog 관련 환경변수: %s" % (", ".join(sorted(have)) or "(없음)"))
    print("기억된 명령 형태 : %s" % json.dumps(load_shapes(), ensure_ascii=False))
    if not exe:
        return 1
    # 하위 명령의 '자기 플래그'는 도움말 아래쪽에 나오는데, 예전엔 앞부분만 찍어서
    # 정작 필요한 부분이 잘렸다 → 공용 플래그 설명은 접고 전체를 보여준다.
    def show(args, keep_common=False):
        print("\n$ gog %s" % " ".join(args))
        print("-" * 60)
        rc, out, err = run_gog(args, timeout=30)
        text = (out or "").strip() or (err or "").strip()
        if not keep_common:
            # 모든 명령에 공통으로 붙는 전역 플래그 줄은 빼서 읽기 쉽게 만든다.
            common = ("--color", "--home=", "--client=", "--access-token", "--enable-commands",
                      "--disable-commands", "--gmail-no-send", "--readonly", "--wrap-untrusted",
                      "--results-only", "--select=", "--no-input", "-v, --verbose", "--version",
                      "-h, --help", "-a, --account", "-n, --dry-run", "-y, --force",
                      "-j, --json", "-p, --plain")
            lines, skip = [], False
            for line in text.splitlines():
                st = line.strip()
                if any(st.startswith(c) for c in common):
                    skip = True
                    continue
                if skip and st and line.startswith((" " * 20, "\t")):
                    continue          # 앞 줄 설명의 이어지는 줄
                skip = False
                lines.append(line)
            text = "\n".join(lines)
        print(text[:4000] or "(출력 없음)")
        if err.strip() and out.strip():
            print("[stderr] " + err.strip()[:400])

    for args in (["drive", "ls", "--help"], ["drive", "download", "--help"],
                 ["drive", "search", "--help"], ["auth", "list"]):
        show(args, keep_common=(args[0] == "auth"))
    return 0


def after_sync(date, rc, quiet):
    """
    사진이 준비됐으면 지면 글자 읽기(news_page_text.py)를 이어서 돌린다 (2026-09-24).
    웹 '📰 글+지면' 이 요약 기사와 신문 사진을 자동으로 잇는 데 쓴다.
    이미 읽은 장은 건너뛰므로 30분마다 불려도 처음 한 번만 시간이 든다.
    실패해도 동기화 결과(rc)는 그대로 돌려준다 — 부가 기능이 본업을 막지 않게.
    끄기: .env 에 NEWS_PAGE_OCR=0
    """
    if rc != 0 or os.getenv("NEWS_PAGE_OCR", "1") == "0":
        return rc
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import news_page_text
        news_page_text.build(date, verbose=not quiet)
    except Exception as e:
        if not quiet:
            print("  ⚠️ 지면 글자 읽기 건너뜀: %r" % e)
    return rc


def main():
    ap = argparse.ArgumentParser(description="구글 드라이브의 그날 신문(사진·PDF)을 로컬 캐시로 내려받는다.")
    ap.add_argument("date", nargs="?", default="", help="YYYY-MM-DD (기본: 오늘, KST)")
    ap.add_argument("--force", action="store_true", help="이미 받은 파일도 다시 받기")
    ap.add_argument("--probe", action="store_true", help="gog 사용법 진단 출력")
    ap.add_argument("--quiet", action="store_true", help="조용히 (cron 용)")
    ap.add_argument("--source", choices=("auto", "local", "drive"), default="auto",
                    help="auto(기본)=서버 로컬 먼저, 없으면 드라이브 / local=로컬만 / drive=드라이브만")
    args = ap.parse_args()

    load_env_file()
    load_gateway_env()

    if args.probe:
        return probe()

    date = args.date or today_kst()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print("날짜 형식은 YYYY-MM-DD 입니다: %s" % date, file=sys.stderr)
        return 1
    try:
        # 1순위: 서버에 이미 있는 파일(수집기가 만들어 둔 것) — 인증도 네트워크도 필요 없다.
        if args.source in ("auto", "local"):
            rc = sync_from_local(date, verbose=not args.quiet)
            if rc is not None:
                return after_sync(date, rc, args.quiet)
            if args.source == "local":
                if not args.quiet:
                    print("[%s] 서버 로컬(%s)에 신문 파일이 없습니다." % (date, local_day_dir(date)))
                return 2
        # 2순위: 구글 드라이브 (gog CLI)
        return after_sync(date, sync(date, force=args.force, verbose=not args.quiet), args.quiet)
    except GogError as e:
        print("[news_sync] %s" % e, file=sys.stderr)
        return 1
    except Exception as e:  # 예상 못 한 오류도 cron 로그에 남게
        print("[news_sync] 예상치 못한 오류: %r" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
