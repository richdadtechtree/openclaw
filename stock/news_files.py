# -*- coding: utf-8 -*-
"""
news_files.py — news_sync.py 가 내려받아 둔 "그날 신문" 캐시를 웹에서 읽기 위한 도우미.

[역할 분담]
  scripts/news_sync.py  : 구글 드라이브 → 서버 로컬 캐시 (하루 한 번, gog CLI 사용)
  stock/news_files.py   : 그 캐시를 읽어서 웹(app.py)에 넘겨줌  ← 이 파일
  stock/app.py          : /api/news/* 엔드포인트
  slack_digest_live.html: 화면(상단 '오늘 신문 원본' 패널)

웹 서버는 구글 드라이브를 직접 부르지 않는다. 요청마다 외부 API 를 부르면
느리고, 인증이 끊기면 페이지 전체가 멈추기 때문이다. 여기서는 **로컬 폴더만** 읽는다.

캐시 구조:
    ~/.openclaw/news_cache/2026-09-15/
        index.json        ← 목록·크기·원문 주소 (news_sync.py 가 씀)
        2026-09-15.pdf
        01.jpg … 30.gif
        .thumb/01.jpg     ← 썸네일(Pillow 가 있을 때만, 없으면 원본을 그대로 씀)
        photos.zip        ← 처음 요청될 때 한 번 만들어 재사용
"""

import json
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Pillow 는 있으면 좋고 없어도 되는 선택 사항(썸네일 축소용).
try:
    from PIL import Image  # noqa: F401
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def cache_root():
    return os.path.expanduser(os.getenv("NEWS_CACHE_DIR", "~/.openclaw/news_cache"))


def day_dir(date):
    return os.path.join(cache_root(), date)


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def valid_date(date):
    return bool(date) and bool(DATE_RE.fullmatch(date))


def load_index(date):
    """그날의 index.json 을 읽는다. 없으면 None."""
    if not valid_date(date):
        return None
    try:
        with open(os.path.join(day_dir(date), "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def cached_dates():
    """캐시에 남아 있는 날짜들(최신순)."""
    root = cache_root()
    if not os.path.isdir(root):
        return []
    out = [d for d in os.listdir(root)
           if DATE_RE.fullmatch(d) and os.path.isfile(os.path.join(root, d, "index.json"))]
    return sorted(out, reverse=True)


def latest_date():
    dates = cached_dates()
    return dates[0] if dates else None


def allowed_names(index):
    """index.json 에 적힌 파일 이름만 허용 목록으로 만든다(경로 탈출·임의 파일 열람 차단)."""
    names = set()
    if not index:
        return names
    if index.get("pdf"):
        names.add(index["pdf"]["name"])
    for im in index.get("images") or []:
        names.add(im["name"])
    return names


def resolve(date, name):
    """
    (date, 파일명) → 실제 경로. 목록에 없는 이름이면 None 을 돌려준다.
    ⚠️ 보안 핵심: 사용자가 보낸 name 을 그대로 경로에 붙이면 ../../etc/passwd 같은
       요청으로 아무 파일이나 읽힐 수 있다. 그래서 index.json 에 있는 이름만 통과시킨다.
    """
    index = load_index(date)
    if not index or name not in allowed_names(index):
        return None
    path = os.path.join(day_dir(date), os.path.basename(name))
    return path if os.path.isfile(path) else None


def media_type(name):
    ext = os.path.splitext(name)[1].lower()
    return {
        ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def ensure_thumb(date, name, width=420):
    """
    썸네일 경로를 돌려준다. Pillow 가 없으면 원본 경로를 그대로 준다
    (화면은 똑같이 보이고 데이터만 더 쓴다 — 기능이 죽지는 않는다).
    """
    src = resolve(date, name)
    if not src:
        return None
    if not HAVE_PIL:
        return src
    tdir = os.path.join(day_dir(date), ".thumb")
    dst = os.path.join(tdir, os.path.basename(name) + ".jpg")
    try:
        if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return dst
        os.makedirs(tdir, exist_ok=True)
        from PIL import Image
        with Image.open(src) as im:
            if getattr(im, "is_animated", False):
                im.seek(0)          # 움직이는 GIF 는 첫 장면만 쓴다
            im = im.convert("RGB")
            im.thumbnail((width, width * 6))
            tmp = dst + ".tmp"
            im.save(tmp, "JPEG", quality=72, optimize=True)
        os.replace(tmp, dst)
        return dst
    except Exception:
        return src  # 썸네일 실패는 치명적이지 않다 → 원본으로 대체


def ensure_zip(date, what="photos"):
    """
    한 번에 받을 ZIP 을 만든다(처음 요청될 때 만들고 그다음부터 재사용).
      what="photos" (기본) → 사진만        · 파일명 photos.zip
      what="all"           → 사진 + PDF    · 파일명 all.zip
    """
    index = load_index(date)
    if not index:
        return None
    if what == "all":
        names = sorted(allowed_names(index))
    else:
        names = sorted(im["name"] for im in index.get("images") or [])
    if not names:
        return None
    zpath = os.path.join(day_dir(date), "photos.zip" if what != "all" else "all.zip")
    if os.path.isfile(zpath) and os.path.getsize(zpath) > 0:
        return zpath
    tmp = zpath + ".tmp"
    try:
        # jpg/pdf 는 이미 압축된 형식이라 다시 압축해도 거의 안 줄고 CPU만 쓴다 → 그냥 담기(STORED).
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for n in names:
                p = resolve(date, n)
                if p:
                    z.write(p, arcname=n)
        os.replace(tmp, zpath)
        return zpath
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None


# ── 형광펜 표시 저장 ──────────────────────────────────────────────────────
# 신문 사진 위에 그은 형광펜을 서버에 보관한다. 폰에서 칠한 걸 PC 에서도 본다.
#
# ⚠️ 왜 news_cache 가 아닌 별도 폴더인가:
#    news_cache 는 news_sync.py 가 NEWS_CACHE_KEEP_DAYS(기본 7일) 지나면 통째로 지운다.
#    사진은 다시 받으면 되지만 **사람이 직접 그은 표시는 복구할 방법이 없다.**
#    그래서 지워지지 않는 자리에 따로 둔다.
#
# 좌표는 **0~1 비율**로 저장한다(사진 왼쪽 위가 0,0 / 오른쪽 아래가 1,1).
# 픽셀로 저장하면 화면 크기·확대 배율이 다른 기기에서 위치가 어긋난다.
MARKS_MAX_STROKES = 400          # 한 장에 그을 수 있는 선 개수
MARKS_MAX_POINTS = 2000          # 선 하나의 점 개수
MARKS_MAX_PAGES = 100            # 하루치 장수 상한
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")   # 사진 파일 이름 형태만


def marks_root():
    return os.path.expanduser(os.getenv("NEWS_MARKS_DIR", "~/.openclaw/news_marks"))


def marks_path(date):
    return os.path.join(marks_root(), "%s.json" % date)


def load_marks(date):
    """그날의 형광펜 표시. 없으면 빈 dict."""
    if not valid_date(date):
        return {}
    try:
        with open(marks_path(date), encoding="utf-8") as f:
            data = json.load(f)
        return data.get("marks", {}) if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print("[marks] 읽기 실패 %s: %r" % (date, e))
        return {}


def _clean_stroke(st):
    """선 하나를 안전한 형태로 다듬는다. 이상하면 None."""
    if not isinstance(st, dict):
        return None
    pts = st.get("pts")
    if not isinstance(pts, list) or len(pts) < 1:
        return None
    out = []
    for pt in pts[:MARKS_MAX_POINTS]:
        if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
            continue
        try:
            x, y = float(pt[0]), float(pt[1])
        except (TypeError, ValueError):
            continue
        # 사진 밖으로 나간 좌표는 가장자리로 붙인다(0~1 유지)
        out.append([round(min(max(x, 0.0), 1.0), 4), round(min(max(y, 0.0), 1.0), 4)])
    if not out:
        return None
    color = st.get("c")
    if not (isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
        color = "#ffe14d"
    try:
        width = float(st.get("w", 0.018))
    except (TypeError, ValueError):
        width = 0.018
    return {"c": color, "w": round(min(max(width, 0.002), 0.2), 4), "pts": out}


def clean_marks(raw, date=""):
    """브라우저가 보낸 값을 그대로 믿지 않고 형태·크기를 검사해 정리한다."""
    if not isinstance(raw, dict):
        return {}
    index = load_index(date) if date else None
    allowed = allowed_names(index) if index else None   # 그날 실제로 있는 사진 이름만
    cleaned = {}
    for name, strokes in list(raw.items())[:MARKS_MAX_PAGES]:
        if not isinstance(name, str) or not isinstance(strokes, list):
            continue
        # 사진 '파일 이름' 형태만 받는다. 지금은 JSON 키로만 쓰지만, 나중에 누가
        # 이 값을 경로에 쓰면 ../../ 같은 장난이 사고가 된다 → 입구에서 막는다.
        if not SAFE_NAME_RE.fullmatch(name):
            continue
        if allowed is not None and name not in allowed:
            continue                                     # 없는 사진 이름은 버린다
        keep = [s for s in (_clean_stroke(x) for x in strokes[:MARKS_MAX_STROKES]) if s]
        if keep:
            cleaned[name] = keep
    return cleaned


def save_marks(date, raw):
    """형광펜 표시를 저장한다. 반환 (성공여부, 정리된 표시)."""
    if not valid_date(date):
        return False, {}
    marks = clean_marks(raw, date)
    try:
        os.makedirs(marks_root(), exist_ok=True)
        tmp = marks_path(date) + ".tmp"
        # 임시 파일에 쓰고 바꿔치기 — 저장 도중 꺼져도 기존 파일이 깨지지 않는다
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"date": date, "saved_at": datetime.now(KST).isoformat(),
                       "marks": marks}, f, ensure_ascii=False)
        os.replace(tmp, marks_path(date))
        return True, marks
    except Exception as e:
        print("[marks] 저장 실패 %s: %r" % (date, e))
        return False, marks


def summary(date):
    """
    화면이 그대로 쓸 수 있는 형태로 정리해서 준다.
    아직 안 올라왔으면 ready=False + 가장 최근 날짜(latest)를 같이 알려준다.
    """
    index = load_index(date)
    if not index:
        return {
            "ok": True, "ready": False, "date": date,
            "latest": latest_date(),
            "reason": "아직 준비되지 않았습니다 (보통 오전 6시경 올라옵니다).",
        }

    def furl(name, dl=0):
        return "/api/news/file?date=%s&name=%s%s" % (date, name, "&dl=1" if dl else "")

    pdf = None
    if index.get("pdf"):
        pdf = dict(index["pdf"])
        pdf["url"] = furl(pdf["name"], dl=1)
        pdf["view_url"] = furl(pdf["name"])

    images = []
    for im in index.get("images") or []:
        images.append({
            "name": im["name"], "size": im.get("size", 0),
            "url": furl(im["name"]), "download_url": furl(im["name"], dl=1),
            "thumb": "/api/news/thumb?date=%s&name=%s" % (date, im["name"]),
        })

    photos_size = sum(i["size"] for i in images)
    total = (pdf["size"] if pdf else 0) + photos_size
    return {
        "ok": True, "ready": True, "date": date,
        "title": index.get("title") or "",
        "source_url": index.get("source_url") or "",
        "updated": index.get("updated") or "",
        "pdf": pdf, "images": images, "count": len(images),
        "expected_count": index.get("expected_count") or len(images),
        "total_size": total,
        "photos_size": photos_size,
        "zip_url": "/api/news/zip?date=%s" % date,                 # 사진만
        "zip_all_url": "/api/news/zip?date=%s&what=all" % date,    # 사진+PDF
        "latest": latest_date(),
        "thumbs": HAVE_PIL,
    }
